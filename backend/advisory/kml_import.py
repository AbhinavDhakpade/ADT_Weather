"""
Shared KML import logic.

One KML file = one field boundary (one Placemark with a Polygon), exported from
Google Earth Pro. `import_kml()` turns one such file into a FarmProfile and
decides what to do about duplicates and logins. It is used by the
`import_kml_farmers` management command and by the admin upload page, so the
rules live in exactly one place.

Outcome for each file (ImportResult.status):

  "error"    The file could not be read, or has no usable polygon.
  "exists"   Already present: the same file name was imported before, OR the
             same farmer name already has a farm at (about) the same place.
             Nothing is changed.
  "added"    Known farmer name, but a different place: a new farm is created
             and linked to that farmer's existing login (no new password).
  "created"  New farmer: a new farm AND a new login (username + one-time
             password) are created.
"""

import datetime
import math
import re
import secrets
import string
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction

from .models import FarmProfile

KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

# Two farms of the same farmer whose centres are closer than this are treated
# as the same field (e.g. the same KML saved again under another file name).
SAME_PLACE_METRES = 100

# A real field boundary is a few KB. Anything bigger than this is not a normal
# KML export, so refuse it instead of loading it.
MAX_KML_BYTES = 5 * 1024 * 1024

# One file may hold many fields (one Placemark each); refuse absurdly large ones.
MAX_PLACEMARKS = 100


@dataclass
class ImportResult:
    filename: str
    status: str  # "created" | "added" | "exists" | "error"
    message: str
    farmer_name: str = ""
    farm_id: Optional[int] = None
    username: str = ""
    password: str = ""  # only filled when a brand-new login was created


# ---------------------------------------------------------------- parsing ---

def _parse_coordinates(text):
    """'<lon>,<lat>,<alt> <lon>,<lat>,<alt> ...' -> [[lon, lat], ...]"""
    points = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) < 2:
            continue
        points.append([float(parts[0]), float(parts[1])])
    return points


