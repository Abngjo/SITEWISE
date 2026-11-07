// Normalise backend responses (contracts/api.md + contracts/schemas.json) into the shapes the screens use.
// If a contract field changes, fix it here and the screens keep working.

export const STATUS = {
  supported: { color: "#2ECC71", label: "Supported" },
  uncertain: { color: "#F1C40F", label: "Uncertain" },
  discrepancy: { color: "#E74C3C", label: "Discrepancy" },
  no_evidence: { color: "#9AA5AE", label: "No evidence" },
};
// Element statuses are the four legend values. BOQ item statuses add two more; map them onto legend colours.
const ITEM_STATUS = {
  supported: ["supported", "Supported"],
  partially_supported: ["uncertain", "Partially supported"],
  insufficient_evidence: ["no_evidence", "Insufficient evidence"],
  discrepancy: ["discrepancy", "Discrepancy"],
  uncertain: ["uncertain", "Uncertain"],
  no_evidence: ["no_evidence", "No evidence"],
};
export const normStatus = s => {
  const k = String(s || "").toLowerCase();
  if (k in STATUS) return k;
  return ITEM_STATUS[k]?.[0] || "no_evidence";
};
const statusLabel = s => ITEM_STATUS[String(s || "").toLowerCase()]?.[1] || STATUS[normStatus(s)].label;
const n = v => (v == null || v === "" ? null : Number(v));

// Visual label the AI should see for each BIM element type (schemas.json visual_labels).
export const EXPECTED_LABEL = { door: "door", wall: "wall", ceiling: "ceiling", slab: "other" };

export const project = p => ({
  ...p,
  name_en: p.name || p.name_en,
  certificate: p.current_certificate || p.certificate || "IPC-04",
  as_of: p.as_of_date,
});

const review = r => (r ? {
  decision: r.decision,
  quantity: n(r.supported_qty),
  reason: r.reason,
  reviewer: r.reviewer,
  at: r.timestamp,
  evidence_id: r.evidence_id,
} : null);

export const element = e => ({
  ...e,
  name_en: e.name || e.name_en,
  level: e.floor || e.level,
  quantity: n(e.quantity),
  boq_item: e.boq_item_id || e.boq_item,
  outdoor: e.calendar === "outdoor",
  status: normStatus(e.status),
  review: review(e.review),
  evidence_ids: e.evidence_ids || [],
});
export const elements = list => (Array.isArray(list) ? list : list.elements || []).map(element);

export const boq = list => Object.fromEntries((list || []).map(b => [b.item_id, { ...b, rate: n(b.contract_rate) }]));

export const audit = a => {
  const t = a.totals || {};
  return {
    ...a,
    certificate: a.certificate_no,
    totals: {
      claimed: t.claimed_this_period ?? 0,
      supported: t.supported_this_period ?? 0,
      discrepancy: t.discrepancy ?? 0,
      noEvidence: t.claimed_value_with_no_evidence ?? 0,
      retention: t.retention ?? null,
      net: t.recommended_for_review_net ?? null,
    },
    items: (a.items || []).map(i => ({
      boq_item: i.boq_item_id,
      description_en: i.description,
      description_ar: i.description_ar,
      unit: i.unit,
      rate: i.rate,
      previous_certified_qty: i.previous_certified_qty,
      claimed_cumulative_qty: i.claimed_qty_cumulative,
      supported_cumulative_qty: i.supported_qty_cumulative,
      claimed_value: i.claimed_value_this_period,
      supported_value: i.supported_value_this_period,
      discrepancy: i.discrepancy,
      status: normStatus(i.status),
      status_label: statusLabel(i.status),
      elements_without_evidence: i.claimed_without_evidence || [],
    })),
  };
};

// GET /api/model/status is {element_id: status}; accept an array form too.
export const modelStatus = m => {
  const out = {};
  const src = m?.elements ?? m ?? {};
  if (Array.isArray(src)) for (const e of src) out[e.element_id] = normStatus(e.status);
  else for (const [k, v] of Object.entries(src)) out[k] = normStatus(typeof v === "string" ? v : v?.status);
  return out;
};

