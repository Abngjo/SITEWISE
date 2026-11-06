import { useCallback, useEffect, useState } from "react";
import { imageUrl } from "../api/client.js";
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

export function ElementPanel({ el, evidence, status, compact }) {
  const { audit, boq } = useStore();
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
        <dt>Floor / zone</dt><dd>{el.level === "L1" ? "Ground floor" : "First floor"} · {el.zone}</dd>
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

export default function Model() {
  const { modelStatus, elements, evidence, flash } = useStore();
  const [sel, setSel] = useState("D-103");
  const [explode, setExplode] = useState(false);
  const [hideL2, setHideL2] = useState(false);
  const theme = useResolvedTheme();
  const onSelect = useCallback(id => setSel(id), []);
  const el = elements.find(e => e.element_id === sel);
  const counts = Object.values(modelStatus).reduce((a, s) => ((a[s] = (a[s] || 0) + 1), a), {});

  return (
    <>
      <div className="page-head">
        <div><h1>3D model</h1><p className="muted">{elements.length} elements coloured by evidence status. Drag to orbit, scroll to zoom, click an element.</p></div>
        <div className="toggles">
          <button className={`btn ${explode ? "on" : ""}`} aria-pressed={explode} onClick={() => setExplode(v => !v)}><Icon name="layers" size={16} />Explode floors</button>
          <button className={`btn ${hideL2 ? "on" : ""}`} aria-pressed={hideL2} onClick={() => setHideL2(v => !v)}>{hideL2 ? "Show first floor" : "Hide first floor"}</button>
        </div>
      </div>
      <div className="model-layout">
        <section className="card flush viewer-card">
          <Viewer3D status={modelStatus} selected={sel} onSelect={onSelect} flash={flash} explode={explode} hideL2={hideL2} theme={theme} />
          <div className="viewer-legend"><Legend /><span className="muted small">{Object.entries(counts).map(([k, n]) => `${n} ${k.replace("_", " ")}`).join(" · ")}</span></div>
        </section>
        <section className="card"><ElementPanel el={el} evidence={evidence} status={modelStatus[sel]} /></section>
      </div>
    </>
  );
}
