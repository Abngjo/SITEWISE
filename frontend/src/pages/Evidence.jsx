import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { imageUrl } from "../api/client.js";
import { EXPECTED_LABEL, FLAG_LABEL } from "../api/adapters.js";
import { MARK, STATE_LABEL, checklistFor } from "../api/checklist.js";
import { useStore } from "../store.jsx";
import Viewer3D from "../components/Viewer3D.jsx";
import { useResolvedTheme } from "./Model.jsx";
import { Icon, Kpi, StatusPill, fmtDate, fmtDateTime, num } from "../ui.jsx";

const TIME_SOURCE = {
  in_app_capture: ["Captured in the SITEWISE camera page", false],
  exif: ["From photo EXIF", false],
  manual: ["Entered manually", true],
  missing: ["No capture time: upload time shown", true],
};
// Per-component checklist, e.g. "Frame ✓ · Leaf ✗ · Handle ?". Preview until Person A's field ships (see api/checklist.js).
export function Checklist({ ev, type, compact }) {
  const { items, source } = checklistFor(ev, type);
  return (
    <div className={`checklist ${compact ? "compact" : ""}`}>
      {!compact && <span className="lbl">Component checklist</span>}
      <div className="ck-row" role="list" aria-label="Component checklist">
        {items.map((i, n) => (
          <span key={i.name} role="listitem" className={`ck ck-${i.state}`} title={`${i.name}: ${STATE_LABEL[i.state]}`}>
            {n > 0 && <i className="ck-sep" aria-hidden="true">·</i>}{i.name} <b aria-hidden="true">{MARK[i.state]}</b><span className="sr">{STATE_LABEL[i.state]}</span>
          </span>
        ))}
        {source === "preview" && <span className="tag" title="Derived from the VLM's completion verdict until the per-component checklist ships">Preview</span>}
      </div>
    </div>
  );
}

const shownTime = e => (e.captured_at ? fmtDateTime(e.captured_at) : `uploaded ${fmtDateTime(e.uploaded_at)}`);

function Upload({ elements, defaultElement, onUploaded }) {
  const { upload } = useStore();
  const [el, setEl] = useState(defaultElement || "D-103");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [drag, setDrag] = useState(false);
  const input = useRef();
  useEffect(() => { if (defaultElement) setEl(defaultElement); }, [defaultElement]);
  const go = async () => {
    if (!file) return setMsg({ bad: true, text: "Choose a photo first." });
    setBusy(true); setMsg(null);
    try {
      const ev = await upload(file, el);
      setMsg({ text: ev.ai.error
        ? `${ev.evidence_id} saved. The AI was unavailable, so the line needs engineer review.`
        : `${ev.evidence_id} analysed: ${ev.ai.final_label} ${(ev.ai.top_score * 100).toFixed(0)}%${ev.ai.escalated ? ", escalated to " + (ev.ai.vlm_name || "the VLM") : ""}${ev.duplicates.length ? ". Possible reuse found." : "."}` });
      setFile(null); onUploaded(ev);
    } catch (e) {
      setMsg({ bad: true, text: `${e.message}. The photo was not saved; try again.` });
    } finally { setBusy(false); }
  };
  return (
    <section className="card upload">
      <div className="card-head"><h2>Upload evidence</h2><span className="muted small">Phones: use the QR code on the Payment page, which records the capture time.</span></div>
      <div className={`drop ${drag ? "over" : ""}`} onDragOver={e => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files[0] || null); }} onClick={() => input.current.click()} role="button" tabIndex={0}
        onKeyDown={e => (e.key === "Enter" || e.key === " ") && input.current.click()}>
        <Icon name="upload" size={22} />
        <span>{file ? file.name : "Drop a site photo, or click to choose"}</span>
        <input ref={input} type="file" accept="image/*" hidden onChange={e => setFile(e.target.files[0] || null)} />
      </div>
      <div className="row">
        <label className="field grow"><span>Element</span>
          <select className="input" value={el} onChange={e => setEl(e.target.value)}>
            {elements.map(e => <option key={e.element_id} value={e.element_id}>{e.element_id} · {e.name_en}</option>)}
          </select>
        </label>
        <button className="btn primary" onClick={go} disabled={busy} aria-busy={busy}>{busy ? <><span className="spinner sm" />Analysing…</> : "Upload and analyse"}</button>
      </div>
      {msg && <p className={`msg ${msg.bad ? "bad" : "good"}`} role={msg.bad ? "alert" : "status"}>{msg.text}</p>}
    </section>
  );
}

