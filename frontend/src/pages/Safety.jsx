import { useEffect, useState } from "react";
import { api, imageUrl } from "../api/client.js";
import { FLAG_LABEL } from "../api/adapters.js";
import { useStore } from "../store.jsx";
import { ErrorState, Icon, Loading } from "../ui.jsx";

export default function Safety() {
  const { evidence } = useStore();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.safety().then(setData).catch(e => setErr(e.message)); }, [evidence.length]);
  if (err) return <ErrorState message={err} />;
  if (!data) return <Loading label="Loading safety flags" />;
  return (
    <>
      <div className="page-head">
        <div><h1>Safety and compliance</h1><p className="muted">Qatar restricts outdoor work in summer midday hours (1 Jun–15 Sep, 10:00–15:30). Photos of outdoor tasks taken in that window, and photos with no trustworthy capture time, are flagged for the safety officer.</p></div>
      </div>
      <section className="card flush">
        <div className="card-head pad"><h2>Flags</h2><span className="pill" style={{ "--c": "#F1C40F" }}><i />{data.items.length} awaiting safety officer review</span></div>
        {data.items.length ? (
          <ul className="flags">
            {data.items.map((f, i) => (
              <li key={`${f.evidence_id}-${f.type}-${i}`}>
                {f.evidence_id ? <img src={imageUrl(f.evidence_id)} alt={f.evidence_id} /> : <span />}
                <div>
                  <div className="flag-top">
                    <span className="tag warn">{f.type === "summer_working_hours" && <Icon name="sun" size={13} />}{FLAG_LABEL[f.type] || f.type}</span>
                    {f.element_id && <b className="mono">{f.element_id}</b>}
                    <span className="muted small">{f.evidence_id}</span>
                  </div>
                  <p>{f.message}</p>
                  <p className="small muted">Severity: {f.severity || "review"} · <a href="#evidence">Open evidence</a></p>
                </div>
                <span className="status-text">Awaiting safety officer review</span>
              </li>
            ))}
          </ul>
        ) : <div className="empty pad"><b>No safety flags.</b><span className="muted">No photo so far falls inside the summer midday window or lacks a capture time.</span></div>}
        <p className="foot-note">Flags never change payment and are not confirmed violations.</p>
      </section>
    </>
  );
}
