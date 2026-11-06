// Thin fetch layer over contracts/api.md. All response-shape handling lives in adapters.js.
import * as A from "./adapters.js";

async function req(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new Error("Can't reach the backend on port 7860. Start it with: SITEWISE_DISABLE_MODELS=1 uvicorn backend.main:app --reload --port 7860");
  }
  const text = await res.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const d = body?.detail;
    throw new Error(Array.isArray(d) ? d.map(x => x.msg).join("; ") : d || `${res.status} ${res.statusText}`);
  }
  return body;
}

export const api = {
  health: () => req("/api/health"),
  meta: () => req("/api/meta").catch(() => null), // optional; QR falls back to this page's origin
  project: () => req("/api/project").then(A.project),
  elements: () => req("/api/elements").then(A.elements),
  boq: () => req("/api/boq").then(A.boq),
  audit: () => req("/api/payments/audit").then(A.audit),
  modelStatus: () => req("/api/model/status").then(A.modelStatus),
  evidence: () => req("/api/evidence").then(A.evidenceList),
  schedule: (task, days) => req(`/api/schedule/forecast${task ? `?delay_task=${encodeURIComponent(task)}&delay_days=${days}` : ""}`).then(A.schedule),
  report: lang => req(`/api/report?lang=${lang}`).then(A.report),
  safety: () => req("/api/safety").then(A.safety),
  aiCosts: () => req("/api/ai/costs").then(A.costs),
  reset: () => req("/api/admin/reset", { method: "POST" }),
  upload: (file, elementId) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("element_id", elementId);
    fd.append("uploader", "engineer-desktop"); // capture time comes from EXIF on desktop uploads
    return req("/api/evidence", { method: "POST", body: fd }).then(A.evidence);
  },
  review: (id, decision, opts) =>
    req(`/api/elements/${encodeURIComponent(id)}/review`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(A.reviewRequest(decision, opts)),
    }).then(A.reviewResponse),
};

export const imageUrl = id => `/api/evidence/${encodeURIComponent(id)}/image`;
