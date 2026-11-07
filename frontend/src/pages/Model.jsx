import { useCallback, useEffect, useMemo, useState } from "react";
import { api, imageUrl } from "../api/client.js";
import { checklistFor } from "../api/checklist.js";
import { useStore } from "../store.jsx";
import Viewer3D from "../components/Viewer3D.jsx";
import { Icon, Legend, StatusPill, fmtDateTime, num, qar } from "../ui.jsx";

export function useResolvedTheme() {
  const [t, setT] = useState(() => document.documentElement.dataset.theme);
  useEffect(() => {
    const mo = new MutationObserver(() => setT(document.documentElement.dataset.theme));
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);
  return t;
}

function useBimElement(id) {
  const [b, setB] = useState(null);
  useEffect(() => {
    let alive = true; setB(null);
    if (id) api.bimElement(id).then(r => alive && setB(r)).catch(() => {});
    return () => { alive = false; };
  }, [id]);
  return b;
}

export function ElementPanel({ el, evidence, status, compact, risk }) {
  const { audit, boq } = useStore();
  const bim = useBimElement(el?.element_id);
  if (!el) return <p className="muted">Click an element in the model to see its details.</p>;
  const evs = evidence.filter(e => e.element_id === el.element_id);
  const r = el.review;
  const item = audit?.items.find(i => i.boq_item === el.boq_item);
  const rate = item?.rate ?? boq[el.boq_item]?.rate;
  return (
    <div className="el-panel">
      <div className="el-head">
        <div><h2 className="mono-id">{el.element_id}</h2><p>{el.name_en}</p><p className="ar sub" lang="ar" dir="rtl">{el.name_ar}</p></div>
        <StatusPill status={status} />
      </div>
      <dl className="kv">
        <dt>IFC element</dt><dd>{bim ? <><b>{bim.ifc_class}</b> · storey {bim.storey}<br /><span className="muted small mono-id">GUID {bim.ifc_guid}</span></> : <span className="muted">—</span>}</dd>
        <dt>Floor / zone</dt><dd>{el.level} ({el.level === "L1" ? "ground floor" : "first floor"}) · zone {el.zone}</dd>
        <dt>Quantity</dt><dd className="num">{num(el.quantity)} {el.unit}</dd>
        <dt>BOQ item</dt><dd>{el.boq_item}{rate != null && <> · QAR {num(rate)} / {el.unit}</>}{item && <><br /><span className="muted">{item.description_en}</span></>}</dd>
        <dt>BOQ item value</dt><dd className="num">{item ? <>claimed {qar(item.claimed_value)} · supported {qar(item.supported_value)}</> : "—"}</dd>
        {risk && <><dt>At risk (this certificate)</dt><dd className="num">{risk.at_risk > 0
          ? <b style={{ color: "var(--neg)" }}>{qar(risk.at_risk)}</b> : <span>{qar(0)}, claim supported</span>}
          <br /><span className="muted small">claimed value {qar(risk.claimed_value)}; share of {risk.boq_item_id} discrepancy</span></dd></>}
        <dt>Task</dt><dd>{el.task_id} · {el.calendar}</dd>
        <dt>Review</dt><dd>{r ? <><b className="cap">{r.decision}</b>{r.quantity != null && ` · ${num(r.quantity)} ${el.unit}`}<br /><span className="muted">{r.reason || "No reason given"} · {r.reviewer}, {fmtDateTime(r.at)}</span></> : <span className="muted">Not reviewed</span>}</dd>
      </dl>
      {!compact && (
        <div>
          <h3 className="h-sm">Evidence</h3>
          {evs.length ? (
            <div className="thumbs">{evs.map(e => <a key={e.evidence_id} href="#evidence" className="thumb"><img src={imageUrl(e.evidence_id)} alt={`${e.evidence_id} for ${el.element_id}`} loading="lazy" /><span>{e.evidence_id}</span></a>)}</div>
          ) : <p className="muted small">No photo submitted.</p>}
        </div>
      )}
    </div>
  );
}

function BimStrip() {
  const [sum, setSum] = useState(null);
  const [imp, setImp] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { api.bimSummary().then(setSum).catch(e => setErr(e.message)); }, []);
  const onImport = async e => {
    const f = e.target.files?.[0]; if (!f) return;
    setBusy(true); setErr(""); setImp(null);
    try { setImp(await api.bimImport(f)); } catch (x) { setErr(x.message); } finally { setBusy(false); e.target.value = ""; }
  };
  const label = c => ({ IfcWall: "walls", IfcSlab: "slabs", IfcDoor: "doors", IfcCovering: "ceilings" }[c] || c);
  return (
    <section className="card" style={{ marginBottom: 16 }}>
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 className="h-sm" style={{ margin: 0 }}>BIM model (IFC)</h2>
          {sum && !sum.error ? (
            <p style={{ margin: "4px 0 0" }}>
              <b>{sum.schema}</b> · {sum.storeys.length} storeys · <b>{sum.total_elements}</b> elements ·{" "}
              <b>{sum.mapped_elements}</b> Package B elements linked to BOQ prices and schedule tasks
              {sum.context_elements ? <> · {sum.context_elements} context elements (other packages)</> : null}
              <span className="muted small"> · parsed live with IfcOpenShell</span>
            </p>
          ) : <p className="muted small" style={{ margin: "4px 0 0" }}>{err || sum?.error || "Reading IFC…"}</p>}
          {sum?.element_counts && (
            <div className="row" style={{ gap: 6, marginTop: 8, flexWrap: "wrap" }}>
              {Object.entries(sum.element_counts).map(([c, n]) => <span key={c} className="tag">{n} {label(c)}</span>)}
            </div>
          )}
        </div>
        <label className="btn">
          <Icon name="upload" size={16} />{busy ? "Reading IFC…" : "Import IFC"}
          <input type="file" accept=".ifc" onChange={onImport} style={{ display: "none" }} />
        </label>
      </div>
      {imp && (
        <p className="small" style={{ margin: "10px 0 0" }}>
          Imported <b>{imp.project || "IFC"}</b> ({imp.schema}): {imp.total_elements} elements found, {imp.mapped_elements} matched to SITEWISE records
          {imp.unmapped_ifc_elements?.length ? `, ${imp.unmapped_ifc_elements.length} need BOQ mapping` : ""}
          {imp.sitewise_records_missing_in_ifc?.length ? `, ${imp.sitewise_records_missing_in_ifc.length} records missing from the model` : ""}.
        </p>
      )}
    </section>
  );
}

