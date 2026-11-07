import { createPortal } from "react-dom";
import { useStore } from "../store.jsx";
import { Icon } from "../ui.jsx";

// Live toasts, e.g. "D-103: new photo, escalated to Gemma 4" when a phone upload arrives.
// Rendered into <body> so `position: fixed` is relative to the screen, not to an animated (transformed) ancestor.
export default function Toasts() {
  const { toasts, dismissToast, openEvidence } = useStore();
  if (!toasts.length) return null;
  return createPortal(
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.warn ? "warn" : ""}`}>
          <span className="toast-ico"><Icon name={t.warn ? "alert" : "phone"} size={16} /></span>
          <span className="toast-text">{t.text}</span>
          {t.evidence_id && <button className="toast-act" onClick={() => { openEvidence(t.evidence_id); dismissToast(t.id); }}>Open</button>}
          <button className="toast-x" aria-label="Dismiss" onClick={() => dismissToast(t.id)}><Icon name="x" size={14} /></button>
        </div>
      ))}
    </div>,
    document.body,
  );
}