def _polygon_centroid_and_area_ha(points):
    """
    Shoelace centroid + area on a local equirectangular projection (longitude
    scaled by cos(mean latitude)). Accurate enough for single-field plots
    without needing a GIS/projection library.
    """
    if len(points) < 3:
        lon, lat = points[0]
        return lat, lon, 0.0

    mean_lat = sum(p[1] for p in points) / len(points)
    scale = math.cos(math.radians(mean_lat))
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * scale

    xy = [(p[0] * m_per_deg_lon, p[1] * m_per_deg_lat) for p in points]
    if xy[0] != xy[-1]:
        xy.append(xy[0])

    a = cx = cy = 0.0
    for i in range(len(xy) - 1):
        x0, y0 = xy[i]
        x1, y1 = xy[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5

    if abs(a) < 1e-9:
        return (
            sum(p[1] for p in points) / len(points),
            sum(p[0] for p in points) / len(points),
            0.0,
        )

    cx /= 6 * a
    cy /= 6 * a
    return cy / m_per_deg_lat, cx / m_per_deg_lon, round(abs(a) / 10_000.0, 3)


def _read_kml_bytes(source):
    """
    Read the whole KML into memory, refusing oversized files and any DOCTYPE /
    ENTITY declaration. Python's XML parser can be made to eat huge amounts of
    memory by "entity expansion" tricks, and a real KML file never needs them.
    """
    if hasattr(source, "read"):
        data = source.read(MAX_KML_BYTES + 1)
    else:
        with open(source, "rb") as fh:
            data = fh.read(MAX_KML_BYTES + 1)
    if len(data) > MAX_KML_BYTES:
        raise ValueError("the file is larger than 5 MB, which is not a normal KML export")
    if re.search(rb"<!\s*(DOCTYPE|ENTITY)", data, re.IGNORECASE):
        raise ValueError("DOCTYPE/ENTITY declarations are not allowed in KML files")
    return data


def _tidy_name(name, fallback):
    """Collapse spaces; use `fallback` if empty; Title Case if ALL CAPS / all lower."""
    name = " ".join((name or "").split())
    if not name:
        name = fallback
    if name == name.lower() or name == name.upper():
        name = name.title()
    return name


def _extended_data(placemark):
    """The <ExtendedData><Data name=..><value> pairs of one Placemark, as a dict."""
    out = {}
    for d in placemark.findall("kml:ExtendedData/kml:Data", KML_NS):
        key = (d.get("name") or "").strip()
        value = d.find("kml:value", KML_NS)
        if key and value is not None and (value.text or "").strip():
            out[key] = " ".join(value.text.split())
    return out


_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y")


def _parse_date(text):
    """Day-first dates in the formats seen in farmer sheets; None if unreadable."""
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime((text or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def _farm_extras(extra):
    """Phone / village / planting date from ExtendedData, only the ones that are usable."""
    out = {}
    phone = re.sub(r"\.0+$", "", extra.get("Mobile No", ""))  # "9970714280.0" -> "9970714280"
    phone = re.sub(r"[^\d+]", "", phone)[:20]
    if phone:
        out["phone"] = phone
    village = extra.get("Address", "")[:120]
    if village:
        out["village"] = village
    planted = _parse_date(extra.get("Planting Date", ""))
    if planted:
        out["planting_date"] = planted
    return out


def _extract_all_placemarks(source):
    """Every Placemark that has a polygon: [(name, points, extended_data), ...]."""
    root = ET.fromstring(_read_kml_bytes(source))
    found = []
    for pm in root.findall(".//kml:Placemark", KML_NS):
        coords_el = pm.find(".//kml:Polygon//kml:coordinates", KML_NS)
        if coords_el is None or not (coords_el.text or "").strip():
            continue
        points = _parse_coordinates(coords_el.text)
        if len(points) < 3:
            continue
        name_el = pm.find("kml:name", KML_NS)
        found.append((name_el.text if name_el is not None else "", points, _extended_data(pm)))
    return found


def _extract_placemark(source, filename):
    """`source` is a file path or an open file-like object. Returns (name, points) or None."""
    root = ET.fromstring(_read_kml_bytes(source))
    placemark = root.find(".//kml:Placemark", KML_NS)
    if placemark is None:
        return None

    name_el = placemark.find("kml:name", KML_NS)
    name = " ".join((name_el.text or "").split()) if name_el is not None else ""
    if not name:
        name = filename.rsplit(".", 1)[0]
    if name == name.lower() or name == name.upper():
        name = name.title()

    coords_el = placemark.find(".//kml:Polygon//kml:coordinates", KML_NS)
    if coords_el is None or not (coords_el.text or "").strip():
        return None
    points = _parse_coordinates(coords_el.text)
    if len(points) < 3:
        return None
    return name, points


def _distance_m(lat1, lon1, lat2, lon2):
    """Small-distance approximation, plenty for 'same field?' checks."""
    m_lat = 111_320.0
    m_lon = 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lat1 - lat2) * m_lat, (lon1 - lon2) * m_lon)


# ------------------------------------------------------------------ logins ---

def _new_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _free_username(User, farm_id):
    """farmer<farm id>, or farmer<id>-2, -3 ... if that name is taken."""
    base = f"farmer{farm_id}"
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}-{n}"
    return username


# ------------------------------------------------------------- main entry ---

def import_kml(source, filename, dry_run=False):
    """
    Import the FIRST field of one KML file. `source` is a path or file-like object,
    `filename` the original file name (used for duplicate detection). With dry_run=True
    nothing is written, but the result says what would happen. For files that hold
    several fields use import_kml_file().
    """
    try:
        parsed = _extract_placemark(source, filename)
    except ET.ParseError as exc:
        return ImportResult(filename, "error", f"Could not read the file as XML ({exc}).")
    except (ValueError, OSError) as exc:
        return ImportResult(filename, "error", f"Could not use the file ({exc}).")

    if parsed is None:
        return ImportResult(filename, "error", "No usable polygon/coordinates found.")

    name, points = parsed
    return _import_parsed(name, points, filename, filename, {}, dry_run)


