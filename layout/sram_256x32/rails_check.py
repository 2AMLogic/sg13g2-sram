"""Flat supply-connectivity analysis of the macro layout (issue #92).

Grows the connected set of Metal1 / Via1 / Metal2 / Via2 / Metal3 / Via3 / Metal4 from
each Metal4 trunk and reports, for the periphery body ties and the bitcell supply
risers, which net they reach. Used by ``test_macro.py`` and the record script.
"""

from __future__ import annotations

import klayout.db as kdb

import generate as g

_LAYERS = dict(m1=g.bc.L_METAL1, v1=g.L_VIA1, m2=g.L_METAL2, v2=g.L_VIA2, m3=g.L_METAL3, v3=g.L_VIA3, m4=g.L_METAL4)
_EDGES = [("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3"), ("m3", "v3"), ("v3", "m4")]
_U = 1000  # dbu per um


def _box(x: float, y: float, h: float) -> kdb.Box:
    return kdb.Box(round((x - h) * _U), round((y - h) * _U), round((x + h) * _U), round((y + h) * _U))


def _grow(regions: dict[str, kdb.Region], seed: kdb.Region) -> dict[str, kdb.Region]:
    sel = {k: kdb.Region() for k in regions}
    sel["m4"] = regions["m4"].interacting(seed)
    changed = True
    while changed:
        changed = False
        for a, b in _EDGES:
            for src, dst in ((a, b), (b, a)):
                new = regions[dst].interacting(sel[src])
                if (new - sel[dst]).count():
                    sel[dst] = (sel[dst] + new).merged()
                    changed = True
    return sel


def analyse(layout: kdb.Layout, top: kdb.Cell, gen: g.Gen) -> dict:
    regions = {k: kdb.Region(top.begin_shapes_rec(layout.layer(*lp))).merged() for k, lp in _LAYERS.items()}
    y_mid = 10.0
    sel = {
        net: _grow(regions, kdb.Region(_box(g.TRUNK_X[net], y_mid, 0.01)))
        for net in ("VDD", "VSS")
    }
    short = sum((sel["VDD"][k] & sel["VSS"][k]).count() for k in regions)

    ties = gen.tie_wiring
    wired = wrong = 0
    floating: list[dict] = []
    for t in ties:
        pad = kdb.Region(_box(t["x"], t["y"], 0.01))
        mine = not (pad & sel[t["net"]]["m1"]).is_empty()
        other = not (pad & sel["VSS" if t["net"] == "VDD" else "VDD"]["m1"]).is_empty()
        wired += mine
        wrong += other
        if not mine:
            floating.append(t)

    # bitcell supply risers: one VSS and one VDD probe per cell, in global coordinates
    h, w, xcp = g.bc.H_CELL, g.bc.W_CELL, g.bc.xc("pad_c")
    probes = {"VSS": kdb.Region(), "VDD": kdb.Region()}
    y_vss, y_vdd = 0.8, h - 0.8  # between the tie contact and the NMOS / PMOS contact, on the riser
    for c in range(g.COLS):
        x = (c + 1) * w - xcp if c % 2 else c * w + xcp
        for r in range(g.ROWS):
            ys = (r + 1) * h - y_vss if r % 2 else r * h + y_vss
            yd = (r + 1) * h - y_vdd if r % 2 else r * h + y_vdd
            probes["VSS"].insert(_box(x, ys, 0.005))
            probes["VDD"].insert(_box(x, yd, 0.005))
    risers = {}
    for net in ("VDD", "VSS"):
        risers[net] = {
            "expected": g.COLS * g.ROWS,
            "on_rail": probes[net].interacting(sel[net]["m1"]).count(),
            "on_other_rail": probes[net].interacting(sel["VSS" if net == "VDD" else "VDD"]["m1"]).count(),
        }
    return {
        "ties_expected": len(ties),
        "ties_on_own_rail": wired,
        "ties_on_other_rail": wrong,
        "ties_floating": len(floating),
        "floating_ties": floating[:10],
        "vdd_vss_short_polygons": short,
        "bitcell_risers": risers,
        "polygons_on_rail": {net: {k: v.count() for k, v in sel[net].items()} for net in sel},
    }