function ReviewControls({ el, evidenceId }) {
  const { submitReview } = useStore();
  const [mode, setMode] = useState(null);
  const [qty, setQty] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { setMode(null); setQty(""); setReason(""); setErr(""); }, [el?.element_id]);
  if (!el) return null;
  const send = async decision => {
    if (decision === "partial" && !(Number(qty) > 0 && Number(qty) <= el.quantity)) { setMode("partial"); return setErr(`Enter a supported quantity between 0 and ${num(el.quantity)} ${el.unit}.`); }
    if (decision === "reject" && !reason.trim()) { setMode("reject"); return setErr("Give a reason so the contractor knows what to fix."); }
    setBusy(decision); setErr("");
    try { await submitReview(el.element_id, decision, { quantity: qty, reason: reason.trim(), reviewer: "Eng. Noor Al-Kuwari", evidence_id: evidenceId }); setMode(null); }
    catch (e) { setErr(e.message); }
    finally { setBusy(false); }
  };
  const r = el.review;
  return (
    <div className="review">
      <h3 className="h-sm">Engineer decision for {el.element_id}</h3>
      <p className="muted small">Element quantity {num(el.quantity)} {el.unit} · {el.boq_item}. Only this decision changes payment.
        {r && <> Current decision: <b className="ink cap">{r.decision}</b>{r.quantity != null && ` (${num(r.quantity)} ${el.unit})`} by {r.reviewer}.</>}</p>
      <label className="field"><span>Reason {mode === "reject" ? "(required)" : "(optional)"}</span>
        <textarea className="input" rows={2} value={reason} onChange={e => setReason(e.target.value)} placeholder="e.g. Leaf hung, ironmongery to follow" />
      </label>
      {mode === "partial" && (
        <label className="field"><span>Supported quantity ({el.unit}, max {num(el.quantity)})</span>
          <input className="input" type="number" min="0" step="any" max={el.quantity} value={qty} onChange={e => setQty(e.target.value)} autoFocus />
        </label>
      )}
      {err && <p className="msg bad" role="alert">{err}</p>}
      <div className="actions">
        <button className="btn approve" disabled={!!busy} onClick={() => send("approve")}>{busy === "approve" ? <span className="spinner sm" /> : <Icon name="check" size={16} />}Approve</button>
        <button className="btn" disabled={!!busy} onClick={() => (mode === "partial" ? send("partial") : setMode("partial"))}>{busy === "partial" ? <span className="spinner sm" /> : null}{mode === "partial" ? "Confirm partial" : "Partial"}</button>
        <button className="btn reject" disabled={!!busy} onClick={() => send("reject")}>{busy === "reject" ? <span className="spinner sm" /> : <Icon name="x" size={16} />}Reject</button>
      </div>
    </div>
  );
}

