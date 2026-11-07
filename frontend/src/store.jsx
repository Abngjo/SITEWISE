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
  const [toasts, setToasts] = useState([]);
  const [lastSync, setLastSync] = useState(Date.now());
  const [focusEvidence, setFocusEvidence] = useState(null); // {id, at}

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

  const flashFor = useCallback((ids, ms) => {
    setFlash(Object.fromEntries(ids.map(id => [id, true])));
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash({}), ms);
  }, []);
  const pushToast = useCallback(t => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setToasts(list => [...list.slice(-2), { ...t, id }]);
    setTimeout(() => setToasts(list => list.filter(x => x.id !== id)), 6000);
  }, []);
  const dismissToast = useCallback(id => setToasts(list => list.filter(x => x.id !== id)), []);

  // B8: picks up phone uploads. Evidence can change element status, payment and schedule, so refresh those too.
  // A new photo flashes its element in 3D and raises a toast, on whichever page is open.
  const refreshEvidence = useCallback(async ({ announce = true } = {}) => {
    const [ev, m, e, a, s] = await Promise.all([api.evidence(), api.modelStatus(), api.elements(), api.audit(), api.schedule()]);
    const known = knownEvidence.current;
    const fresh = known ? ev.filter(x => !known.has(x.evidence_id)) : [];
    knownEvidence.current = new Set(ev.map(x => x.evidence_id));
    setEvidence(ev); setModelStatus(m); setElements(e); setAudit(a); setSchedule(s); setLastSync(Date.now());
    if (fresh.length && announce) {
      const f = fresh[0];
      const how = f.ai.error ? "AI unavailable, review needed"
        : f.ai.escalated ? `escalated to ${f.ai.vlm_name || "the VLM"}`
        : `${f.ai.final_label} (SigLIP2)`;
      setEvent({ kind: "upload", id: f.element_id, text: `New photo for ${f.element_id || "unassigned"}`, sub: how, at: Date.now() });
      pushToast({ kind: "upload", element_id: f.element_id, evidence_id: f.evidence_id, text: `${f.element_id || "Unassigned"}: new photo, ${how}`, warn: !!f.ai.error });
      flashFor(fresh.map(x => x.element_id).filter(Boolean), 4000);
    }
  }, [pushToast, flashFor]);

  // Cheap poll: only the evidence list. Full refresh happens when something new arrives.
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const ev = await api.evidence();
        setLastSync(Date.now());
        const known = knownEvidence.current;
        if (known && ev.some(x => !known.has(x.evidence_id))) await refreshEvidence();
      } catch { /* offline: the health check reports it */ }
    }, 4000);
    return () => clearInterval(id);
  }, [refreshEvidence]);

  // Open a specific photo on the Evidence page (used by the 3D photo cards and toasts).
  const openEvidence = useCallback(evidenceId => {
    setFocusEvidence({ id: evidenceId, at: Date.now() });
    if (location.hash !== "#evidence") location.hash = "evidence";
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
    flashFor([id], 2400);
    return r;
  }, [audit, flashFor]);

  // Desktop upload: the uploader already sees the result inline, so mark it known and skip the toast.
  const upload = useCallback(async (file, elementId) => {
    const ev = await api.upload(file, elementId);
    knownEvidence.current?.add(ev.evidence_id);
    await refreshEvidence({ announce: false });
    flashFor([elementId], 2400);
    return ev;
  }, [refreshEvidence, flashFor]);

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
    toasts, dismissToast, lastSync, focusEvidence, openEvidence,
  }), [project, audit, modelStatus, elements, boq, schedule, evidence, health, error, event, flash, pendingReview, needsReview, loadAll, refreshEvidence, submitReview, upload, reset,
    toasts, dismissToast, lastSync, focusEvidence, openEvidence]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
