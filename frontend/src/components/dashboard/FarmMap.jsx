import { useEffect } from "react";
import {
  MapContainer, TileLayer, Marker, Popup,
  Circle, useMapEvents, useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";
import { haToAcres } from "../../utils/helpers";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Custom green marker for edit mode
const greenIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png",
  shadowUrl: markerShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

// Sub-component: fly the map center whenever lat/lng change (edit mode)
function MapFlyTo({ lat, lng }) {
  const map = useMap();
  useEffect(() => {
    if (lat && lng) map.flyTo([lat, lng], map.getZoom(), { duration: 0.8 });
  }, [lat, lng, map]);
  return null;
}

// Sub-component: handle click-to-set-coordinates in edit mode
function ClickHandler({ onMapClick }) {
  useMapEvents({
    click(e) {
      onMapClick(
        parseFloat(e.latlng.lat.toFixed(6)),
        parseFloat(e.latlng.lng.toFixed(6))
      );
    },
  });
  return null;
}

/**
 * FarmMap — view mode: shows marker + green area circle
 * FarmMap — edit mode: clicking the map sets new lat/lng,
 *           area circle resizes live as area_hectares changes
 */
export default function FarmMap({ farm, editMode = false, editLat, editLng, editArea, onMapClick }) {
  if (!farm) return null;

  // In edit mode use the live draft values, in view mode use the saved farm values
  const lat = editMode && editLat !== undefined ? editLat : farm.latitude;
  const lng = editMode && editLng !== undefined ? editLng : farm.longitude;
  const area = editMode && editArea !== undefined ? editArea : farm.area_hectares;

  // Circle radius: sqrt(area_hectares * 10000 / π)  →  meters
  const radiusM = Math.sqrt((area * 10000) / Math.PI);

  return (
    <div className="farm-leaflet-wrap" style={{ position: "relative" }}>
      {editMode && (
        <div className="map-edit-hint">
          📍 Click anywhere on the map to set your farm location
        </div>
      )}
      <MapContainer
        center={[lat, lng]}
        zoom={14}
        scrollWheelZoom={false}
        style={{ height: editMode ? 340 : 280, width: "100%", borderRadius: 12 }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {editMode && <ClickHandler onMapClick={onMapClick} />}
        {editMode && <MapFlyTo lat={lat} lng={lng} />}
        <Circle
          center={[lat, lng]}
          radius={radiusM}
          pathOptions={{
            color: editMode ? "#e07b00" : "#2d7a4f",
            fillColor: editMode ? "#f5a623" : "#4caf78",
            fillOpacity: 0.22,
            weight: editMode ? 2 : 1.5,
            dashArray: editMode ? "6 4" : null,
          }}
        />
        <Marker position={[lat, lng]} icon={editMode ? greenIcon : new L.Icon.Default()}>
          <Popup>
            <strong>{farm.farm_name}</strong>
            <br />
            {farm.crop_name} · {farm.variety}
            <br />
            {farm.soil_type} soil · {haToAcres(area)} Acres
            <br />
            {lat.toFixed(5)}°N, {lng.toFixed(5)}°E
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  );
}