export default function Evidence() {
  const { evidence, elements, modelStatus, audit, schedule, flash, needsReview, lastSync, focusEvidence } = useStore();
  const [filter, setFilter] = useState("all");
  const [sel, setSel] = useState(null); // {kind:"ev"|"el", id}
  const theme = useResolvedTheme();

  // B8: new phone uploads appear without a reload (the store polls every 4 s on every page).
  // A 3D photo card or a toast can ask for a specific photo.
  useEffect(() => {
    if (focusEvidence?.id) { setFilter("all"); setSel({ kind: "ev", id: focusEvidence.id }); }
  }, [focusEvidence]);

  const FILTERS = { all: () => true, review: needsReview, reuse: e => e.duplicates.length > 0, escalated: e => e.ai.escalated };
  const list = useMemo(() => evidence.filter(FILTERS[filter]), [evidence, filter, needsReview]); // eslint-disable-line react-hooks/exhaustive-deps

  // Claimed elements that are not yet supported and have no photo in this certificate: still reviewable.
  const withPhoto = new Set(evidence.map(e => e.element_id));
  const claimedNoPhoto = [...new Set(audit?.items.flatMap(i => i.elements_without_evidence) || [])];
  const openNoPhoto = elements.filter(e => !withPhoto.has(e.element_id) && (claimedNoPhoto.includes(e.element_id) || ["uncertain", "discrepancy"].includes(modelStatus[e.element_id])));

  const fallback = list.find(e => e.element_id === "D-103") || list[0];
  const current = sel?.kind === "ev" ? evidence.find(e => e.evidence_id === sel.id) : null;
  const cur = sel?.kind === "el" ? null : current || fallback || null;
  const elId = sel?.kind === "el" ? sel.id : cur?.element_id || (openNoPhoto.find(e => e.element_id === "D-103") || openNoPhoto[0])?.element_id;
  const el = elements.find(e => e.element_id === elId);
  // Pin the default selection so the panel stays on the same element after a decision moves it out of the open list.
  useEffect(() => {
    if (sel || !elId) return;
    setSel(cur ? { kind: "ev", id: cur.evidence_id } : { kind: "el", id: elId });
  }, [sel, elId, cur]);
  const setSelByElement = useCallback(id => {
    const e = evidence.find(x => x.element_id === id);
    setSel(e ? { kind: "ev", id: e.evidence_id } : { kind: "el", id });
  }, [evidence]);

  return (
    <>
      <div className="page-head">
        <div><h1>Evidence review</h1><p className="muted">Newest first. AI results are observations; your decision is what certifies.</p></div>
        <span className="muted small live-dot">Live · updated {new Date(lastSync).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</span>
      </div>
      <div className="ev-layout">
        <section className="card flush ev-list">
          <div className="seg-filters" role="group" aria-label="Filter evidence">
            {[["all", "All"], ["review", "Needs review"], ["reuse", "Possible reuse"], ["escalated", "Escalated"]].map(([k, l]) => (
              <button key={k} aria-pressed={filter === k} onClick={() => setFilter(k)}>{l} <span>{evidence.filter(FILTERS[k]).length}</span></button>
            ))}
          </div>
          <ul>
            {list.map(e => (
              <li key={e.evidence_id}>
                <button className="ev-row" aria-current={cur?.evidence_id === e.evidence_id && sel?.kind !== "el"} onClick={() => setSel({ kind: "ev", id: e.evidence_id })}>
                  <img src={imageUrl(e.evidence_id)} alt="" loading="lazy" />
                  <span className="ev-meta">
                    <span className="ev-top"><b className="mono">{e.element_id || "Unassigned"}</b><StatusPill status={modelStatus[e.element_id]} /></span>
                    <span className="small muted">{e.evidence_id} · {shownTime(e)}</span>
                    <span className="tags">
                      {e.ai.error ? <span className="tag warn">Review needed</span> : <span className="tag">{e.ai.final_label} {(e.ai.top_score * 100).toFixed(0)}%</span>}
                      {e.ai.escalated && <span className="tag accent">Escalated to VLM</span>}
                      {e.duplicates.length > 0 && <span className="tag warn">Possible reuse</span>}
                      {e.flags.some(f => f.type === "summer_working_hours") && <span className="tag warn"><Icon name="sun" size={12} />Heat hours</span>}
                    </span>
                    {!e.ai.error && <Checklist compact ev={e} type={elements.find(x => x.element_id === e.element_id)?.type} />}
                  </span>
                </button>
              </li>
            ))}
            {!evidence.length && (
              <li className="empty"><b>No photos for this certificate yet.</b><span className="muted small">Upload one below, or scan the QR code on the Payment page with a phone.</span></li>
            )}
            {evidence.length > 0 && !list.length && <li className="empty"><b>No photos match this filter.</b><button className="btn sm" onClick={() => setFilter("all")}>Show all</button></li>}
          </ul>
          {openNoPhoto.length > 0 && (
            <div className="nophoto">
              <b>Claimed, awaiting decision, no photo</b>
              <span className="chips">{openNoPhoto.map(e => (
                <button key={e.element_id} className={`chip chip-btn ${sel?.kind === "el" && sel.id === e.element_id ? "on" : ""}`} onClick={() => setSel({ kind: "el", id: e.element_id })}>{e.element_id}</button>
              ))}</span>
            </div>
          )}
        </section>

        {el ? (
          <section className="card ev-detail" key={cur?.evidence_id || el.element_id}>
            <div className="el-head">
              <div><h2 className="mono-id">{el.element_id} <span className="ev-name">{el.name_en}</span></h2><p className="muted small">{cur ? `${cur.evidence_id} · ` : ""}{el.boq_item} · {el.level === "L1" ? "Level 1" : "Level 2"} · {el.calendar}</p></div>
              <StatusPill status={modelStatus[el.element_id]} />
            </div>

            {cur ? (
              <>
                {cur.duplicates.length > 0 ? (
                  <div className="reuse">
                    <div className="reuse-head"><Icon name="alert" size={18} /><b>Possible reuse, review needed</b><span className="muted small">{cur.duplicates[0].match_type} · score {cur.duplicates[0].similarity}</span></div>
                    <div className="pair">
                      <figure><img src={imageUrl(cur.evidence_id)} alt="New photo" /><figcaption>This claim · {cur.certificate} · {cur.evidence_id}</figcaption></figure>
                      <figure><img src={imageUrl(cur.duplicates[0].evidence_id)} alt="Earlier photo" /><figcaption>Earlier · {cur.duplicates[0].certificate} · {cur.duplicates[0].evidence_id}</figcaption></figure>
                    </div>
                  </div>
                ) : (
                  <figure className="hero-photo"><img src={imageUrl(cur.evidence_id)} alt={`${cur.evidence_id} for ${el.element_id}`} /></figure>
                )}

                <div className="obs">
                  <div>
                    <span className="lbl">AI observation</span>
                    {cur.ai.error ? (
                      <p className="warn-t">AI unavailable. Review needed: {cur.ai.error}</p>
                    ) : (
                      <>
                        <p>Photo likely shows a <b>{cur.ai.final_label}</b>{cur.ai.matches === false && <span className="neg"> but the claim is a {EXPECTED_LABEL[el.type] || el.type}</span>}.</p>
                        <div className="score"><i style={{ width: `${cur.ai.top_score * 100}%` }} /></div>
                        <span className="small muted">Stage 1 top score {(cur.ai.top_score * 100).toFixed(0)}% · {cur.ai.model} · {cur.ai.latency_ms} ms</span>
                      </>
                    )}
                  </div>
                  <div>
                    <span className="lbl">Capture time</span>
                    <p>{cur.captured_at ? fmtDateTime(cur.captured_at) : fmtDateTime(cur.uploaded_at)}</p>
                    <span className={`small ${TIME_SOURCE[cur.time_source]?.[1] ? "warn-t" : "muted"}`}>{TIME_SOURCE[cur.time_source]?.[0] || cur.time_source}</span>
                  </div>
                </div>
                {!cur.ai.error && <Checklist ev={cur} type={el.type} />}
                {cur.ai.escalated && cur.ai.vlm && (
                  <div className="vlm"><span className="tag accent">Escalated to {cur.ai.vlm_name || "VLM"}</span><p>“{cur.ai.vlm.reason}”</p><span className="small muted">{cur.ai.vlm_model || "VLM"} via Hugging Face Inference Providers{cur.ai.completion ? ` · completion: ${String(cur.ai.completion).replace("_", " ")}` : ""}</span></div>
                )}
                {cur.flags.length > 0 && (
                  <ul className="flag-list">{cur.flags.map((f, i) => <li key={i}><span className="tag warn">{f.type === "summer_working_hours" && <Icon name="sun" size={12} />}{FLAG_LABEL[f.type] || f.type}</span>{f.message}</li>)}</ul>
                )}
              </>
            ) : (
              <div className="no-photo-note"><Icon name="evidence" size={20} /><div><b>No photo submitted for {el.element_id} in {audit?.certificate || "this certificate"}.</b><p className="muted small">You can still decide on this line, or upload a photo for it below.</p></div></div>
            )}

            <ReviewControls el={el} evidenceId={cur?.evidence_id} />
            <div className="impact">
              <span className="lbl">Live impact of your decision</span>
              <div className="impact-grid">
                <div className="impact-kpis">
                  <Kpi label="Supported by evidence" value={audit?.totals.supported} tone="good" />
                  <Kpi label="Discrepancy" value={audit?.totals.discrepancy} tone="bad" />
                  {schedule && <p className="small muted">Forecast handover <b className="ink">{fmtDate(schedule.forecast_handover)}</b> · delay {schedule.delay_days} days</p>}
                </div>
                <div className="mini-viewer"><Viewer3D status={modelStatus} selected={el.element_id} onSelect={setSelByElement} flash={flash} explode={false} hideL2={el.level === "L1"} theme={theme} /></div>
              </div>
            </div>
          </section>
        ) : <section className="card"><p className="muted">Select a photo or an element to review.</p></section>}
      </div>
      <Upload elements={elements} defaultElement={el?.element_id} onUploaded={ev => setSel({ kind: "ev", id: ev.evidence_id })} />
    </>
  );
}
