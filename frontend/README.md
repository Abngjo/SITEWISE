# Frontend (Dev B)

```bash
cd frontend
npm create vite@latest . -- --template react    # keep public/model.glb and mobile_upload.html
npm install three
npm run dev            # proxy /api to the backend: add to vite.config.js
                       #   server: { proxy: { '/api': 'http://localhost:7860', '/model.glb': 'http://localhost:7860' } }
npm run build          # Dockerfile builds this automatically on the Space
```

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
