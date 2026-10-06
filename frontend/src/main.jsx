import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import AuthGate from "./components/auth/AuthGate.jsx";
import { AppSettingsProvider } from "./context/AppSettingsContext.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AppSettingsProvider>
        <AuthProvider>
          <AuthGate />
        </AuthProvider>
      </AppSettingsProvider>
    </BrowserRouter>
  </StrictMode>
);