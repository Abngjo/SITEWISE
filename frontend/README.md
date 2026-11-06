# Frontend (Dev B)

Vite + React + three.js. Built (B1–B8 done).

```bash
# terminal 1, repo root: backend with stub AI
SITEWISE_DISABLE_MODELS=1 uvicorn backend.main:app --reload --port 7860
# terminal 2
cd frontend
npm install
npm run dev            # http://localhost:5173  (proxies /api, /model.glb and /m to 127.0.0.1:7860)
npm run build          # Dockerfile builds this automatically on the Space
```

Sign-in is a prototype screen: any email and any 4+ character password.

| Where | What |
|---|---|
| `src/api/client.js` | every call in `contracts/api.md` |
| `src/api/adapters.js` | maps contract shapes to what the screens use (the only file to touch if a contract changes) |
| `src/store.jsx` | shared state; `submitReview()` applies the single review response to 3D + payment + schedule |
| `src/pages/` | Payment, Evidence, Model, Schedule, Report, Safety, Costs |
| `src/components/` | Login (animated sign-in), Shell, DynamicIsland (Doha time + live status), ThemeSwitch (light/dark/system), Viewer3D |

Notes:
- The proxy targets `127.0.0.1`, not `localhost`: on Windows Node resolves `localhost` to IPv6 first and uvicorn listens on IPv4.
- The UI never computes money. It only displays what the API returns.
- UI decisions map to the contract: Approve → `supported`, Partial → `partial` + `supported_qty`, Reject → `rejected`.
- Hidden reset before rehearsals: user menu → Reset demo state, or Shift + Alt + R.
- The 3D viewer frames whatever `/model.glb` contains and looks from the side where D-103 sits.

Pages (priority order): Payment audit → Evidence review (with side-by-side reuse) → 3D model → Schedule → Report (EN/AR, `dir="rtl"`) → Safety → AI costs.

## 3D recolor (Three.js)
```js
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
const COLORS = { supported: 0x2ECC71, uncertain: 0xF1C40F, discrepancy: 0xE74C3C, no_evidence: 0x9AA5AE };
new GLTFLoader().load('/model.glb', (gltf) => {
  scene.add(gltf.scene);
  refresh = async () => {
    const status = await (await fetch('/api/model/status')).json();
    gltf.scene.traverse((o) => {
      if (o.isMesh && status[o.name]) {   // node/mesh name == element_id
        o.material = o.material.clone();
        o.material.color.setHex(COLORS[status[o.name]]);
      }
    });
  };
  refresh();
});
// After POST /api/elements/{id}/review, use the returned model_status directly. No second fetch needed.
```
Click an element with a Raycaster → `o.name` is the element_id → show `/api/elements` row + evidence thumbnails (`/api/evidence/{id}/image`).

`mobile_upload.html` is served at `/m` by the backend. Put a QR code to `https://<space-url>/m` on the demo screen.
