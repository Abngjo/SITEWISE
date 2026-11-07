import { useCallback, useEffect, useState } from "react";
import { api, imageUrl } from "../api/client.js";
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

export function ElementPanel({ el, evidence, status, compact }) {
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
              <b>{sum.mapped_elements}/{sum.total_elements}</b> linked to BOQ prices and schedule tasks
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

export default function Model() {
  const { modelStatus, elements, evidence, flash } = useStore();
  const [sel, setSel] = useState("D-103");
  const [explode, setExplode] = useState(false);
  const [hideL2, setHideL2] = useState(false);
  const [view, setView] = useState("verified"); // verified | claim
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
  const replaying = fi >= 0 && frames[fi];
  const shown = replaying ? frames[fi].status : view === "claim" ? claimStatus : modelStatus;
  const onSelect = useCallback(id => setSel(id), []);
  const el = elements.find(e => e.element_id === sel);
  const counts = Object.values(modelStatus).reduce((a, s) => ((a[s] = (a[s] || 0) + 1), a), {});

  return (
    <>
      <div className="page-head">
        <div><h1>BIM model</h1><p className="muted">{elements.length} IFC elements coloured by evidence status. Drag to orbit, scroll to zoom, click an element.</p></div>
        <div className="toggles">
          <div className="seg" role="group" aria-label="Model view">
            <button aria-pressed={view === "claim"} onClick={() => setView("claim")}>Contractor's claim</button>
            <button aria-pressed={view === "verified"} onClick={() => setView("verified")}>Verified by evidence</button>
          </div>
          <button className={`btn ${replaying ? "on" : ""}`} onClick={replaying && !playing ? () => setFi(-1) : startReplay} disabled={playing}>
            <Icon name="refresh" size={16} />{playing ? "Replaying…" : replaying ? "Exit replay" : "Replay certificates"}
          </button>
          <a className="btn" href="/api/bim/export" download><Icon name="print" size={16} />Export as-verified IFC</a>
          <button className={`btn ${explode ? "on" : ""}`} aria-pressed={explode} onClick={() => setExplode(v => !v)}><Icon name="layers" size={16} />Explode floors</button>
          <button className={`btn ${hideL2 ? "on" : ""}`} aria-pressed={hideL2} onClick={() => setHideL2(v => !v)}>{hideL2 ? "Show first floor" : "Hide first floor"}</button>
        </div>
      </div>
      <BimStrip />
      <div className="model-layout">
        <section className="card flush viewer-card">
          <Viewer3D status={shown} selected={sel} onSelect={onSelect} flash={flash} explode={explode} hideL2={hideL2} theme={theme} />
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
            ) : <Legend />}
            <span className="muted small">{view === "claim"
              ? `What the contractor says is built: ${Object.values(claim).filter(c => c !== "not_claimed").length} of ${Object.keys(claim).length} elements`
              : Object.entries(counts).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(" · ")}</span>
          </div>
        </section>
        <section className="card"><ElementPanel el={el} evidence={evidence} status={modelStatus[sel]} /></section>
      </div>
    </>
  );
}