export const evidence = e => {
  const ai = e.ai || {};
  const obs = ai.observations || [];
  const top = obs.reduce((best, o) => (o.score > (best?.score ?? -1) ? o : best), null);
  return {
    ...e,
    certificate: e.certificate_no,
    captured_at: e.capture_time,
    uploaded_at: e.upload_time,
    time_source: e.time_source, // in_app_capture | exif | manual | missing
    ai: {
      final_label: ai.final_label,
      top_score: top?.score ?? 0,
      observations: obs,
      escalated: !!(ai.escalation_model_id || ai.vlm),
      vlm: ai.vlm ? { ...ai.vlm, model: ai.escalation_model_id } : null,
      completion_pct: ai.completion_pct ?? null,
      model: ai.model_id,
      matches: ai.matches_declared_element,
      requires_review: ai.requires_review !== false,
      latency_ms: Math.round((ai.latency_s || 0) * 1000),
      error: ai.error || null,
    },
    duplicates: (e.duplicates || []).map(d => ({
      evidence_id: d.evidence_id,
      certificate: d.certificate_no,
      match_type: { exact: "Exact copy", near_duplicate_phash: "Near-duplicate (pHash)", near_duplicate_embedding: "Near-duplicate (embedding)" }[d.kind] || d.kind,
      similarity: d.score,
    })),
    flags: e.flags || [],
  };
};
// Newest first (B4).
export const evidenceList = l => (Array.isArray(l) ? l : l.items || []).map(evidence)
  .sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || "")));

export const schedule = s => ({
  ...s,
  delay_days: s.handover_delay_days ?? s.delay_days ?? 0,
  critical_path: s.critical_path || [],
  tasks: (s.tasks || []).map(t => ({
    ...t,
    name_en: t.name,
    outdoor: t.calendar === "outdoor",
    forecast_start: t.start,
    forecast_finish: t.finish,
    float_days: t.total_float_days,
    variance_days: t.finish_variance_days || 0,
  })),
});

export const FLAG_LABEL = {
  summer_working_hours: "Summer working hours", timestamp_anomaly: "Missing capture time", ppe: "PPE",
  no_camera_metadata: "No camera metadata", photo_predates_period: "Photo predates this period",
  photo_date_in_future: "Date in the future", capture_time_mismatch: "Time mismatch", off_site: "Away from site",
  authenticity_review: "Check authenticity",
};
export const safety = s => ({ items: Array.isArray(s) ? s : s.items || [] });

export const costs = c => {
  const log = c.log || [];
  return {
    ...c,
    avg_latency_ms: Math.round((c.avg_latency_s || 0) * 1000),
    total_cost_usd: c.est_total_cost_usd ?? 0,
    always_big_model_cost_usd: c.est_cost_if_always_vlm_usd ?? 0,
    escalated: Math.round((c.escalation_rate || 0) * (c.photos_processed || 0)),
    log,
    cost_label: "estimated",
  };
};

export const report = r => ({ ...r, dir: r.direction || r.dir || "ltr", lines: r.lines || [], figures: r.figures || {} });

// UI decision -> contract decision (schemas.json review_decisions).
export const reviewRequest = (decision, { quantity, reason, reviewer, evidence_id }) => ({
  decision: { approve: "supported", partial: "partial", reject: "rejected" }[decision] || decision,
  supported_qty: decision === "partial" ? Number(quantity) : decision === "reject" ? 0 : undefined,
  reason: reason || "",
  reviewer: reviewer || "Site engineer",
  evidence_id: evidence_id || null,
});

export const reviewResponse = r => ({
  element: r.element ? element(r.element) : null,
  modelStatus: r.model_status ? modelStatus(r.model_status) : null,
  audit: r.audit ? audit(r.audit) : null,
  schedule: r.schedule ? schedule(r.schedule) : null,
});
