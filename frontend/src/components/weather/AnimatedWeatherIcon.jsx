const CODE_GROUPS = {
  clear: [0, 1],
  cloudy: [2, 3],
  fog: [45, 48],
  drizzle: [51, 53, 55],
  rain: [61, 63, 65, 80, 81, 82],
  snow: [71, 73, 75],
  storm: [95, 96, 99],
};

function groupForCode(code) {
  for (const [group, codes] of Object.entries(CODE_GROUPS)) {
    if (codes.includes(code)) return group;
  }
  return "cloudy";
}

export default function AnimatedWeatherIcon({ code, size = 48 }) {
  const group = groupForCode(code);

  return (
    <div className={`wx-icon wx-${group}`} style={{ width: size, height: size }}>
      {group === "clear" && <div className="wx-sun" />}
      {group === "cloudy" && (
        <>
          <div className="wx-sun wx-sun-behind" />
          <div className="wx-cloud" />
        </>
      )}
      {group === "fog" && (
        <>
          <div className="wx-fog-line" />
          <div className="wx-fog-line" />
          <div className="wx-fog-line" />
        </>
      )}
      {group === "drizzle" && (
        <>
          <div className="wx-cloud" />
          <div className="wx-drop wx-drop-1" />
          <div className="wx-drop wx-drop-2" />
        </>
      )}
      {group === "rain" && (
        <>
          <div className="wx-cloud wx-cloud-dark" />
          <div className="wx-drop wx-drop-1" />
          <div className="wx-drop wx-drop-2" />
          <div className="wx-drop wx-drop-3" />
        </>
      )}
      {group === "snow" && (
        <>
          <div className="wx-cloud" />
          <div className="wx-flake wx-flake-1">❄</div>
          <div className="wx-flake wx-flake-2">❄</div>
        </>
      )}
      {group === "storm" && (
        <>
          <div className="wx-cloud wx-cloud-dark" />
          <div className="wx-bolt">⚡</div>
        </>
      )}
    </div>
  );
}
