import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { STATUS } from "../api/adapters.js";

const L2_LIFT = 3.6;
const PKG_LEVEL = id => (/-2\d\d$/.test(id) ? "L2" : "L1");
const colorOf = s => STATUS[s]?.color || (typeof s === "string" && s.startsWith("#") ? s : STATUS.no_evidence.color);

/* SITEWISE BIM viewer.
   /model.glb: every node is named with its IFC Tag.
     - Package B elements (S-101, W-203, D-103, C-102 ...) are coloured by `status` (a status key or a hex colour).
     - Context elements (Tag "CTX-L1-...") are the rest of the building: drawn as translucent glass/ghost, not pickable.
   /rooms.json: IfcSpace labels.  pins: {element_id: evidence photo count}.
   Click an element (or a pin) to fly to it. X-ray ghosts everything except doors and the selection. */
export default function Viewer3D({ status, selected, onSelect, flash, explode, hideL2, theme,
                                   xray = false, labels = true, pins = {}, lang = "en" }) {
  const host = useRef();
  const ctx = useRef({});
  const [state, setState] = useState("loading");

  useEffect(() => {
    const el = host.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);
    const css = new CSS2DRenderer();
    Object.assign(css.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
    el.appendChild(css.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 500);
    const controls = new OrbitControls(camera, renderer.domElement);
    const VIEW_DIR = new THREE.Vector3(0.9, 0.75, -1).normalize();
    let radius = 14;
    const home = { target: new THREE.Vector3(8.5, 3, -6.5), pos: new THREE.Vector3() };
    controls.target.copy(home.target);
    camera.position.copy(controls.target).addScaledVector(VIEW_DIR, 40);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.495;
    controls.minDistance = 3; controls.maxDistance = 120;

    scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.25));
    const sun = new THREE.DirectionalLight(0xfff4e0, 2.0);   // Doha afternoon sun, from the south-west
    sun.position.set(-14, 30, 22); sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -20, right: 20, top: 20, bottom: -20, near: 1, far: 90 });
    sun.shadow.bias = -0.0008;
    scene.add(sun); scene.add(sun.target);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.ShadowMaterial({ opacity: 0.18 }));
    ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true; scene.add(ground);
    const grid = new THREE.GridHelper(60, 30, 0x888888, 0x888888);
    grid.material.transparent = true; grid.material.opacity = 0.18; scene.add(grid);

    const meshes = {};          // every node
    const pickable = [];        // package elements only
    const levelGroups = { L1: new THREE.Group(), L2: new THREE.Group() };   // room labels per level
    scene.add(levelGroups.L1, levelGroups.L2);

    const fitDistance = () => {
      const fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
      return fit * 1.05 * Math.max(1, 1.3 / camera.aspect);
    };
    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h); css.setSize(w, h); camera.aspect = w / h;
      if (!ctx.current.flown) {
        const dir = camera.position.clone().sub(controls.target).normalize();
        camera.position.copy(controls.target).addScaledVector(dir, fitDistance());
      }
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();

    // ---- camera flights
    let fly = null;
    const flyTo = (target, dist, dir) => {
      const d = (dir || camera.position.clone().sub(controls.target)).clone().normalize();
      fly = { t0: performance.now(), dur: 900,
              fromT: controls.target.clone(), toT: target.clone(),
              fromP: camera.position.clone(), toP: target.clone().addScaledVector(d, dist) };
    };
    const ease = x => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

    new GLTFLoader().load("/model.glb", gltf => {
      gltf.scene.traverse(o => {
        if (!o.isMesh) return;
        const id = o.name || o.parent?.name;
        const isCtx = id.startsWith("CTX-");
        // IFC meshes arrive without normals: split to flat faces and compute them, or lighting goes black.
        o.geometry = o.geometry.toNonIndexed();
        o.geometry.deleteAttribute("color");
        o.geometry.computeVertexNormals();
        o.material = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0, side: THREE.DoubleSide });
        o.castShadow = (!isCtx && !id.startsWith("C-")) || id.includes("-COL-");
        o.receiveShadow = true;
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry, 25),
          new THREE.LineBasicMaterial({ color: 0x0b1220, transparent: true, opacity: 0.35 }));
        o.add(edges);
        o.geometry.computeBoundingBox();
        o.userData = {
          id, ctx: isCtx, baseY: o.position.y,
          level: isCtx ? (id.includes("-L2-") ? "L2" : "L1") : PKG_LEVEL(id),
          kind: isCtx ? (id.includes("-WIN-") ? "glass" : id.includes("ROOF") ? "roof" : "ghost")
                      : id[0] === "D" ? "door" : id[0] === "C" ? "ceiling" : id[0] === "W" ? "wall" : "slab",
        };
        meshes[id] = o;
        if (!isCtx) pickable.push(o);
      });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      radius = sphere.radius + L2_LIFT / 2;
      home.target.copy(sphere.center);
      controls.target.copy(sphere.center);
      camera.position.copy(sphere.center).addScaledVector(VIEW_DIR, 1);
      grid.position.set(sphere.center.x, box.min.y - 0.01, sphere.center.z);
      ground.position.set(sphere.center.x, box.min.y - 0.005, sphere.center.z);
      sun.target.position.copy(sphere.center);
      resize();
      home.pos.copy(camera.position);
      ctx.current.applyAll?.();
      ctx.current.buildPins?.();
      setState("ready");
    }, undefined, () => setState("error"));

    fetch("/rooms.json").then(r => (r.ok ? r.json() : [])).then(rooms => {
      for (const rm of rooms) {
        const div = document.createElement("div");
        div.className = "room-label";
        div.dataset.en = rm.name; div.dataset.ar = rm.name_ar;
        div.textContent = rm.name;
        const obj = new CSS2DObject(div);
        obj.position.set(rm.x, rm.y, rm.z);
        (levelGroups[rm.level] || levelGroups.L1).add(obj);
      }
      ctx.current.applyLabels?.();
    }).catch(() => {});

    // ---- picking
    const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
    let down = null, hover = null;
    const pick = e => {
      const r = renderer.domElement.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, camera);
      const hit = ray.intersectObjects(pickable.filter(m => m.visible), false)[0];
      return hit?.object.userData.id || null;
    };
    const onDown = e => { down = [e.clientX, e.clientY]; fly = null; };
    const onUp = e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) { const id = pick(e); if (id) ctx.current.onSelect?.(id); } down = null; };
    const onMove = e => { const id = pick(e); if (id !== hover) { hover = id; renderer.domElement.style.cursor = id ? "pointer" : "grab"; ctx.current.hover = id; } };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("wheel", () => { fly = null; }, { passive: true });

    // ---- loop
    let raf;
    const clock = new THREE.Clock();
    const loop = () => {
      const t = clock.getElapsedTime(), c = ctx.current;
      for (const [id, m] of Object.entries(meshes)) {
        const lift = m.userData.level === "L2" && c.explode ? L2_LIFT : 0;
        m.position.y += (m.userData.baseY + lift - m.position.y) * 0.12;
        m.visible = !(m.userData.level === "L2" && c.hideL2);
        if (m.userData.ctx) continue;
        const isSel = id === c.selected, isFlash = c.flash && id in c.flash, isHover = id === c.hover;
        const k = isFlash ? 0.55 + 0.45 * Math.sin(t * 10) : isSel ? 0.3 + 0.12 * Math.sin(t * 3) : isHover ? 0.18 : 0;
        m.material.emissive.copy(m.material.color).multiplyScalar(k);
        m.children[0].material.opacity = isSel ? 0.95 : c.xray ? 0.15 : 0.35;
      }
      const l2 = levelGroups.L2;
      l2.position.y += ((c.explode ? L2_LIFT : 0) - l2.position.y) * 0.12;
      l2.visible = !c.hideL2 && c.labels !== false;
      // ground-floor labels only when that floor can be seen (otherwise they float over the roof)
      levelGroups.L1.visible = c.labels !== false && (c.hideL2 || c.explode || c.xray);
      if (fly) {
        const x = Math.min(1, (performance.now() - fly.t0) / fly.dur), k = ease(x);
        controls.target.lerpVectors(fly.fromT, fly.toT, k);
        camera.position.lerpVectors(fly.fromP, fly.toP, k);
        if (x >= 1) fly = null;
      }
      controls.update();
      renderer.render(scene, camera);
      css.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    ctx.current = {
      ...ctx.current, meshes, renderer, scene, grid, flyTo, home, levelGroups,
      fitDistance, resetView: () => { ctx.current.flown = false; flyTo(home.target, fitDistance(), VIEW_DIR); },
    };
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); controls.dispose();
      renderer.domElement.remove(); css.domElement.remove(); renderer.dispose();
    };
  }, []);

  // ---- colours, transparency, interaction state (no scene rebuild)
  useEffect(() => {
    const c = ctx.current;
    Object.assign(c, { onSelect, selected, flash, explode, hideL2, xray, labels });
    c.applyAll = () => {
      const dark = theme !== "light";
      for (const [id, m] of Object.entries(c.meshes || {})) {
        const u = m.userData, mat = m.material;
        let opacity = 1;
        if (u.ctx) {
          if (u.kind === "glass") { mat.color.set(dark ? 0x6fb7e8 : 0x8cc8f0); opacity = xray ? 0.08 : 0.32; mat.roughness = 0.1; }
          else { mat.color.set(dark ? 0x8b97a6 : 0xc9d1db); opacity = xray ? 0.04 : u.kind === "roof" ? 0.1 : 0.2; }
          m.children[0].material.opacity = xray ? 0.05 : 0.14;
        } else {
          mat.color.set(colorOf(status[id] || "no_evidence"));
          const focus = id === selected || u.kind === "door" || (flash && id in flash);
          if (xray && !focus) opacity = u.kind === "slab" ? 0.12 : 0.18;
          else if (u.kind === "ceiling") opacity = id === selected ? 0.9 : 0.5;
        }
        mat.transparent = opacity < 1;
        mat.opacity = opacity;
        mat.depthWrite = opacity >= 1;
        m.renderOrder = opacity < 1 ? 1 : 0;
        mat.needsUpdate = true;
      }
    };
    c.applyAll();
  }, [status, selected, onSelect, flash, explode, hideL2, xray, labels, theme, state]);

  // ---- fly to the selected element (not on first load: open on the whole building)
  useEffect(() => {
    const c = ctx.current, m = c.meshes?.[selected];
    if (!m || !c.flyTo) return;
    if (!c.seenFirst) { c.seenFirst = true; return; }
    const bb = m.geometry.boundingBox.clone().applyMatrix4(m.matrixWorld);
    const center = bb.getCenter(new THREE.Vector3());
    const size = bb.getSize(new THREE.Vector3()).length();
    c.flown = true;
    c.flyTo(center, Math.min(28, Math.max(7, size * 1.6)));
  }, [selected, state]);

  // ---- evidence pins (camera badge per element with photos)
  useEffect(() => {
    const c = ctx.current;
    c.buildPins = () => {
      (c.pinObjs || []).forEach(o => { o.element.remove(); o.parent?.remove(o); });
      c.pinObjs = [];
      for (const [id, n] of Object.entries(pins || {})) {
        const m = c.meshes?.[id];
        if (!m || !n) continue;
        const bb = m.geometry.boundingBox;
        const div = document.createElement("button");
        div.className = "ev-pin" + (id === selected ? " on" : "");
        div.title = `${id}: ${n} evidence photo${n > 1 ? "s" : ""}`;
        div.innerHTML = `<svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><path fill="currentColor" d="M9 4 7.2 6H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3.2L15 4H9Zm3 5a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z"/></svg><span>${n}</span>`;
        div.style.pointerEvents = "auto";
        div.onpointerdown = e => e.stopPropagation();
        div.onclick = e => { e.stopPropagation(); c.onSelect?.(id); };
        const obj = new CSS2DObject(div);
        obj.position.set((bb.min.x + bb.max.x) / 2, bb.max.y + 0.35, (bb.min.z + bb.max.z) / 2);
        obj.center.set(0.5, 1);
        m.add(obj);
        c.pinObjs.push(obj);
      }
    };
    c.buildPins();
  }, [pins, selected, state]);

  // ---- labels language + theme
  useEffect(() => {
    const c = ctx.current;
    c.applyLabels = () => Object.values(c.levelGroups || {}).forEach(g => g.children.forEach(o => {
      o.element.textContent = lang === "ar" ? o.element.dataset.ar : o.element.dataset.en;
      o.element.dir = lang === "ar" ? "rtl" : "ltr";
    }));
    c.applyLabels();
    const g = c.grid; if (g) g.material.opacity = theme === "light" ? 0.25 : 0.14;
    c.meshes && Object.values(c.meshes).forEach(m => !m.userData.ctx && m.children[0].material.color.set(theme === "light" ? 0x1b2433 : 0x05080f));
  }, [theme, state, lang]);

  return (
    <div className="viewer" ref={host} style={{ position: "relative" }}>
      {state === "ready" && (
        <button className="btn sm viewer-reset" onClick={() => ctx.current.resetView?.()} title="Back to the whole building">
          Reset view
        </button>
      )}
      {state === "loading" && <div className="viewer-msg"><span className="spinner" />Loading model.glb…</div>}
      {state === "error" && <div className="viewer-msg err">Couldn't load /model.glb. Run <code>npm run glb</code>, or check that the backend serves it.</div>}
    </div>
  );
}
