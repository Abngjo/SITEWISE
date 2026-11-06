import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api/client.js";

const Ctx = createContext(null);
export const useStore = () => useContext(Ctx);

export function StoreProvider({ children }) {
  const [project, setProject] = useState(null);
  const [audit, setAudit] = useState(null);
  const [modelStatus, setModelStatus] = useState({});
  const [elements, setElements] = useState([]);
  const [boq, setBoq] = useState({});
  const [schedule, setSchedule] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [health, setHealth] = useState("checking");
  const [error, setError] = useState(null);
  const [event, setEvent] = useState(null); // drives the dynamic island + highlights
  const [flash, setFlash] = useState({});   // {elementId: status} recently changed, for the 3D flash
  const flashTimer = useRef();
  const knownEvidence = useRef(null);

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const [p, a, m, e, b, s, ev] = await Promise.all([api.project(), api.audit(), api.modelStatus(), api.elements(), api.boq().catch(() => ({})), api.schedule(), api.evidence()]);
      setProject(p); setAudit(a); setModelStatus(m); setElements(e); setBoq(b); setSchedule(s); setEvidence(ev); setHealth("ok");
      knownEvidence.current = new Set(ev.map(x => x.evidence_id));
    } catch (err) {
      setError(err.message); setHealth("offline");
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => {
    const id = setInterval(() => api.health().then(() => setHealth("ok")).catch(() => setHealth("offline")), 15000);
    return () => clearInterval(id);
  }, []);

  // B8: picks up phone uploads. Evidence can change element status, payment and schedule, so refresh those too.
  const refreshEvidence = useCallback(async () => {
    const [ev, m, e, a, s] = await Promise.all([api.evidence(), api.modelStatus(), api.elements(), api.audit(), api.schedule()]);
    const known = knownEvidence.current;
    const fresh = known ? ev.find(x => !known.has(x.evidence_id)) : null;
    knownEvidence.current = new Set(ev.map(x => x.evidence_id));
    if (fresh) setEvent({ kind: "upload", id: fresh.element_id, text: `New photo for ${fresh.element_id || "unassigned"}`,
      sub: fresh.ai.error ? "AI unavailable, review needed" : fresh.ai.escalated ? "Escalated to Qwen2.5-VL" : `SigLIP2 · ${fresh.ai.final_label}`, at: Date.now() });
    setEvidence(ev); setModelStatus(m); setElements(e); setAudit(a); setSchedule(s);
  }, []);

  // B4 demo moment: one review response updates 3D, payment and schedule together.
  const submitReview = useCallback(async (id, decision, opts) => {
    const before = audit?.totals?.supported ?? 0;
    const r = await api.review(id, decision, opts);
    if (r.audit) setAudit(r.audit);
    if (r.modelStatus) setModelStatus(r.modelStatus);
    if (r.schedule) setSchedule(r.schedule);
    if (r.element) setElements(list => list.map(e => (e.element_id === id ? { ...e, ...r.element, review: e.review, evidence_ids: e.evidence_ids } : e)));
    api.elements().then(setElements).catch(() => {}); // pick up the stored review record (reason, reviewer, time)
    const delta = (r.audit?.totals?.supported ?? before) - before;
    const verb = decision === "approve" ? "approved" : decision === "partial" ? "partly approved" : "rejected";
    setEvent({ kind: "review", id, decision, delta, text: `${id} ${verb}`,
      sub: delta ? `Supported ${delta > 0 ? "+" : "−"}QAR ${Math.abs(delta).toLocaleString("en-US")}` : "Supported unchanged", at: Date.now() });
    setFlash({ [id]: r.modelStatus?.[id] });
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash({}), 2400);
    return r;
  }, [audit]);

  const upload = useCallback(async (file, elementId) => {
    const ev = await api.upload(file, elementId);
    await refreshEvidence();
    return ev;
  }, [refreshEvidence]);

  const reset = useCallback(async () => {
    await api.reset();
    await loadAll();
    setEvent({ kind: "reset", text: "Demo state restored", sub: "Seed data and earlier-certificate photos reloaded", at: Date.now() });
  }, [loadAll]);

  // A photo still needs the engineer while its element has no review decision.
  const needsReview = useCallback(ev => { const r = elements.find(el => el.element_id === ev.element_id)?.review; return !r || r.decision === "uncertain"; }, [elements]);
  const pendingReview = evidence.filter(needsReview).length;

  const value = useMemo(() => ({
    project, audit, modelStatus, elements, boq, schedule, evidence, health, error, event, flash, pendingReview,
    needsReview, loadAll, refreshEvidence, submitReview, upload, reset, setSchedule,
  }), [project, audit, modelStatus, elements, boq, schedule, evidence, health, error, event, flash, pendingReview, needsReview, loadAll, refreshEvidence, submitReview, upload, reset]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
