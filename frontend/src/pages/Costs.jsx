import { useEffect, useState } from "react";
import { api } from "../api/client.js";
import { useStore } from "../store.jsx";
import { ErrorState, Loading } from "../ui.jsx";

const usd = n => `$${Number(n || 0).toFixed(4)}`;

export default function Costs() {
  const { evidence } = useStore();
  const [c, setC] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.aiCosts().then(setC).catch(e => setErr(e.message)); }, [evidence.length]);
  if (err) return <ErrorState message={err} />;
  if (!c) return <Loading label="Loading AI costs" />;
  const max = Math.max(c.always_big_model_cost_usd, c.total_cost_usd, 1e-9);
  const saved = c.always_big_model_cost_usd ? 1 - c.total_cost_usd / c.always_big_model_cost_usd : 0;
  return (
    <>
      <div className="page-head">
        <div><h1>AI costs</h1><p className="muted">A small model reads every photo on the Space's CPU. Only uncertain or conflicting photos go to the large model, which is the only paid call.</p></div>
      </div>
      <section className="stats">
        <div className="stat"><span className="lbl">Photos processed</span><b>{c.photos_processed}</b></div>
        <div className="stat"><span className="lbl">Escalated to VLM</span><b>{(c.escalation_rate * 100).toFixed(1)}%</b><span className="small muted">{c.escalated} of {c.photos_processed}</span></div>
        <div className="stat"><span className="lbl">Average latency</span><b>{(c.avg_latency_ms / 1000).toFixed(2)} s</b><span className="small muted">{c.cache_hits} cache hits</span></div>
        <div className="stat"><span className="lbl">Total cost ({c.cost_label})</span><b>{usd(c.total_cost_usd)}</b></div>
      </section>
      <section className="card">
        <div className="card-head"><h2>Two-stage routing vs always using the big model</h2><span className="tag">{c.cost_label}</span></div>
        {c.photos_processed === 0 ? (
          <p className="muted">No photos processed yet. Upload one on the Evidence page or from a phone to see the comparison.</p>
        ) : (
          <>
            <div className="cmp">
              <div className="cmp-row"><span>SITEWISE routing</span><div className="cmp-track"><i className="ours" style={{ width: `${(c.total_cost_usd / max) * 100}%` }} /></div><b>{usd(c.total_cost_usd)}</b></div>
              <div className="cmp-row"><span>Always Gemma 4</span><div className="cmp-track"><i style={{ width: "100%" }} /></div><b>{usd(c.always_big_model_cost_usd)}</b></div>
            </div>
            <p className="small"><b>{(saved * 100).toFixed(0)}% lower</b> estimated cost for this claim's photos. Replace with the test-split results from the model card before quoting them.</p>
          </>
        )}
        <dl className="kv mt">
          <dt>Stage 1</dt><dd>SigLIP2 (or the fine-tuned checkpoint) on the Space</dd>
          <dt>Stage 2</dt><dd>Gemma 4 (Qwen2.5-VL fallback) via Hugging Face Inference Providers</dd>
        </dl>
      </section>
    </>
  );
}