const TIME_NOTE = { in_app_capture: "SITEWISE camera", exif: "photo EXIF", manual: "entered manually", missing: "no capture time, upload time shown" };

// Money-at-risk ramp: amber -> red by share of the largest single exposure.
const heat = k => {
  const a = [241, 196, 15], b = [231, 76, 60], c = [146, 20, 12];
  const [p, q, t] = k < 0.5 ? [a, b, k * 2] : [b, c, (k - 0.5) * 2];
  return "#" + p.map((v, i) => Math.round(v + (q[i] - v) * t).toString(16).padStart(2, "0")).join("");
};

export default function Model() {
  const { modelStatus, elements, evidence, flash, openEvidence } = useStore();
  const [sel, setSel] = useState("D-103");
  const [explode, setExplode] = useState(false);
  const [hideL2, setHideL2] = useState(false);
  const [view, setView] = useState("verified"); // verified | claim | risk
  const [xray, setXray] = useState(false);
  const [rooms, setRooms] = useState("en"); // off | en | ar
  const [overlay, setOverlay] = useState(null);
  useEffect(() => { api.overlay().then(setOverlay).catch(() => {}); }, [modelStatus]);
  const [claim, setClaim] = useState({});
  useEffect(() => { api.claimView().then(setClaim).catch(() => {}); }, [modelStatus]);
  const theme = useResolvedTheme();
  // "Contractor's claim": everything claimed or already certified shows as done (green).
  const claimStatus = Object.fromEntries(Object.entries(claim).map(([id, c]) => [id, c === "not_claimed" ? "no_evidence" : "supported"]));
  // Replay: animate certificate by certificate (IPC-01 ... claim ... verified now).
  const [frames, setFrames] = useState([]);
  const [fi, setFi] = useState(-1); // -1 = not replaying
  const [playing, setPlaying] = useState(false);
  const startReplay = async () => {
    const fr = await api.timeline().catch(() => []);
    if (!fr.length) return;
    setFrames(fr); setFi(0); setPlaying(true);
  };
  useEffect(() => {
    if (!playing || fi < 0) return;
    if (fi >= frames.length - 1) { setPlaying(false); return; }
    const t = setTimeout(() => setFi(i => i + 1), 1600);
    return () => clearTimeout(t);
  }, [playing, fi, frames.length]);
  const risk = overlay?.elements || {};
  const riskStatus = Object.fromEntries(elements.map(e => {
    const r = risk[e.element_id];
    if (!r) return [e.element_id, "no_evidence"];
    if (!r.at_risk) return [e.element_id, "supported"];
    return [e.element_id, heat(overlay.max_at_risk ? r.at_risk / overlay.max_at_risk : 1)];
  }));
  const riskiest = Object.entries(risk).sort((a, b) => b[1].at_risk - a[1].at_risk)[0]?.[0];
  const pins = evidence.reduce((a, e) => (e.element_id ? ((a[e.element_id] = (a[e.element_id] || 0) + 1), a) : a), {});
  // Photo card data per pinned element: the newest photo (evidence is already sorted newest first).
  const photos = useMemo(() => {
    const out = {};
    for (const e of evidence) {
      if (!e.element_id || out[e.element_id]) continue;
      const type = elements.find(x => x.element_id === e.element_id)?.type;
      out[e.element_id] = {
        evidence_id: e.evidence_id, count: pins[e.element_id],
        label: e.ai.error ? "AI unavailable" : e.ai.final_label, score: e.ai.error ? 0 : e.ai.top_score,
        escalatedTo: e.ai.escalated ? e.ai.vlm_name || "VLM" : null,
        takenAt: fmtDateTime(e.captured_at || e.uploaded_at),
        timeNote: TIME_NOTE[e.time_source] || "",
        checklist: checklistFor(e, type),
      };
    }
    return out;
  }, [evidence, elements]); // eslint-disable-line react-hooks/exhaustive-deps
  const replaying = fi >= 0 && frames[fi];
  const shown = replaying ? frames[fi].status : view === "claim" ? claimStatus : view === "risk" ? riskStatus : modelStatus;
  const onSelect = useCallback(id => setSel(id), []);
  const el = elements.find(e => e.element_id === sel);
  const counts = Object.values(modelStatus).reduce((a, s) => ((a[s] = (a[s] || 0) + 1), a), {});

  return (
    <>
      <div className="page-head">
        <div><h1>BIM model</h1><p className="muted">{elements.length} Package B elements coloured by evidence status, inside the full IFC building. Click an element to fly to it; blue pins are site photos.</p></div>
        <div className="toggles">
          <div className="seg" role="group" aria-label="Model view">
            <button aria-pressed={view === "claim"} onClick={() => setView("claim")}>Contractor's claim</button>
            <button aria-pressed={view === "verified"} onClick={() => setView("verified")}>Verified by evidence</button>
            <button aria-pressed={view === "risk"} onClick={() => setView("risk")}>Money at risk</button>
          </div>
          <button className={`btn ${replaying ? "on" : ""}`} onClick={replaying && !playing ? () => setFi(-1) : startReplay} disabled={playing}>
            <Icon name="refresh" size={16} />{playing ? "Replaying…" : replaying ? "Exit replay" : "Replay certificates"}
          </button>
          <a className="btn" href="/api/bim/export" download><Icon name="print" size={16} />Export as-verified IFC</a>
          <button className={`btn ${explode ? "on" : ""}`} aria-pressed={explode} onClick={() => setExplode(v => !v)}><Icon name="layers" size={16} />Explode floors</button>
          <button className={`btn ${hideL2 ? "on" : ""}`} aria-pressed={hideL2} onClick={() => setHideL2(v => !v)}>{hideL2 ? "Show first floor" : "Hide first floor"}</button>
          <button className={`btn ${xray ? "on" : ""}`} aria-pressed={xray} onClick={() => setXray(v => !v)} title="Ghost the building, keep doors and the selection solid">X-ray</button>
          <div className="seg" role="group" aria-label="Room labels">
            {[["off", "No labels"], ["en", "Rooms"], ["ar", "الغرف"]].map(([k, l]) =>
              <button key={k} aria-pressed={rooms === k} onClick={() => setRooms(k)}>{l}</button>)}
          </div>
        </div>
      </div>
      <BimStrip />
      <div className="model-layout">
        <section className="card flush viewer-card">
          <Viewer3D status={shown} selected={sel} onSelect={onSelect} flash={flash} explode={explode} hideL2={hideL2} theme={theme}
            xray={xray} labels={rooms !== "off"} lang={rooms === "ar" ? "ar" : "en"} pins={pins}
            photos={photos} onOpenEvidence={openEvidence} />
          {replaying && (
            <div className="viewer-legend" style={{ flexDirection: "column", alignItems: "stretch", gap: 6 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b>{frames[fi].label}</b><span className="muted small">{frames[fi].caption}</span>
              </div>
              <input type="range" min={0} max={frames.length - 1} value={fi} aria-label="Certificate"
                onChange={e => { setPlaying(false); setFi(Number(e.target.value)); }} />
              <div className="row small muted" style={{ justifyContent: "space-between" }}>
                {frames.map((f, i) => <span key={f.key} style={{ fontWeight: i === fi ? 700 : 400 }}>{f.key.replace("-claim", " claim").replace("verified-now", "Now")}</span>)}
              </div>
            </div>
          )}
          <div className="viewer-legend">
            {!replaying && view === "claim" ? (
              <div className="legend"><span><i style={{ background: "#2ECC71" }} />Claimed or certified as done</span><span><i style={{ background: "#9AA5AE" }} />Not claimed</span></div>
            ) : !replaying && view === "risk" ? (
              <div className="legend" style={{ alignItems: "center" }}>
                <span><i style={{ background: "#2ECC71" }} />Claimed, fully supported</span>
                <span><i style={{ background: "#9AA5AE" }} />Not claimed</span>
                <span className="heat-bar"><em>QAR 0</em><b style={{ background: `linear-gradient(90deg, ${heat(0)}, ${heat(0.5)}, ${heat(1)})` }} /><em>{qar(overlay?.max_at_risk || 0)}</em></span>
                {riskiest && <button className="btn sm" onClick={() => setSel(riskiest)}>Fly to largest exposure</button>}
              </div>
            ) : <Legend />}
            <span className="muted small">{view === "risk" && !replaying
              ? `${qar(overlay?.total_at_risk || 0)} claimed without supporting evidence, across ${Object.values(risk).filter(r => r.at_risk > 0).length} elements (matches the payment audit)`
              : view === "claim"
              ? `What the contractor says is built: ${Object.values(claim).filter(c => c !== "not_claimed").length} of ${Object.keys(claim).length} elements`
              : Object.entries(counts).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(" · ")}</span>
          </div>
        </section>
        <section className="card"><ElementPanel el={el} evidence={evidence} status={modelStatus[sel]} risk={risk[sel]} /></section>
      </div>
    </>
  );
}
