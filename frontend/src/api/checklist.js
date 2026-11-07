// Per-component checklist for a photo, e.g. "Frame ✓ · Leaf ✗ · Handle ?".
//
// Person A's VLM will return a checklist; until that field lands we show a PREVIEW derived from the
// VLM's existing `completion` verdict, clearly labelled as such in the UI (source: "preview").
// Accepted real shapes (whichever A ships):
//   ai.checklist or ai.vlm.checklist =
//     [{component|name|part: "frame", status|state|present: "present"|"missing"|"unclear"|true|false|null}, ...]
//     or { frame: true, leaf: false, handle: null }  (values may also be "yes"/"no"/"unclear")

export const COMPONENTS = {
  door: ["Frame", "Leaf", "Handle"],
  wall: ["Blockwork", "Mortar joints", "Plaster"],
  ceiling: ["Grid", "Boards", "Finish"],
  slab: ["Formwork", "Rebar", "Concrete"],
};

const toState = v => {
  if (v === true) return "yes";
  if (v === false) return "no";
  const s = String(v ?? "").toLowerCase();
  if (["yes", "present", "installed", "done", "complete", "ok", "true", "✓"].includes(s)) return "yes";
  if (["no", "missing", "absent", "not_installed", "not_started", "false", "✗"].includes(s)) return "no";
  return "unknown";
};
const title = s => String(s).replace(/[_-]+/g, " ").replace(/^\w/, c => c.toUpperCase());

function fromReal(raw) {
  if (!raw) return null;
  if (Array.isArray(raw)) {
    const items = raw.map(x => ({ name: title(x.component ?? x.name ?? x.part ?? "?"), state: toState(x.status ?? x.state ?? x.present) }));
    return items.length ? items : null;
  }
  if (typeof raw === "object") {
    const items = Object.entries(raw).map(([k, v]) => ({ name: title(k), state: toState(v) }));
    return items.length ? items : null;
  }
  return null;
}

// Preview from the VLM completion verdict: complete -> all ✓, partial -> first ✓ / second ✗ / rest ?,
// not_started -> all ✗, anything else (no VLM run, unclear) -> all ?.
function preview(type, completion) {
  const names = COMPONENTS[type] || ["Element"];
  return names.map((name, i) => ({
    name,
    state: completion === "complete" ? "yes"
      : completion === "not_started" ? "no"
      : completion === "partial" ? (i === 0 ? "yes" : i === 1 ? "no" : "unknown")
      : "unknown",
  }));
}

export function checklistFor(ev, elementType) {
  const ai = ev?.ai || {};
  const real = fromReal(ai.checklist ?? ai.vlm?.checklist);
  if (real) return { items: real, source: "model" };
  return { items: preview(elementType, ai.completion ?? ai.vlm?.completion), source: "preview" };
}

export const MARK = { yes: "✓", no: "✗", unknown: "?" };
export const STATE_LABEL = { yes: "present", no: "missing", unknown: "unclear" };
