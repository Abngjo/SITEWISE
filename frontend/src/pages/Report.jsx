import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useStore } from "../store.jsx";
import { ErrorState, Icon, Loading, num } from "../ui.jsx";

// GET /api/report?lang=en|ar returns {lang, direction, lines[], figures{}}. The text lines are written by the
// backend in each language; the figure tiles below only label the backend's numbers.
// GET /api/audit-letter?lang=en|ar returns the draft letter to the contractor. Every figure and item is
// written by code; an open LLM (Gemma 4 via Inference Providers) writes only the opening paragraph.
const FIG = {
  claimed_this_period: ["Claimed this period", "المطالب به هذه الفترة", ""],
  supported_this_period: ["Supported by evidence", "المدعوم بالأدلة", "supported"],
  discrepancy: ["Discrepancy", "الفرق", "discrepancy"],
  claimed_value_with_no_evidence: ["Claimed with no photo", "مطالب به دون صورة", ""],
  retention: ["Retention", "المحتجزات", ""],
  recommended_for_review_net: ["Recommended for review (net)", "الصافي الموصى بمراجعته", ""],
};

function Letter({ letter }) {
  const ar = letter.lang === "ar";
  const llm = letter.opening_source && !letter.opening_source.startsWith("template");
  return (
    <article className={`report card ${ar ? "rtl" : ""}`} dir={letter.direction} lang={letter.lang} key={`letter-${letter.lang}`}>
      <header className="rep-head">
        <div>
          <h2>{ar ? "مسودة خطاب إلى المقاول" : "Draft letter to the contractor"}</h2>
          {letter.header.map((h, i) => <p key={i} className={i ? "muted small" : ""}><bdi>{h}</bdi></p>)}
        </div>
        <span className="brand small-brand" dir="ltr"><span className="brand-mark" aria-hidden="true" />SITEWISE</span>
      </header>
      <p>{letter.opening}</p>
      <p><b><bdi>{letter.summary}</bdi></b></p>
      <h3 className="h-sm">{ar ? "البنود المطلوب استكمالها" : "Items requiring action"} ({letter.items.length})</h3>
      <ol className="rep-lines">{letter.items.map((l, i) => <li key={i}><bdi>{l}</bdi></li>)}</ol>
      <p className="muted">{letter.closing}</p>
      <p className="muted small no-print" dir="ltr">
        {llm ? `Opening paragraph written by ${letter.opening_source} via Hugging Face Inference Providers. ` : "Opening paragraph from template. "}
        All figures and items are computed by code.
      </p>
    </article>
  );
}

export default function Report() {
  const { audit, project, evidence } = useStore(); // refetch when the audit or evidence changes
  const [lang, setLang] = useState("en");
  const [doc, setDoc] = useState("report"); // report | letter
  const [rep, setRep] = useState(null);
  const [letter, setLetter] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true; setErr("");
    const p = doc === "report"
      ? api.report(lang).then(r => alive && setRep(r))
      : api.letter(lang).then(r => alive && setLetter(r));
    p.catch(e => alive && setErr(e.message));
    return () => { alive = false; };
  }, [lang, doc, audit, evidence]);

  const ar = rep?.lang === "ar";
  const current = doc === "report" ? rep : letter;
  return (
    <>
      <div className="page-head no-print">
        <div>
          <h1>{doc === "report" ? "Audit report" : "Letter to contractor"}</h1>
          <p className="muted">{doc === "report" ? "Written by the backend in English and Arabic from the same figures." : "Drafted for the engineer to review and sign. Figures from code, never from the AI."}</p>
        </div>
        <div className="row">
          <div className="seg" role="group" aria-label="Document">
            <button aria-pressed={doc === "report"} onClick={() => setDoc("report")}>Report</button>
            <button aria-pressed={doc === "letter"} onClick={() => setDoc("letter")}>Letter</button>
          </div>
          <div className="seg" role="group" aria-label="Language">
            <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
            <button aria-pressed={lang === "ar"} onClick={() => setLang("ar")} lang="ar" className="ar">العربية</button>
          </div>
          <button className="btn" onClick={() => window.print()}><Icon name="print" size={16} />Download</button>
        </div>
      </div>
      {err ? <ErrorState message={err} /> : !current || current.lang !== lang ? <Loading label={doc === "report" ? "Generating report" : "Drafting letter"} /> : doc === "letter" ? <Letter letter={letter} /> : (
        <article className={`report card ${ar ? "rtl" : ""}`} dir={rep.dir} lang={rep.lang} key={rep.lang}>
          <header className="rep-head">
            <div>
              <h2>{ar ? "تقرير تدقيق مطالبة الدفع" : "Payment claim audit report"}</h2>
              <p>{ar ? project?.name_ar : project?.name_en}</p>
              <p className="muted small"><bdi>{project?.certificate}</bdi></p>
            </div>
            <span className="brand small-brand" dir="ltr"><span className="brand-mark" aria-hidden="true" />SITEWISE</span>
          </header>
          <div className="rep-totals">
            {Object.entries(FIG).filter(([k]) => rep.figures[k] != null).map(([k, [en, arl, tone]]) => (
              <div key={k} className={tone}><span>{ar ? arl : en}</span><b><bdi>{ar ? "ر.ق" : "QAR"} {num(rep.figures[k])}</bdi></b></div>
            ))}
            {rep.figures.handover_delay_days != null && (
              <div><span>{ar ? "تأخير التسليم" : "Handover delay"}</span><b><bdi>{rep.figures.handover_delay_days} {ar ? "يوم" : "days"}</bdi></b></div>
            )}
          </div>
          <ol className="rep-lines">{rep.lines.map((l, i) => <li key={i}>{l}</li>)}</ol>
        </article>
      )}
    </>
  );
}
