import App from "../../App.jsx";
import { useAuth } from "../../context/AuthContext";
import { DataProvider } from "../../context/DataContext";
import LoginPage from "../../pages/LoginPage";

// Shows the login page until someone is logged in, then the real app.
// `key` makes the data layer start fresh if a different person logs in.
export default function AuthGate() {
  const { user, checking } = useAuth();
  if (checking) return <div className="center-page">Loading…</div>;
  if (!user) return <LoginPage />;
  return (
    <DataProvider key={user.username}>
      <App />
    </DataProvider>
  );
}