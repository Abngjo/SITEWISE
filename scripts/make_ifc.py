"""Generate the SITEWISE sample building (owner: Dev C/D). Run: python scripts/make_ifc.py

A two-storey clinic block (Al Wakra Community Clinic, Package B; SAMPLE DATA):
  * PACKAGE elements (22): the audited scope. Tag = element_id (D-103 ...), deterministic GlobalId,
    same IDs and quantities as elements.csv, so all payment/schedule numbers are unchanged.
      - S-x01 slabs, W-x0n perimeter blockwork walls (with real window openings),
      - D-x0n door sets (frame + ajar leaf) in the corridor partitions, C-x0n suspended ceilings.
  * CONTEXT elements: the rest of the building, out of Package B scope. Tag starts with "CTX-":
      columns, corridor/room partitions, windows (glazing), stair, roof slab + parapet.
  * IfcSpace rooms with names (EN/AR); room label positions also written to frontend/public/rooms.json.
Payment quantities come from elements.csv (agreed BOQ measurement), not from IFC geometry.
"""
from __future__ import annotations

import csv
import json
import math
import uuid
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "sample_project"
PUBLIC = ROOT / "frontend" / "public"
NS = uuid.UUID("5a1e7e57-0000-4000-8000-517e7715e000")

LX, LY = 17.0, 13.0          # footprint (m)
H, SLAB = 3.6, 0.3           # storey height, slab thickness
WALL_H = H - SLAB            # 3.3 clear wall height
T, TP = 0.2, 0.12            # exterior / partition thickness
CORR_S, CORR_N = 5.5, 7.5    # corridor between y=5.5 and y=7.5
XMID = 8.5                   # zone A (west) | zone B (east)
LEVEL_Z = {"L1": 0.0, "L2": H}
DOOR_X = {"A": (3.5, 4.5), "B": (12.0, 13.0)}
SILL, HEAD = 0.9, 2.2
WIN_S = [(1.8, 3.2), (5.3, 6.7), (10.3, 11.7), (13.8, 15.2)]   # south/north window spans along x
WIN_EW = [(5.8, 7.2)]                                          # west/east window span along y


def guid_for(eid: str) -> str:
    return ifcopenshell.guid.compress(uuid.uuid5(NS, eid).hex)


