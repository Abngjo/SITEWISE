import { useRef, useState } from "react";
import { Icon } from "../ui.jsx";
import ThemeSwitch from "./ThemeSwitch.jsx";

// Prototype sign-in: no real authentication. The button runs a three-stage animation:
// ripple from the click point -> spinner -> check, then the app fades in.
export default function Login({ onSignedIn, theme, setTheme }) {
  const [stage, setStage] = useState("idle"); // idle | loading | success
  const [ripple, setRipple] = useState(null);
  const [leaving, setLeaving] = useState(false);
  const [email, setEmail] = useState("noor.alkuwari@consultant.qa");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const btn = useRef();
  const ptr = useRef(null);
  const recordPointer = e => { const r = btn.current.getBoundingClientRect(); ptr.current = { x: e.clientX - r.left, y: e.clientY - r.top }; };

  const submit = e => {
    e.preventDefault();
    if (stage !== "idle") return;
    if (!/^\S+@\S+\.\S+$/.test(email)) return setErr("Enter a work email address, like name@company.qa.");
    if (pw.length < 4) return setErr("Enter your password (any 4+ characters in this prototype).");
    setErr("");
    const r = btn.current.getBoundingClientRect();
    const { x, y } = ptr.current || { x: r.width / 2, y: r.height / 2 };
    ptr.current = null;
    setRipple({ x, y, k: Date.now() });
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    setStage("loading");
    setTimeout(() => setStage("success"), reduce ? 150 : 1100);
    setTimeout(() => setLeaving(true), reduce ? 300 : 1750);
    setTimeout(() => onSignedIn({ email }), reduce ? 350 : 2150);
  };

  return (
    <div className={`login ${leaving ? "leaving" : ""}`}>
      <aside className="login-art">
        <div className="brand"><span className="brand-mark" aria-hidden="true" /><span>SITEWISE</span></div>
        <div className="login-copy">
          <h1>Evidence-backed payment auditing for Qatar's construction projects.</h1>
          <p>Every claimed quantity is checked against site photos, the building model and BOQ rates before anyone certifies a riyal.</p>
          <ol className="flow">
            <li><b>AI observes</b><span>SigLIP2 reads each photo; uncertain ones go to Gemma 4.</span></li>
            <li><b>Evidence supports</b><span>Reuse checks, BOQ rates and the summer heat rule.</span></li>
            <li><b>Engineer certifies</b><span>Only a person's decision changes payment.</span></li>
          </ol>
        </div>
        <svg className="login-blueprint" viewBox="0 0 400 240" aria-hidden="true">
          <g fill="none" stroke="currentColor" strokeWidth="1">
            <path d="M40 200V80l120-50 120 50v120z" /><path d="M40 140h240M160 30v170M100 200v-40h40v40M200 110h50v30h-50z" />
            <path d="M300 200h60M330 200V60" strokeDasharray="4 4" /><path d="M20 200h360" />
          </g>
        </svg>
        <span className="login-foot">Qai × Hugging Face Hackathon · Doha 2026</span>
      </aside>

      <main className="login-main">
        <div className="login-top"><ThemeSwitch value={theme} onChange={setTheme} /></div>
        <form className="login-card" onSubmit={submit} noValidate>
          <div>
            <h2>Sign in</h2>
            <p className="muted">Al Wakra Community Clinic · Package B</p>
          </div>
          <label className="field">
            <span>Work email</span>
            <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="username" disabled={stage !== "idle"} />
          </label>
          <label className="field">
            <span>Password</span>
            <input className="input" type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="current-password" placeholder="Any 4+ characters" disabled={stage !== "idle"} />
          </label>
          {err && <p className="form-error" role="alert"><Icon name="alert" size={16} />{err}</p>}
          <button ref={btn} className={`signin ${stage}`} type="submit" onPointerDown={recordPointer} aria-busy={stage === "loading"} aria-live="polite">
            {ripple && <span className="ripple" key={ripple.k} style={{ left: ripple.x, top: ripple.y }} />}
            <span className="signin-label">Sign in</span>
            <span className="signin-spinner" aria-hidden="true" />
            <svg className="signin-check" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
            <span className="sr">{stage === "loading" ? "Signing in" : stage === "success" ? "Signed in" : ""}</span>
          </button>
          <p className="note">Prototype: no real accounts. Sample project data only.</p>
        </form>
      </main>
    </div>
  );
}
