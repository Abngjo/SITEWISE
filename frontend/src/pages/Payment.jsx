import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api/client.js";
import { useStore } from "../store.jsx";
import { Icon, Kpi, Legend, Loading, StatusPill, num, qar, fmtDate } from "../ui.jsx";

function QrCard() {
  const [svg, setSvg] = useState("");
  const [url, setUrl] = useState("");
  useEffect(() => {
    let alive = true;
    api.meta().then(m => {
      const u = m?.mobile_url || `${location.origin}/m`;
      QRCode.toString(u, { type: "svg", margin: 0, errorCorrectionLevel: "M" }).then(s => { if (alive) { setSvg(s); setUrl(u); } });
    });
    return () => { alive = false; };
  }, []);
  return (
    <section className="card qr-card">
      <div className="qr" aria-label={`QR code for ${url}`} dangerouslySetInnerHTML={{ __html: svg }} />
      <div className="qr-copy">
        <h2>Photograph a door, live</h2>
        <p className="muted">Scan with a phone on the same wifi to open the upload page. The photo runs through the AI and appears on the Evidence page.</p>
        <code className="url">{url || "…"}</code>
      </div>
    </section>
  );
}

export default function Payment() {
  const { audit, project, schedule } = useStore();
  if (!audit) return <Loading label="Loading payment audit" />;
  const t = audit.totals;
  const pct = v => (t.claimed ? (v / t.claimed) * 100 : 0);
  const unverified = Math.max(0, t.discrepancy - t.noEvidence);
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Payment audit</h1>
          <p className="muted">{project.certificate} · as of {fmtDate(project.as_of)} · {project.contractor}</p>
        </div>
        <a className="btn primary" href="#evidence">Review evidence <Icon name="arrow" size={16} /></a>
      </div>

      <section className="kpis" aria-label="Claim totals">
        <Kpi label="Claimed this period" value={t.claimed} />
        <Kpi label="Supported by evidence" value={t.supported} tone="good" hint={`${pct(t.supported).toFixed(1)}% of claim`} />
        <Kpi label="Discrepancy" value={t.discrepancy} tone="bad" hint="Claimed minus supported" />
        <Kpi label="Claimed with no evidence" value={t.noEvidence} tone="grey" hint="No photo submitted" />
      </section>

      <div className="grid-2-1">
        <section className="card">
          <div className="card-head"><h2>Where the claim stands</h2><span className="muted small">{qar(t.claimed)}</span></div>
          <div className="bar" role="img" aria-label={`Supported ${pct(t.supported).toFixed(0)}%, unverified ${pct(unverified).toFixed(0)}%, no evidence ${pct(t.noEvidence).toFixed(0)}%`}>
            <i style={{ width: `${pct(t.supported)}%`, background: "var(--s-supported)" }} />
            <i style={{ width: `${pct(unverified)}%`, background: "var(--s-uncertain)" }} />
            <i style={{ width: `${pct(t.noEvidence)}%`, background: "var(--s-none)" }} />
          </div>
          <div className="bar-key">
            <span><i style={{ background: "var(--s-supported)" }} />Supported <b>{qar(t.supported)}</b></span>
            <span><i style={{ background: "var(--s-uncertain)" }} />Photo submitted, not yet supported</span>
            <span><i style={{ background: "var(--s-none)" }} />No photo <b>{qar(t.noEvidence)}</b></span>
          </div>
          {t.net != null && <p className="small muted mt">Retention ({project.retention_pct}%) <b className="ink">{qar(t.retention)}</b> · recommended for review, net <b className="ink">{qar(t.net)}</b></p>}
          {schedule && <p className="small muted mt">Forecast handover <b className="ink">{fmtDate(schedule.forecast_handover)}</b>, {schedule.delay_days} days after baseline. <a href="#schedule">See schedule</a></p>}
        </section>
        <QrCard />
      </div>

      <section className="card flush">
        <div className="card-head pad"><h2>BOQ items</h2><Legend compact /></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Item</th><th>Description</th><th>Unit</th><th className="r">Rate</th>
                <th className="r">Prev. certified</th><th className="r">Claimed cum.</th><th className="r">Supported cum.</th>
                <th className="r">Claimed value</th><th className="r">Supported value</th><th className="r">Discrepancy</th>
                <th>Status</th><th>Claimed without evidence</th>
              </tr>
            </thead>
            <tbody>
              {audit.items.map(i => (
                <tr key={i.boq_item}>
                  <td className="mono">{i.boq_item}</td>
                  <td><span>{i.description_en}</span><span className="ar sub" lang="ar" dir="rtl">{i.description_ar}</span></td>
                  <td>{i.unit}</td>
                  <td className="r num">{num(i.rate)}</td>
                  <td className="r num">{num(i.previous_certified_qty)}</td>
                  <td className="r num">{num(i.claimed_cumulative_qty)}</td>
                  <td className="r num">{num(i.supported_cumulative_qty)}</td>
                  <td className="r num">{num(i.claimed_value)}</td>
                  <td className="r num">{num(i.supported_value)}</td>
                  <td className={`r num ${i.discrepancy > 0 ? "neg" : ""}`}>{num(i.discrepancy)}</td>
                  <td><StatusPill status={i.status} /></td>
                  <td>{i.elements_without_evidence?.length ? <span className="chips">{i.elements_without_evidence.map(id => <a key={id} className="chip" href="#evidence">{id}</a>)}</span> : <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={7}>Totals, QAR</td>
                <td className="r num">{num(t.claimed)}</td><td className="r num">{num(t.supported)}</td><td className="r num neg">{num(t.discrepancy)}</td><td colSpan={2} />
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="foot-note">{audit.note || "Recommendation only. Certification remains with the engineer / QS."}</p>
      </section>
    </>
  );
}
