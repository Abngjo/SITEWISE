import { useMemo, useState } from "react";
import { api } from "../api/client.js";
import { useStore } from "../store.jsx";
import { Icon, Loading, fmtDate } from "../ui.jsx";

const D = s => Date.parse(s + "T00:00:00Z");

export default function Schedule() {
  const { schedule: live } = useStore();
  const [whatIf, setWhatIf] = useState(null); // schedule returned for a what-if
  const [task, setTask] = useState("T-210");
  const [days, setDays] = useState(5);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const s = whatIf || live;

  const range = useMemo(() => {
    if (!s) return null;
    const all = s.tasks.flatMap(t => [D(t.baseline_finish), D(t.forecast_start), D(t.forecast_finish)]).filter(Number.isFinite);
    const min = Math.min(...all), max = Math.max(...all) + 10 * 864e5;
    const months = [];
    for (let d = new Date(min); d <= max; d.setUTCMonth(d.getUTCMonth() + 1, 1)) months.push(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
    const sumStart = Date.UTC(2026, 5, 1), sumEnd = Date.UTC(2026, 8, 15);
    return { min, max, span: max - min, months: months.filter(m => m >= min), sumStart, sumEnd };
  }, [s]);
  if (!s || !range) return <Loading label="Loading schedule" />;
  const x = t => `${((t - range.min) / range.span) * 100}%`;
  const w = (a, b) => `${Math.max(0.6, ((b - a + 864e5) / range.span) * 100)}%`;

  const run = async () => {
    setBusy(true); setErr("");
    try { setWhatIf(await api.schedule(task, days)); } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <>
      <div className="page-head">
        <div><h1>Schedule forecast</h1><p className="muted">Critical path forecast from claimed progress, with Qatar's summer calendar: outdoor tasks run at reduced capacity 1 Jun–15 Sep (midday restriction 10:00–15:30).</p></div>
      </div>

      <section className="sched-top">
        <div className={`delay-big ${s.delay_days > 0 ? "late" : ""}`}>
          <span className="lbl">Delay to handover</span>
          <b>{s.delay_days > 0 ? "+" : ""}{s.delay_days}<small> days</small></b>
          {s.delay_exposure_qar > 0 && (
            <span className="lbl" title={s.delay_damages_note}>≈ QAR {Number(s.delay_exposure_qar).toLocaleString("en-US")} delay damages exposure
              <br /><span className="small muted">QAR {Number(s.delay_damages_per_day_qar).toLocaleString("en-US")}/day · sample assumption</span></span>
          )}
        </div>
        <div className="card dates">
          <div><span className="lbl">Baseline handover</span><b>{fmtDate(s.baseline_handover)}</b></div>
          <Icon name="arrow" />
          <div><span className="lbl">Forecast handover</span><b className={s.delay_days > 0 ? "neg" : ""}>{fmtDate(s.forecast_handover)}</b></div>
        </div>
        <div className="card whatif">
          <span className="lbl">What-if</span>
          <div className="row">
            <label className="field grow"><span>Delay task</span>
              <select className="input" value={task} onChange={e => setTask(e.target.value)}>
                {s.tasks.map(t => <option key={t.task_id} value={t.task_id}>{t.task_id} · {t.name_en}{t.critical ? " (critical)" : ` (float ${t.float_days}d)`}</option>)}
              </select>
            </label>
            <label className="field narrow"><span>Days</span><input className="input" type="number" min="0" max="60" value={days} onChange={e => setDays(Math.max(0, Number(e.target.value)))} /></label>
          </div>
          <div className="row">
            <button className="btn primary" onClick={run} disabled={busy} aria-busy={busy}>{busy ? <span className="spinner sm" /> : null}Run what-if</button>
            {whatIf && <button className="btn" onClick={() => setWhatIf(null)}>Clear</button>}
          </div>
          {err && <p className="msg bad">{err}</p>}
          {whatIf?.what_if && (
            <p className="small">
              Delaying <b>{whatIf.what_if.task_id}</b> by {whatIf.what_if.days} days {whatIf.forecast_handover !== live.forecast_handover
                ? <>moves handover to <b className="neg">{fmtDate(whatIf.forecast_handover)}</b>{whatIf.delay_exposure_qar > (live.delay_exposure_qar || 0) && <> and adds <b className="neg">QAR {Number(whatIf.delay_exposure_qar - (live.delay_exposure_qar || 0)).toLocaleString("en-US")}</b> of delay exposure</>}.</>
                : <>does not move handover: the task has enough float.</>}
            </p>
          )}
        </div>
      </section>

      <section className="card flush">
        <div className="card-head pad">
          <h2>Tasks</h2>
          <div className="gkey"><span><i className="k-fc" />Forecast</span><span><i className="k-mark" />Baseline finish</span><span><i className="k-base" />Complete</span><span><i className="k-crit" />Critical</span><span><i className="k-sum" />Summer window</span></div>
        </div>
        <div className="table-wrap">
          <div className="gantt">
            <div className="g-head"><span />
              <div className="g-axis">{range.months.map(m => <span key={m} style={{ left: x(m) }}>{new Date(m).toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" })}</span>)}</div>
            </div>
            {s.tasks.map(t => (
              <div key={t.task_id} className={`g-row ${t.critical ? "crit" : ""}`}>
                <div className="g-label">
                  <span className="g-name">{t.outdoor && <Icon name="sun" size={14} className="sun" />}{t.name_en}</span>
                  <span className="small muted mono">{t.task_id} · {t.complete ? "complete" : t.critical ? "critical" : `float ${t.float_days}d`}{!t.complete ? ` · ${Math.round((t.progress || 0) * 100)}% done` : ""}{t.variance_days ? ` · +${t.variance_days}d vs baseline` : ""}</span>
                </div>
                <div className="g-track">
                  <span className="g-summer" style={{ left: x(range.sumStart), width: w(range.sumStart, range.sumEnd) }} />
                  <span className={`g-bar fc ${t.complete ? "done" : ""}`} style={{ left: x(D(t.forecast_start)), width: w(D(t.forecast_start), D(t.forecast_finish)) }} title={`Forecast ${t.forecast_start} → ${t.forecast_finish}`} />
                  {t.baseline_finish && <span className="g-base-mark" style={{ left: x(D(t.baseline_finish) + 864e5) }} title={`Baseline finish ${t.baseline_finish}`} />}
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="foot-note"><Icon name="sun" size={14} className="sun" /> Outdoor task. {s.calendar_note}{s.critical_path?.length ? ` Critical path: ${s.critical_path.join(" → ")}.` : ""}</p>
      </section>
    </>
  );
}