def import_kml_file(source, filename, dry_run=False):
    """
    Import EVERY field in one KML file (one Placemark with a polygon = one field).
    Returns a list with one ImportResult per field. A file with a single field behaves
    exactly like import_kml(); with several, each field is remembered as "<file>#<n>".
    Phone, village and planting date are read from the Placemark's ExtendedData.
    """
    try:
        fields = _extract_all_placemarks(source)
    except ET.ParseError as exc:
        return [ImportResult(filename, "error", f"Could not read the file as XML ({exc}).")]
    except (ValueError, OSError) as exc:
        return [ImportResult(filename, "error", f"Could not use the file ({exc}).")]

    if not fields:
        return [ImportResult(filename, "error", "No usable polygon/coordinates found.")]
    if len(fields) > MAX_PLACEMARKS:
        return [ImportResult(
            filename, "error",
            f"The file holds {len(fields)} fields; the limit is {MAX_PLACEMARKS} per file.",
        )]

    stem = filename.rsplit(".", 1)[0]
    single = len(fields) == 1
    results = []
    for i, (raw_name, points, extra) in enumerate(fields, start=1):
        key = filename if single else f"{filename}#{i}"
        label = filename if single else f"{filename} #{i}"
        name = _tidy_name(raw_name, stem if single else f"{stem} {i}")
        results.append(_import_parsed(name, points, key, label, extra, dry_run))
    return results


def _import_parsed(name, points, source_key, label, extra, dry_run):
    """Decide what to do with one parsed field. `source_key` is the duplicate-detection
    key stored on the farm; `label` is what the result row shows."""
    lat, lon, area_ha = _polygon_centroid_and_area_ha(points)

    # Rule 1: this exact file was imported before.
    same_file = FarmProfile.objects.filter(boundary_source_file=source_key).first()
    if same_file is not None:
        return ImportResult(
            label, "exists",
            f"Already present: farm #{same_file.id} ({same_file.farmer_name}) was imported from this file name.",
            farmer_name=same_file.farmer_name, farm_id=same_file.id,
        )

    # Rule 2: same farmer name at about the same place (e.g. a renamed copy).
    same_name = list(FarmProfile.objects.filter(farmer_name__iexact=name).order_by("id"))
    for farm in same_name:
        if _distance_m(lat, lon, farm.latitude, farm.longitude) <= SAME_PLACE_METRES:
            return ImportResult(
                label, "exists",
                f"Already present: {farm.farmer_name} already has farm #{farm.id} at this location.",
                farmer_name=farm.farmer_name, farm_id=farm.id,
            )

    defaults = {
        "farm_name": f"{name} Field",
        "farmer_name": name,
        "latitude": lat,
        "longitude": lon,
        "area_hectares": area_ha if area_ha > 0 else 1.0,
        "boundary_geojson": points,
        "boundary_source_file": source_key,
        "crop_name": "Sugarcane",
        "variety": "Co 86032",
        "soil_type": "Black Cotton",
        "irrigation_method": "Drip",
        "village": "",
        "planting_date": datetime.date.today(),
    }
    defaults.update(_farm_extras(extra))  # phone / village / planting date from the KML, if present

    User = get_user_model()
    owner = next((f.owner for f in same_name if f.owner_id), None)

    # Rule 3: known farmer, different place -> another farm for the same login.
    if owner is not None:
        if dry_run:
            return ImportResult(
                label, "added", f"(dry run) Would add a new farm for {name} (login {owner.username}).",
                farmer_name=name, username=owner.username,
            )
        farm = FarmProfile.objects.create(owner=owner, **defaults)
        return ImportResult(
            label, "added",
            f"New farm #{farm.id} added for existing farmer {name} (login {owner.username}).",
            farmer_name=name, farm_id=farm.id, username=owner.username,
        )

    # Rule 4: new farmer -> new farm and a new login.
    if dry_run:
        return ImportResult(
            label, "created", f"(dry run) Would create a new farm and login for {name}.",
            farmer_name=name,
        )
    with transaction.atomic():
        farm = FarmProfile.objects.create(**defaults)
        username = _free_username(User, farm.id)
        password = _new_password()
        user = User.objects.create_user(username=username, password=password, first_name=name[:150])
        farm.owner = user
        farm.save(update_fields=["owner"])
    return ImportResult(
        label, "created", f"New farmer {name}: farm #{farm.id} and login {username} created.",
        farmer_name=name, farm_id=farm.id, username=username, password=password,
    )