import { useEffect, useRef, useState } from "react";
import { STATUS } from "./api/adapters.js";

export const qar = n => `QAR ${Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
export const num = n => Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 2 });
export const fmtDate = s => (s ? new Date(s.length === 10 ? s + "T00:00:00Z" : s).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Qatar" }) : "—");
export const fmtDateTime = s => (s ? new Date(s).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Qatar" }) : "—");

// One authored icon set: 24px grid, 1.6 stroke.
const P = {
  payment: '<path d="M4 20h16M6 16V10M10 16V6M14 16v-4M18 16V8"/>',
  evidence: '<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 17l5-4.5 3.5 3 3-2.5L20 17"/>',
  model: '<path d="M12 3.5l8 4.5v8L12 20.5 4 16V8z"/><path d="M4 8l8 4.5L20 8M12 12.5v8"/>',
  schedule: '<rect x="3.5" y="5" width="17" height="15" rx="2"/><path d="M3.5 10h17M8 3v4M16 3v4M7.5 14h4M13 17h3.5"/>',
  report: '<path d="M7 3.5h7l4 4V20.5H7z"/><path d="M14 3.5v4h4M10 12h5M10 15.5h5"/>',
  safety: '<path d="M12 3.5l7 3v5.5c0 4-3 7.2-7 8.5-4-1.3-7-4.5-7-8.5V6.5z"/><path d="M9 12l2.2 2.2L15.5 10"/>',
  costs: '<circle cx="12" cy="12" r="8.5"/><path d="M14.8 9.2c-.5-.9-1.6-1.4-2.8-1.4-1.6 0-2.8.8-2.8 2s1.2 1.7 2.8 2.1 2.8.9 2.8 2.1-1.2 2-2.8 2c-1.3 0-2.4-.6-2.9-1.5M12 6v1.8M12 16.2V18"/>',
  sun: '<circle cx="12" cy="12" r="3.8"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
  moon: '<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z"/>',
  monitor: '<rect x="3.5" y="4.5" width="17" height="11.5" rx="1.5"/><path d="M9 20h6M12 16v4"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4.5 15.5v4h15v-4"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4v4.5H15"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  alert: '<path d="M12 4 21 20H3z"/><path d="M12 10v4.5M12 17.2v.3"/>',
  layers: '<path d="m12 4 8.5 4.5L12 13 3.5 8.5z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5M3.5 16.5 12 21l8.5-4.5"/>',
  print: '<path d="M7 9V3.5h10V9M7 17H4.5V10h15v7H17"/><rect x="7" y="14" width="10" height="6.5"/>',
  logout: '<path d="M14 4.5h4.5v15H14M10 8l-4 4 4 4M6 12h9"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  wifi: '<path d="M4 9.5a12 12 0 0 1 16 0M7 13a7.5 7.5 0 0 1 10 0M10 16.5a3 3 0 0 1 4 0"/><circle cx="12" cy="19.2" r=".6"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 17.5h2"/>',
  reset: '<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4.5 4v4.5H9"/>',
};
export function Icon({ name, size = 18, className = "" }) {
  return <svg className={`ico ${className}`} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{ __html: P[name] || "" }} />;
}

export function StatusPill({ status, label }) {
  const s = STATUS[status] || STATUS.no_evidence;
  return <span className="pill" style={{ "--c": s.color }}><i />{label || s.label}</span>;
}
export function Legend({ compact }) {
  return (
    <div className={`legend ${compact ? "compact" : ""}`}>
      {Object.entries(STATUS).map(([k, s]) => <span key={k}><i style={{ background: s.color }} />{s.label}</span>)}
    </div>
  );
}

// KPI with count-up + highlight when the value changes (B4).
export function Kpi({ label, value, tone, hint }) {
  const [shown, setShown] = useState(value);
  const [pulse, setPulse] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    const from = prev.current, to = value;
    prev.current = value;
    if (from === to) { setShown(to); return; }
    setPulse(true);
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setShown(to); const t = setTimeout(() => setPulse(false), 1200); return () => clearTimeout(t); }
    const t0 = performance.now(), dur = 900;
    let raf;
    const tick = t => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4);
      setShown(Math.round(from + (to - from) * e));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    const off = setTimeout(() => setPulse(false), 1600);
    return () => { cancelAnimationFrame(raf); clearTimeout(off); };
  }, [value]);
  return (
    <div className={`kpi ${tone || ""} ${pulse ? "pulse" : ""}`}>
      <span className="kpi-l">{tone && <i className="kpi-dot" />}{label}</span>
      <span className="kpi-v"><small>QAR</small>{num(shown)}</span>
      {hint && <span className="kpi-h">{hint}</span>}
    </div>
  );
}

export function Loading({ label = "Loading" }) {
  return <div className="state"><span className="spinner" aria-hidden="true" /><span>{label}…</span></div>;
}
export function ErrorState({ message, onRetry }) {
  return (
    <div className="state error" role="alert">
      <Icon name="alert" />
      <div><b>Something went wrong</b><p>{message}</p></div>
      {onRetry && <button className="btn sm" onClick={onRetry}><Icon name="refresh" size={16} />Try again</button>}
    </div>
  );
}
