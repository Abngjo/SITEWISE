import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useStore } from "../store.jsx";
import { ErrorState, Icon, Loading, num } from "../ui.jsx";

// GET /api/report?lang=en|ar returns {lang, direction, lines[], figures{}}. The text lines are written by the
// backend in each language; the figure tiles below only label the backend's numbers.
const FIG = {
  claimed_this_period: ["Claimed this period", "المطالب به هذه الفترة", ""],
  supported_this_period: ["Supported by evidence", "المدعوم بالأدلة", "supported"],
  discrepancy: ["Discrepancy", "الفرق", "discrepancy"],
  claimed_value_with_no_evidence: ["Claimed with no photo", "مطالب به دون صورة", ""],
  retention: ["Retention", "المحتجزات", ""],
  recommended_for_review_net: ["Recommended for review (net)", "الصافي الموصى بمراجعته", ""],
};

export default function Report() {
  const { audit, project } = useStore(); // refetch when the audit changes after a review
  const [lang, setLang] = useState("en");
  const [rep, setRep] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true; setErr("");
    api.report(lang).then(r => alive && setRep(r)).catch(e => alive && setErr(e.message));
    return () => { alive = false; };
  }, [lang, audit]);

  const ar = rep?.lang === "ar";
  return (
    <>
      <div className="page-head no-print">
        <div><h1>Audit report</h1><p className="muted">Written by the backend in English and Arabic from the same figures.</p></div>
        <div className="row">
          <div className="seg" role="group" aria-label="Report language">
            <button aria-pressed={lang === "en"} onClick={() => setLang("en")}>English</button>
            <button aria-pressed={lang === "ar"} onClick={() => setLang("ar")} lang="ar" className="ar">العربية</button>
          </div>
          <button className="btn" onClick={() => window.print()}><Icon name="print" size={16} />Download</button>
        </div>
      </div>
      {err ? <ErrorState message={err} /> : !rep ? <Loading label="Generating report" /> : (
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
