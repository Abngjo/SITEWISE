import { useEffect, useState } from "react";
import Login from "./components/Login.jsx";
import Shell, { NAV } from "./components/Shell.jsx";
import { StoreProvider, useStore } from "./store.jsx";
import { useTheme } from "./theme.js";
import { ErrorState, Loading } from "./ui.jsx";
import Payment from "./pages/Payment.jsx";
import Evidence from "./pages/Evidence.jsx";
import Model from "./pages/Model.jsx";
import Schedule from "./pages/Schedule.jsx";
import Report from "./pages/Report.jsx";
import Safety from "./pages/Safety.jsx";
import Costs from "./pages/Costs.jsx";

const PAGES = { payment: Payment, evidence: Evidence, model: Model, schedule: Schedule, report: Report, safety: Safety, costs: Costs };
const routeFromHash = () => { const h = location.hash.slice(1); return NAV.some(n => n[0] === h) ? h : "payment"; };

function Routed() {
  const [route, setRoute] = useState(routeFromHash);
  const { project, error, loadAll } = useStore();
  useEffect(() => { const f = () => { setRoute(routeFromHash()); window.scrollTo(0, 0); }; window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  const Page = PAGES[route];
  if (error && !project) return <ErrorState message={error} onRetry={loadAll} />;
  if (!project) return <Loading label="Loading project" />;
  return <div className="page-enter" key={route}><Page /></div>;
}

export default function App() {
  const [theme, setTheme] = useTheme();
  const [user, setUser] = useState(() => { try { return JSON.parse(sessionStorage.getItem("sw-user")); } catch { return null; } });
  const signIn = u => { try { sessionStorage.setItem("sw-user", JSON.stringify(u)); } catch { /* ignore */ } setUser(u); };
  const signOut = () => { try { sessionStorage.removeItem("sw-user"); } catch { /* ignore */ } setUser(null); };

  if (!user) return <Login onSignedIn={signIn} theme={theme} setTheme={setTheme} />;
  return (
    <StoreProvider>
      <div className="app-enter">
        <Shell theme={theme} setTheme={setTheme} user={user} onSignOut={signOut}>
          <Routed />
        </Shell>
      </div>
    </StoreProvider>
  );
}
