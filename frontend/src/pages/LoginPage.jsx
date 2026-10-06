import { useState } from "react";
import { useAuth } from "../context/AuthContext";

const field = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid var(--border)",
  background: "var(--bg)",
  color: "inherit",
  fontSize: 15,
  boxSizing: "border-box",
};

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(
        err.response?.status === 400
          ? "Wrong username or password."
          : "Could not reach the AgriAura server. Please try again."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center-page">
      <form
        onSubmit={onSubmit}
        style={{
          width: "100%", maxWidth: 340, display: "flex", flexDirection: "column", gap: 12,
          background: "var(--surface)", border: "1px solid var(--border)",
          borderRadius: "var(--radius)", boxShadow: "var(--shadow)", padding: 24,
        }}
      >
        <div style={{ fontSize: 40, textAlign: "center" }}>🌾</div>
        <div style={{ fontSize: 20, fontWeight: 700, textAlign: "center" }}>AgriAura</div>
        <div style={{ textAlign: "center", fontSize: 14, opacity: 0.7 }}>Sign in to see your farm</div>
        <input style={field} placeholder="Username" autoComplete="username"
          value={username} onChange={(e) => setUsername(e.target.value)} />
        <input style={field} type="password" placeholder="Password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <div role="alert" style={{ color: "#c0392b", fontSize: 14 }}>{error}</div>}
        <button className="btn-primary" type="submit" disabled={busy || !username || !password}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}