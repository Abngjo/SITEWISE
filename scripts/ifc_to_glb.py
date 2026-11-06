"""Convert the sample IFC to a GLB for the Three.js viewer (owner: Dev B/D).
Run: python scripts/ifc_to_glb.py  ->  frontend/public/model.glb

Each mesh node is named with the element_id (IFC Tag), e.g. "D-103".
The frontend loads the GLB once, then recolors nodes from GET /api/model/status:
  supported=green  uncertain=amber  discrepancy=red  no_evidence=grey
"""
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
IFC = ROOT / "data" / "sample_project" / "project.ifc"
OUT = ROOT / "frontend" / "public" / "model.glb"


def main():
    f = ifcopenshell.open(str(IFC))
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    scene = trimesh.Scene()
    for el in f.by_type("IfcProduct"):
        if not el.Representation or not el.Tag:
            continue
        shape = ifcopenshell.geom.create_shape(s, el)
        v = np.array(shape.geometry.verts).reshape(-1, 3)
        fc = np.array(shape.geometry.faces).reshape(-1, 3)
        v = v[:, [0, 2, 1]] * np.array([1, 1, -1])  # IFC Z-up -> glTF Y-up
        m = trimesh.Trimesh(v, fc, process=False)
        m.visual.face_colors = [180, 180, 180, 255]
        scene.add_geometry(m, node_name=el.Tag, geom_name=el.Tag)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scene.export(str(OUT))
    print(f"wrote {OUT} ({len(scene.geometry)} elements)")


if __name__ == "__main__":
    main()
