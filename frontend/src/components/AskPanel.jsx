import { useState } from "react";
import { Icon } from "../ui.jsx";

// POST /api/ask {question, lang}: Gemma answers from SITEWISE's computed data; every figure in the answer
// is checked against that data before it's shown.
const SUGGEST = {
  en: ["Which claimed items have no photo evidence, and how much is at risk?",
       "Why is handover late, and which tasks are critical?",
       "Which photos may have been reused from earlier certificates?"],
  ar: ["ما البنود المطالب بها دون دليل مصور وما قيمتها؟",
       "لماذا تأخر موعد التسليم وما المهام الحرجة؟"],
};

export default function AskPanel() {
  const [lang, setLang] = useState("en");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const send = async question => {
    const text = (question ?? q).trim(); if (!text || busy) return;
    setQ(text); setBusy(true); setRes(null);
    try {
      const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: text, lang }) });
      setRes(await r.json());
    } catch { setRes({ answer: "Can't reach SITEWISE right now.", grounded: null }); }
    finally { setBusy(false); }
  };
  const ar = lang === "ar";
  return (
    <section className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <h2>Ask SITEWISE</h2>
        <div className="seg" role="group" aria-label="Language">
          <button aria-pressed={!ar} onClick={() => setLang("en")}>EN</button>
          <button aria-pressed={ar} onClick={() => setLang("ar")} lang="ar" className="ar">ع</button>
        </div>
      </div>
      <form className="row" style={{ gap: 8 }} onSubmit={e => { e.preventDefault(); send(); }}>
        <input className="input" dir={ar ? "rtl" : "ltr"} value={q} onChange={e => setQ(e.target.value)}
          placeholder={ar ? "اسأل عن المطالبة أو الأدلة أو الجدول الزمني…" : "Ask about this claim, the evidence or the schedule…"} />
        <button className="btn primary" disabled={busy || !q.trim()}>{busy ? "Thinking…" : "Ask"}</button>
      </form>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        {SUGGEST[lang].map(s => <button key={s} type="button" className="tag" dir={ar ? "rtl" : "ltr"} style={{ cursor: "pointer", border: "none" }} onClick={() => send(s)}>{s}</button>)}
      </div>
      {res && (
        <div style={{ marginTop: 12 }}>
          <p dir={ar ? "rtl" : "ltr"} style={{ whiteSpace: "pre-wrap", margin: "0 0 8px" }}>{res.answer}</p>
          {res.grounded === true && <span className="tag" style={{ color: "var(--s-supported)" }}><Icon name="check" size={14} /> All figures verified against project data</span>}
          {res.grounded === false && <span className="tag" style={{ color: "var(--s-discrepancy, #E74C3C)" }}><Icon name="alert" size={14} /> Answer blocked: a figure couldn't be verified</span>}
          {res.model && <span className="muted small" style={{ marginLeft: 8 }}>{res.model.split("/").pop()} via Hugging Face Inference Providers · the engineer decides</span>}
        </div>
      )}
    </section>
  );
}
