"""Generate the canonical sample building (owner: Dev D). Run: python scripts/make_ifc.py

Creates data/sample_project/project.ifc with ONE IFC element per row in elements.csv:
  - Tag = element_id (D-103 etc.), deterministic GlobalId from element_id
  - Writes the GlobalIds back into elements.csv (ifc_guid column)
Geometry is simplified (boxes); quantities for payment come from elements.csv, which
represent the agreed BOQ measurement, not from IFC geometry.
"""
from __future__ import annotations

import csv
import uuid
from pathlib import Path

import numpy as np
import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample_project"
NS = uuid.UUID("5a1e7e57-0000-4000-8000-517e7715e000")

LX, LY, H, T = 17.0, 13.0, 3.6, 0.2   # footprint (m), storey height, wall thickness
LEVEL_Z = {"L1": 0.0, "L2": H}


def guid_for(eid: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(NS, eid).hex)


def place(f, product, x, y, z, rot_deg=0.0):
    r = np.radians(rot_deg)
    m = np.eye(4)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = np.cos(r), -np.sin(r), np.sin(r), np.cos(r)
    m[:3, 3] = (x, y, z)
    ifcopenshell.api.geometry.edit_object_placement(f, product=product, matrix=m)


def main():
    rows = list(csv.DictReader(open(DATA / "elements.csv", encoding="utf-8")))
    f = ifcopenshell.api.project.create_file(version="IFC4")
    proj = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="SITEWISE Sample - Al Wakra Clinic Pkg B")
    ifcopenshell.api.unit.assign_unit(f)
    model = ifcopenshell.api.context.add_context(f, context_type="Model")
    body = ifcopenshell.api.context.add_context(f, context_type="Model", context_identifier="Body",
                                                target_view="MODEL_VIEW", parent=model)
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Al Wakra (sample)")
    bldg = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Clinic Block B")
    ifcopenshell.api.aggregate.assign_object(f, relating_object=proj, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[bldg])
    storeys = {}
    for lv, z in LEVEL_Z.items():
        s = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=lv)
        s.Elevation = z
        ifcopenshell.api.aggregate.assign_object(f, relating_object=bldg, products=[s])
        storeys[lv] = s

    door_slots = {"A": [(3.0, 0), (7.0, 0)], "B": [(11.0, LY), (14.0, LY)]}
    door_count = {}
    for r in rows:
        eid, lv, z = r["element_id"], r["floor"], LEVEL_Z[r["floor"]]
        el = ifcopenshell.api.root.create_entity(f, ifc_class=r["ifc_class"], name=f"{eid} {r['name']}")
        el.GlobalId = guid_for(eid)
        el.Tag = eid
        t = r["type"]
        if t == "slab":
            rep = ifcopenshell.api.geometry.add_slab_representation(
                f, context=body, depth=0.3, polyline=[(0, 0), (LX, 0), (LX, LY), (0, LY)])
            ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
            place(f, el, 0, 0, z - 0.3 if lv != "L1" else -0.3)
        elif t == "wall":
            side = r["name"].split()[1]  # north/south/west/east
            length = LX if side in ("north", "south") else LY
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=body, length=length, height=H - 0.3, thickness=T)
            ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
            x, y, rot = {"south": (0, 0, 0), "north": (0, LY - T, 0),
                         "west": (T, 0, 90), "east": (LX, 0, 90)}[side]
            place(f, el, x, y, z, rot)
        elif t == "door":
            key = (lv, r["zone"])
            i = door_count.get(key, 0)
            door_count[key] = i + 1
            x, y = door_slots[r["zone"]][i % 2]
            rep = ifcopenshell.api.geometry.add_wall_representation(
                f, context=body, length=1.0, height=2.1, thickness=T + 0.06)
            ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
            place(f, el, x, y - 0.03 if y == 0 else y - T - 0.03, z)
        elif t == "ceiling":
            x0 = 0 if r["zone"] == "A" else LX / 2
            rep = ifcopenshell.api.geometry.add_slab_representation(
                f, context=body, depth=0.05,
                polyline=[(0, 0), (LX / 2, 0), (LX / 2, LY), (0, LY)])
            ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
            place(f, el, x0, 0, z + 2.9)
        ifcopenshell.api.spatial.assign_container(f, relating_structure=storeys[lv], products=[el])
        r["ifc_guid"] = el.GlobalId

    out = DATA / "project.ifc"
    f.write(str(out))
    with open(DATA / "elements.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} with {len(rows)} elements; updated elements.csv ifc_guid")


if __name__ == "__main__":
    main()
