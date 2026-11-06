import { useEffect, useState } from "react";
import { useStore } from "../store.jsx";
import { Icon } from "../ui.jsx";
import DynamicIsland from "./DynamicIsland.jsx";
import ThemeSwitch from "./ThemeSwitch.jsx";

export const NAV = [
  ["payment", "Overview / Payment", "payment"],
  ["evidence", "Evidence", "evidence"],
  ["model", "3D Model", "model"],
  ["schedule", "Schedule", "schedule"],
  ["report", "Report", "report"],
  ["safety", "Safety", "safety"],
  ["costs", "AI Costs", "costs"],
];

const hashRoute = () => { const h = location.hash.slice(1); return NAV.some(n => n[0] === h) ? h : "payment"; };

export default function Shell({ children, theme, setTheme, user, onSignOut }) {
  const { project, pendingReview, health, reset } = useStore();
  const [route, setRoute] = useState(hashRoute);
  useEffect(() => { const f = () => { setRoute(hashRoute()); setMenu(false); }; window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  const [menu, setMenu] = useState(false);
  const [resetting, setResetting] = useState(false);
  const pending = pendingReview;

  const doReset = async () => { setResetting(true); try { await reset(); } finally { setResetting(false); setMenu(false); } };
  // B9 hidden reset: Shift + Alt + R
  useEffect(() => {
    const k = e => { if (e.shiftKey && e.altKey && e.code === "KeyR") { e.preventDefault(); doReset(); } };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  return (
    <div className="shell">
      <aside className="side">
        <a className="brand" href="#payment"><span className="brand-mark" aria-hidden="true" /><span>SITEWISE</span></a>
        <nav aria-label="Main">
          {NAV.map(([id, label, icon]) => (
            <a key={id} href={`#${id}`} className="nav" aria-current={route === id ? "page" : undefined}>
              <Icon name={icon} /><span>{label}</span>
              {id === "evidence" && pending > 0 && <span className="count" aria-label={`${pending} awaiting review`}>{pending}</span>}
            </a>
          ))}
        </nav>
        <div className="side-foot">
          <span className={`conn ${health}`}><i />{health === "ok" ? "API connected" : health === "offline" ? "API offline" : "Connecting"}</span>
          <span>AI observes · evidence supports · engineer certifies</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="proj">
            <b>{project?.name_en || "Loading project…"}</b>
            <span lang="ar" dir="rtl" className="ar">{project?.name_ar}</span>
          </div>
          <span className="cert">{project?.certificate || "IPC-04"}</span>
          <span className="sample">SAMPLE DATA</span>
          <DynamicIsland />
          <div className="top-right">
            <ThemeSwitch value={theme} onChange={setTheme} />
            <div className="user">
              <button className="avatar" onClick={() => setMenu(m => !m)} aria-expanded={menu} aria-haspopup="menu" title={user?.email}>
                {(user?.email || "NA").slice(0, 2).toUpperCase()}
              </button>
              {menu && (
                <div className="menu" role="menu">
                  <div className="menu-head"><b>Site engineer</b><span>{user?.email}</span></div>
                  <button role="menuitem" onClick={doReset} disabled={resetting}><Icon name="reset" size={16} />{resetting ? "Resetting…" : "Reset demo state"}<kbd>⇧⌥R</kbd></button>
                  <a role="menuitem" href="/m" target="_blank" rel="noreferrer"><Icon name="phone" size={16} />Open mobile upload (/m)</a>
                  <button role="menuitem" onClick={onSignOut}><Icon name="logout" size={16} />Sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className="content" id="main">{children}</main>
      </div>
    </div>
  );
}
