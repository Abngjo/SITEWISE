import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STATUS } from "../api/adapters.js";

const L2_LIFT = 3.2;

// B3: loads /model.glb; every mesh name is an element_id. Colours come from /api/model/status.
export default function Viewer3D({ status, selected, onSelect, flash, explode, hideL2, theme }) {
  const host = useRef();
  const ctx = useRef({});
  const [state, setState] = useState("loading");

  useEffect(() => {
    const el = host.current;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    el.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 500);
    const controls = new OrbitControls(camera, renderer.domElement);
    // Default view looks from the −z side, where scripts/ifc_to_glb.py puts D-103/D-104,
    // so the demo door is visible without orbiting. Re-framed to the model's bounds on load.
    const VIEW_DIR = new THREE.Vector3(0.9, 0.75, -1).normalize();
    let radius = 14;
    controls.target.set(8.5, 3, -6.5);
    camera.position.copy(controls.target).addScaledVector(VIEW_DIR, 40);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.minDistance = 8; controls.maxDistance = 120;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(20, 40, 25); scene.add(sun);
    const grid = new THREE.GridHelper(60, 30, 0x888888, 0x888888);
    grid.position.set(10, -0.01, 6); grid.material.transparent = true; grid.material.opacity = 0.18; scene.add(grid);

    const meshes = {};
    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight; renderer.setSize(w, h); camera.aspect = w / h;
      // Keep the whole building in frame, from its bounding radius and the viewport shape.
      const fit = radius / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2));
      const dist = fit * 1.05 * Math.max(1, 1.3 / camera.aspect);
      const dir = camera.position.clone().sub(controls.target).normalize();
      camera.position.copy(controls.target).addScaledVector(dir, dist);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();

    new GLTFLoader().load("/model.glb", gltf => {
      gltf.scene.traverse(o => {
        if (!o.isMesh) return;
        const id = o.name || o.parent?.name;
        o.material = o.material.clone(); // clone per mesh so each element colours independently
        o.material.roughness = 0.8; o.material.metalness = 0;
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry), new THREE.LineBasicMaterial({ color: 0x0b1220, transparent: true, opacity: 0.35 }));
        o.add(edges);
        o.userData.id = id; o.userData.level = o.userData.level || (/-2\d\d$/.test(id) ? "L2" : "L1");
        o.userData.baseY = o.position.y;
        meshes[id] = o;
      });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const sphere = box.getBoundingSphere(new THREE.Sphere());
      radius = sphere.radius + L2_LIFT / 2;
      controls.target.copy(sphere.center);
      camera.position.copy(sphere.center).addScaledVector(VIEW_DIR, 1);
      grid.position.set(sphere.center.x, box.min.y - 0.01, sphere.center.z);
      resize();
      ctx.current.applyAll?.();
      setState("ready");
    }, undefined, () => setState("error"));

    const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
    let down = null, hover = null;
    const pick = e => {
      const r = renderer.domElement.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, camera);
      const hit = ray.intersectObjects(Object.values(meshes).filter(m => m.visible), false)[0];
      return hit?.object.userData.id || null;
    };
    const onDown = e => { down = [e.clientX, e.clientY]; };
    const onUp = e => { if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 5) { const id = pick(e); if (id) ctx.current.onSelect?.(id); } down = null; };
    const onMove = e => { const id = pick(e); if (id !== hover) { hover = id; renderer.domElement.style.cursor = id ? "pointer" : "grab"; ctx.current.hover = id; } };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);

    let raf;
    const clock = new THREE.Clock();
    const loop = () => {
      const t = clock.getElapsedTime(), c = ctx.current;
      for (const [id, m] of Object.entries(meshes)) {
        const lift = m.userData.level === "L2" && c.explode ? L2_LIFT : 0;
        m.position.y += (m.userData.baseY + lift - m.position.y) * 0.12;
        m.visible = !(m.userData.level === "L2" && c.hideL2);
        const isSel = id === c.selected, isFlash = c.flash && id in c.flash, isHover = id === c.hover;
        const k = isFlash ? 0.55 + 0.45 * Math.sin(t * 10) : isSel ? 0.35 : isHover ? 0.18 : 0;
        m.material.emissive.copy(m.material.color).multiplyScalar(k);
        m.children[0].material.opacity = isSel ? 0.95 : 0.35;
      }
      controls.update();
      renderer.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    ctx.current = { ...ctx.current, meshes, renderer, scene, grid };
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); controls.dispose();
      renderer.domElement.remove(); renderer.dispose();
    };
  }, []);

  // colours + interaction state, without rebuilding the scene
  useEffect(() => {
    const c = ctx.current;
    c.onSelect = onSelect; c.selected = selected; c.flash = flash; c.explode = explode; c.hideL2 = hideL2;
    c.applyAll = () => {
      for (const [id, m] of Object.entries(c.meshes || {})) {
        const s = status[id] || "no_evidence";
        m.material.color.set(STATUS[s].color);
        m.material.transparent = false;
      }
    };
    c.applyAll();
  }, [status, selected, onSelect, flash, explode, hideL2]);

  useEffect(() => {
    const g = ctx.current.grid; if (g) g.material.opacity = theme === "light" ? 0.25 : 0.14;
    ctx.current.meshes && Object.values(ctx.current.meshes).forEach(m => m.children[0].material.color.set(theme === "light" ? 0x1b2433 : 0x05080f));
  }, [theme, state]);

  return (
    <div className="viewer" ref={host}>
      {state === "loading" && <div className="viewer-msg"><span className="spinner" />Loading model.glb…</div>}
      {state === "error" && <div className="viewer-msg err">Couldn't load /model.glb. Run <code>npm run glb</code>, or check that the backend serves it.</div>}
    </div>
  );
}
