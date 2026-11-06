import { useEffect, useRef, useState } from "react";
import { useStore } from "../store.jsx";
import { Icon, num } from "../ui.jsx";

// Doha local time and Qatar's summer midday rule (1 Jun–15 Sep, 10:00–15:30).
function dohaNow() {
  const d = new Date();
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Qatar", hour: "2-digit", minute: "2-digit", month: "numeric", day: "numeric", hour12: false })
    .formatToParts(d).map(p => [p.type, p.value]));
  const h = +parts.hour % 24, m = +parts.minute, md = +parts.month * 100 + +parts.day;
  const inSeason = md >= 601 && md <= 915, mins = h * 60 + m, inHours = mins >= 600 && mins <= 930;
  return {
    time: d.toLocaleTimeString("en-GB", { timeZone: "Asia/Qatar", hour: "2-digit", minute: "2-digit" }),
    date: d.toLocaleDateString("en-GB", { timeZone: "Asia/Qatar", weekday: "short", day: "numeric", month: "short" }),
    heat: inSeason && inHours ? { level: "active", text: "Outdoor midday work restricted until 15:30" }
      : inSeason ? { level: "season", text: "Summer rule in force: 10:00–15:30 restricted" }
      : { level: "off", text: "Summer midday rule starts 1 Jun" },
  };
}

export default function DynamicIsland() {
  const { project, audit, health, event, pendingReview } = useStore();
  const [now, setNow] = useState(dohaNow);
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(null);
  const timer = useRef();
  const ref = useRef();

  useEffect(() => { const id = setInterval(() => setNow(dohaNow()), 15000); return () => clearInterval(id); }, []);
  useEffect(() => {
    if (!event) return;
    setLive(event);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setLive(null), 4200);
    return () => clearTimeout(timer.current);
  }, [event]);
  useEffect(() => {
    if (!open) return;
    const close = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const esc = e => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const t = audit?.totals;
  const open_reviews = pendingReview;
  const mode = open ? "open" : live ? "live" : "idle";
  const tone = live?.kind === "review" ? (live.decision === "reject" ? "bad" : "good") : live ? "info" : "";

  return (
    <div className="island-wrap" ref={ref}>
      <button className={`island ${mode} ${tone}`} onClick={() => setOpen(o => !o)} aria-expanded={open} aria-label="Project status">
        {mode === "idle" && (
          <span className="island-row">
            <span className={`island-dot ${health}`} />
            <span className="island-time">{now.time}</span>
            <span className="island-sep" />
            <span>{project?.certificate || "IPC-04"}</span>
            {now.heat.level !== "off" && <Icon name="sun" size={14} className={`island-heat ${now.heat.level}`} />}
          </span>
        )}
        {mode === "live" && (
          <span className="island-row live-row" key={live.at}>
            <span className={`island-badge ${tone}`}><Icon name={live.kind === "review" ? (live.decision === "reject" ? "x" : "check") : live.kind === "upload" ? "upload" : "reset"} size={14} /></span>
            <span className="island-live-text"><b>{live.text}</b><span>{live.sub}</span></span>
          </span>
        )}
        {mode === "open" && (
          <span className="island-panel">
            <span className="ip-head">
              <span><b className="ip-time">{now.time}</b><span className="ip-date">{now.date} · Doha</span></span>
              <span className={`ip-health ${health}`}><span className={`island-dot ${health}`} />{health === "ok" ? "Backend online" : health === "offline" ? "Backend offline" : "Checking"}</span>
            </span>
            <span className="ip-grid">
              <span><small>Claimed</small><b>{t ? num(t.claimed) : "—"}</b></span>
              <span><small>Supported</small><b className="g">{t ? num(t.supported) : "—"}</b></span>
              <span><small>Discrepancy</small><b className="r">{t ? num(t.discrepancy) : "—"}</b></span>
            </span>
            <span className="ip-line"><Icon name="sun" size={15} />{now.heat.text}</span>
            <span className="ip-line"><Icon name="evidence" size={15} />{open_reviews} photo{open_reviews === 1 ? "" : "s"} awaiting engineer review</span>
            <span className="ip-line muted"><Icon name="clock" size={15} />{project ? `${project.certificate} · ${project.contractor}` : "Loading project"}</span>
          </span>
        )}
      </button>
    </div>
  );
}
