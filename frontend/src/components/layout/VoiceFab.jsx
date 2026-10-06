import { useState } from "react";
import { useAppData } from "../../context/DataContext";

export default function VoiceFab() {
  const [speaking, setSpeaking] = useState(false);
  const { dashboard } = useAppData();

  const buildSpeech = () => {
    if (!dashboard) return "AgriAura Smart Advisory. Data is still loading.";
    const { health_score, current_stage, mini_diseases, today_weather, alerts } = dashboard;
    const topDisease = mini_diseases?.[0];
    const secondDisease = mini_diseases?.[1];
    const rainLine = today_weather
      ? `Rainfall of ${today_weather.rainfall_mm} millimeters today.`
      : "";
    const alertLine = alerts?.length
      ? `There are ${alerts.length} active alerts. The most important: ${alerts[0].title}.`
      : "No active alerts.";
    return `AgriAura Smart Advisory. Crop health score is ${health_score} out of 100. Current crop stage is ${current_stage}. ${
      topDisease ? `${topDisease.name} risk is ${topDisease.risk_label} at ${topDisease.risk_score} percent.` : ""
    } ${
      secondDisease ? `${secondDisease.name} risk is ${secondDisease.risk_label} at ${secondDisease.risk_score} percent.` : ""
    } ${rainLine} ${alertLine}`;
  };

  const toggleVoice = () => {
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    if (!("speechSynthesis" in window)) return;
    const utterance = new SpeechSynthesisUtterance(buildSpeech());
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.onend = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  return (
    <button
      className={`voice-fab${speaking ? " speaking" : ""}`}
      onClick={toggleVoice}
      title="Voice Guidance"
      aria-label="Voice guidance"
    >
      {speaking ? "🔇" : "🔊"}
    </button>
  );
}