def box(x0, y0, z0, x1, y1, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def rotated_panel(hx, hy, z0, w, thick, h, ang_deg):
    """Door leaf hinged at (hx, hy), swung ang_deg around the vertical axis."""
    a = math.radians(ang_deg)
    ux, uy = math.cos(a), math.sin(a)          # along the leaf
    nx, ny = -uy * thick, ux * thick           # leaf thickness
    pts = [(hx, hy), (hx + ux * w, hy + uy * w), (hx + ux * w + nx, hy + uy * w + ny), (hx + nx, hy + ny)]
    v = [(x, y, z0) for x, y in pts] + [(x, y, z0 + h) for x, y in pts]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def wall_with_openings(axis, fixed0, fixed1, span0, span1, z0, openings, sill=SILL, head=HEAD):
    """Boxes for a straight wall along `axis` ('x' or 'y') with rectangular openings (along-axis spans)."""
    parts = []

    def b(a0, a1, za, zb):
        if a1 - a0 < 1e-6 or zb - za < 1e-6:
            return
        if axis == "x":
            parts.append(box(a0, fixed0, za, a1, fixed1, zb))
        else:
            parts.append(box(fixed0, a0, za, fixed1, a1, zb))

    b(span0, span1, z0, z0 + sill)                       # below sills
    b(span0, span1, z0 + head, z0 + WALL_H)              # above heads
    cur = span0
    for o0, o1 in sorted(openings):                       # piers between openings
        b(cur, o0, z0 + sill, z0 + head)
        cur = o1
    b(cur, span1, z0 + sill, z0 + head)
    return parts


def partition_with_doors(y0, y1, x0, x1, z0, gaps):
    parts, cur = [], x0
    for g0, g1 in sorted(gaps):
        parts.append(box(cur, y0, z0, g0, y1, z0 + WALL_H))
        parts.append(box(g0, y0, z0 + 2.16, g1, y1, z0 + WALL_H))   # transom over the door
        cur = g1
    parts.append(box(cur, y0, z0, x1, y1, z0 + WALL_H))
    return parts


class Builder:
    def __init__(self):
        self.f = ifcopenshell.api.project.create_file(version="IFC4")
        f = self.f
        self.proj = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="SITEWISE Sample - Al Wakra Clinic Pkg B")
        ifcopenshell.api.unit.assign_unit(f)
        model = ifcopenshell.api.context.add_context(f, context_type="Model")
        self.body = ifcopenshell.api.context.add_context(f, context_type="Model", context_identifier="Body",
                                                         target_view="MODEL_VIEW", parent=model)
        site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Al Wakra (sample)")
        bldg = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Clinic Block B")
        ifcopenshell.api.aggregate.assign_object(f, relating_object=self.proj, products=[site])
        ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[bldg])
        self.storeys = {}
        for lv, z in LEVEL_Z.items():
            s = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey", name=lv)
            s.Elevation = z
            ifcopenshell.api.aggregate.assign_object(f, relating_object=bldg, products=[s])
            self.storeys[lv] = s
        self.rooms = []

    def element(self, ifc_class, tag, name, level, parts, guid=None, scope="package"):
        f = self.f
        el = ifcopenshell.api.root.create_entity(f, ifc_class=ifc_class, name=name)
        if guid:
            el.GlobalId = guid
        el.Tag = tag
        rep = ifcopenshell.api.geometry.add_mesh_representation(
            f, context=self.body, vertices=[[list(p) for p in v] for v, _ in parts], faces=[fc for _, fc in parts])
        ifcopenshell.api.geometry.assign_representation(f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(f, product=el)
        ifcopenshell.api.spatial.assign_container(f, relating_structure=self.storeys[level], products=[el])
        pset = ifcopenshell.api.pset.add_pset(f, product=el, name="SITEWISE_Scope")
        ifcopenshell.api.pset.edit_pset(f, pset=pset, properties={
            "InPackage": scope == "package",
            "Package": "B" if scope == "package" else "Other packages / existing",
        })
        return el

    def space(self, level, name, name_ar, x0, y0, x1, y1):
        f = self.f
        sp = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSpace", name=name)
        sp.LongName = name_ar
        ifcopenshell.api.aggregate.assign_object(f, relating_object=self.storeys[level], products=[sp])
        z = LEVEL_Z[level]
        # label position in glTF coordinates (Y up, Z = -IFC Y), see scripts/ifc_to_glb.py
        self.rooms.append({"name": name, "name_ar": name_ar, "level": level,
                           "x": round((x0 + x1) / 2, 2), "y": round(z + 1.4, 2), "z": round(-(y0 + y1) / 2, 2)})


ROOMS = {
    "L1": {("A", "S"): ("Consult room 1", "غرفة الكشف 1"), ("A", "N"): ("Consult room 2", "غرفة الكشف 2"),
           ("B", "S"): ("Treatment room", "غرفة العلاج"), ("B", "N"): ("Store", "المخزن")},
    "L2": {("A", "S"): ("Office 1", "المكتب 1"), ("A", "N"): ("Office 2", "المكتب 2"),
           ("B", "S"): ("Meeting room", "غرفة الاجتماعات"), ("B", "N"): ("Staff room", "غرفة الموظفين")},
}


def main():
    rows = list(csv.DictReader(open(DATA / "elements.csv", encoding="utf-8")))
    by_id = {r["element_id"]: r for r in rows}
    B = Builder()

    for lv, z in LEVEL_Z.items():
        n = "1" if lv == "L1" else "2"
        top = z - (0 if lv == "L1" else 0)          # finished floor level of this storey
        wz = top                                     # walls start at FFL

        # ---- PACKAGE: slab
        sid = f"S-{n}01"
        slab_z0 = -SLAB if lv == "L1" else z - SLAB
        B.element("IfcSlab", sid, f"{sid} {by_id[sid]['name']}", lv,
                  [box(-0.15, -0.15, slab_z0, LX + 0.15, LY + 0.15, slab_z0 + SLAB)], guid_for(sid))

        # ---- PACKAGE: perimeter blockwork with window openings
        walls = {
            f"W-{n}01": ("x", LY - T, LY, 0, LX, WIN_S),       # north
            f"W-{n}02": ("x", 0, T, 0, LX, WIN_S),             # south
            f"W-{n}03": ("y", 0, T, T, LY - T, WIN_EW),        # west
            f"W-{n}04": ("y", LX - T, LX, T, LY - T, WIN_EW),  # east
        }
        for wid, (axis, f0, f1, s0, s1, wins) in walls.items():
            B.element("IfcWall", wid, f"{wid} {by_id[wid]['name']}", lv,
                      wall_with_openings(axis, f0, f1, s0, s1, wz, wins), guid_for(wid))
            # CONTEXT: glazing in those openings
            for k, (o0, o1) in enumerate(wins):
                mid = (f0 + f1) / 2
                g = box(o0, mid - 0.02, wz + SILL, o1, mid + 0.02, wz + HEAD) if axis == "x" \
                    else box(mid - 0.02, o0, wz + SILL, mid + 0.02, o1, wz + HEAD)
                B.element("IfcWindow", f"CTX-{lv}-WIN-{wid[-2:]}{k}", "Window (Package A, glazing)", lv, [g], scope="context")

        # ---- PACKAGE: door sets in the corridor partitions (frame + ajar leaf)
        for zone in ("A", "B"):
            for side, wall_y, swing in (("S", CORR_S, -1), ("N", CORR_N, 1)):
                did = next(r["element_id"] for r in rows if r["type"] == "door" and r["floor"] == lv
                           and r["zone"] == zone and r["element_id"] in _door_order(lv, zone, side))
                g0, g1 = DOOR_X[zone]
                y0, y1 = wall_y - TP / 2, wall_y + TP / 2
                frame = [box(g0, y0 - 0.02, wz, g0 + 0.06, y1 + 0.02, wz + 2.16),
                         box(g1 - 0.06, y0 - 0.02, wz, g1, y1 + 0.02, wz + 2.16),
                         box(g0, y0 - 0.02, wz + 2.10, g1, y1 + 0.02, wz + 2.16)]
                hinge_y = y0 if side == "S" else y1
                leaf = rotated_panel(g0 + 0.06, hinge_y, wz + 0.01, (g1 - g0) - 0.12, 0.045 * (1 if side == "N" else -1),
                                     2.06, 32 * swing * (-1 if side == "S" else 1) * -1)
                B.element("IfcDoor", did, f"{did} {by_id[did]['name']}", lv, frame + [leaf], guid_for(did))
                rname, rname_ar = ROOMS[lv][(zone, side)]
                x0, x1 = (T, XMID) if zone == "A" else (XMID, LX - T)
                ry0, ry1 = (T, CORR_S) if side == "S" else (CORR_N, LY - T)
                B.space(lv, rname, rname_ar, x0, ry0, x1, ry1)
        B.space(lv, "Corridor", "الممر", T, CORR_S, LX - T, CORR_N)

        # ---- PACKAGE: suspended ceilings (zone A / B)
        for cid, (x0, x1) in ((f"C-{n}01", (T, XMID)), (f"C-{n}02", (XMID, LX - T))):
            B.element("IfcCovering", cid, f"{cid} {by_id[cid]['name']}", lv,
                      [box(x0, T, wz + 2.9, x1, LY - T, wz + 2.95)], guid_for(cid))

        # ---- CONTEXT: corridor partitions with door gaps, zone partitions, columns
        parts = (partition_with_doors(CORR_S - TP / 2, CORR_S + TP / 2, T, LX - T, wz, list(DOOR_X.values()))
                 + partition_with_doors(CORR_N - TP / 2, CORR_N + TP / 2, T, LX - T, wz, list(DOOR_X.values())))
        B.element("IfcWall", f"CTX-{lv}-PART-CORR", "Corridor partitions (Package C)", lv, parts, scope="context")
        B.element("IfcWall", f"CTX-{lv}-PART-ZONE", "Zone partitions (Package C)", lv,
                  [box(XMID - TP / 2, T, wz, XMID + TP / 2, CORR_S - TP / 2, wz + WALL_H),
                   box(XMID - TP / 2, CORR_N + TP / 2, wz, XMID + TP / 2, LY - T, wz + WALL_H)], scope="context")
        for i, cx in enumerate((0.25, XMID, LX - 0.25)):
            for j, cy in enumerate((0.25, LY / 2, LY - 0.25)):
                if cx == XMID and cy == LY / 2:
                    continue  # no column in the corridor
                B.element("IfcColumn", f"CTX-{lv}-COL-{i}{j}", "RC column (existing frame)", lv,
                          [box(cx - 0.25, cy - 0.25, wz, cx + 0.25, cy + 0.25, wz + WALL_H)], scope="context")

    # ---- CONTEXT: stair (L1 -> L2) at the east end of the corridor, roof slab + parapet
    steps, n_steps, x0 = [], 12, 13.9
    run = (LX - T - 0.1 - x0) / n_steps
    for k in range(n_steps):
        steps.append(box(x0 + k * run, CORR_S + TP, 0, x0 + (k + 1) * run, CORR_N - TP, (k + 1) * H / n_steps))
    B.element("IfcStair", "CTX-L1-STAIR", "Stair (Package C)", "L1", steps, scope="context")
    rz = LEVEL_Z["L2"] + WALL_H
    roof = [box(-0.15, -0.15, rz, LX + 0.15, LY + 0.15, rz + SLAB)]
    pz = rz + SLAB
    roof += [box(-0.15, -0.15, pz, LX + 0.15, 0.05, pz + 0.9), box(-0.15, LY - 0.05, pz, LX + 0.15, LY + 0.15, pz + 0.9),
             box(-0.15, 0.05, pz, 0.05, LY - 0.05, pz + 0.9), box(LX - 0.05, 0.05, pz, LX + 0.15, LY - 0.05, pz + 0.9)]
    B.element("IfcSlab", "CTX-L2-ROOF", "Roof slab + parapet (Package A)", "L2", roof, scope="context")

    out = DATA / "project.ifc"
    B.f.write(str(out))
    for r in rows:
        r["ifc_guid"] = guid_for(r["element_id"])
    with open(DATA / "elements.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "rooms.json").write_text(json.dumps(B.rooms, ensure_ascii=False, indent=1), encoding="utf-8")
    n_ctx = sum(1 for e in B.f.by_type("IfcElement") if (e.Tag or "").startswith("CTX-"))
    print(f"wrote {out}: {len(rows)} package elements, {n_ctx} context elements, {len(B.rooms)} rooms")


def _door_order(level, zone, side):
    """Which door ID sits in which room: matches elements.csv names (consult 1/2, treatment, store...)."""
    n = "1" if level == "L1" else "2"
    table = {("A", "S"): f"D-{n}01", ("A", "N"): f"D-{n}02", ("B", "S"): f"D-{n}03", ("B", "N"): f"D-{n}04"}
    return {table[(zone, side)]}


if __name__ == "__main__":
    main()
