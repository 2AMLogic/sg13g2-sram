"""Flat supply-connectivity analysis of the macro layout (issues #92, #231).

Grows the connected set of Metal1 / Via1 / Metal2 / Via2 / Metal3 / Via3 / Metal4 / Via4 / Metal5 from
each Metal5 trunk and reports, for the periphery body ties, the periphery supply D/S pads, and the
bitcell supply risers, which net they reach. Used by ``test_macro.py`` and the record script.
"""

from __future__ import annotations

import generate as g
import klayout.db as kdb

_LAYERS = dict(
    m1=g.bc.L_METAL1,
    v1=g.L_VIA1,
    m2=g.L_METAL2,
    v2=g.L_VIA2,
    m3=g.L_METAL3,
    v3=g.L_VIA3,
    m4=g.L_METAL4,
    v4=g.L_VIA4,
    m5=g.L_METAL5,
)
_EDGES = [
    ("m1", "v1"),
    ("v1", "m2"),
    ("m2", "v2"),
    ("v2", "m3"),
    ("m3", "v3"),
    ("v3", "m4"),
    ("m4", "v4"),
    ("v4", "m5"),
]
_U = 1000  # dbu per um


def _box(x: float, y: float, h: float) -> kdb.Box:
    return kdb.Box(
        round((x - h) * _U),
        round((y - h) * _U),
        round((x + h) * _U),
        round((y + h) * _U),
    )


def _grow(regions: dict[str, kdb.Region], seed: kdb.Region) -> dict[str, kdb.Region]:
    sel = {k: kdb.Region() for k in regions}
    sel["m5"] = regions["m5"].interacting(seed)
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


def _expected_cell_name(inst: g.Inst) -> str:
    if inst.ref in g.DEVICE_REFS:
        kind = inst.ref.rsplit("_", 1)[1]
        w, lg = g.micron(inst.params["w"]), g.micron(inst.params["l"])
        return f"sg13_lv_{kind}_w{w:g}_l{lg:g}".replace(".", "p")
    return inst.ref


def _device_pad_centers(layout: kdb.Layout, cell: kdb.Cell) -> dict[str, kdb.Point]:
    """Read D, S and B Metal1 pad centres (in dbu) directly from a transistor cell's drawn geometry."""
    la = layout.layer(*g.bc.L_ACTIV)
    lm1 = layout.layer(*g.bc.L_METAL1)
    activs = sorted((s.box for s in cell.shapes(la).each() if s.is_box()), key=lambda b: b.left)
    assert len(activs) == 2, (cell.name, len(activs))
    ch_box, tie_box = activs
    ds_bars = sorted(
        (s.box for s in cell.shapes(lm1).each() if s.is_box() and ch_box.overlaps(s.box)),
        key=lambda b: b.left,
    )
    assert len(ds_bars) == 2, (cell.name, len(ds_bars))
    tie_bars = [s.box for s in cell.shapes(lm1).each() if s.is_box() and tie_box.overlaps(s.box)]
    assert len(tie_bars) == 1, (cell.name, len(tie_bars))
    return {"D": ds_bars[0].center(), "S": ds_bars[1].center(), "B": tie_bars[0].center()}


def _pair_instances(layout: kdb.Layout, cell: kdb.Cell, sc: g.Subckt) -> list[tuple[g.Inst, kdb.Instance]]:
    gds_insts = [i for i in cell.each_inst() if layout.cell(i.cell_index).name != "rails"]
    assert len(gds_insts) == len(sc.insts), (cell.name, len(gds_insts), len(sc.insts))
    want = [_expected_cell_name(ni) for ni in sc.insts]
    got = [layout.cell(gi.cell_index).name for gi in gds_insts]
    if got == want:
        return list(zip(sc.insts, gds_insts))
    by_ref: dict[str, list[kdb.Instance]] = {}
    for gi in gds_insts:
        by_ref.setdefault(layout.cell(gi.cell_index).name, []).append(gi)
    for group in by_ref.values():
        group.sort(key=lambda gi: (gi.trans.disp.x, gi.trans.disp.y))
    out: list[tuple[g.Inst, kdb.Instance]] = []
    for ni, cname in zip(sc.insts, want):
        if ni.name.startswith("XS[") and ni.name.endswith("]"):
            out.append((ni, by_ref[cname][int(ni.name[3:-1])]))
        else:
            assert len(by_ref[cname]) == 1, (cell.name, ni.name, cname, len(by_ref[cname]))
            out.append((ni, by_ref[cname][0]))
    return out


def _resolved_supply_map(nl: dict[str, g.Subckt], top_name: str) -> dict[tuple[str, str, str], str]:
    flat = g.flat_nets(nl, top=top_name)
    term_supply: dict[tuple[str, str, str], str] = {}
    for entry in flat.values():
        leaf_names = {a.rsplit("/", 1)[-1] for a in entry["aliases"]}
        supplies = leaf_names & set(g.SUPPLY_NETS)
        assert len(supplies) <= 1, f"netlist shorts supplies together: {entry['aliases'][:4]}"
        if supplies:
            snet = next(iter(supplies))
            for t in entry["terminals"]:
                term_supply[t] = snet
    return term_supply


def netlist_supply_pads(
    layout: kdb.Layout,
    top_name: str = g.TOP,
    netlist_path: str = g.NETLIST,
    nl: dict[str, g.Subckt] | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Independently derive periphery supply D/S and B pad coordinates from ``layout`` and the SPICE netlist.

    Resolves flat nets across every placed instance in ``nl`` (never assuming device polarity) and reads pad
    centres from the drawn transistor cells in ``layout`` (never from ``Gen.dev_pts`` or generator wiring tables).
    Returns ``{"ds": {"VDD": [...], "VSS": [...]}, "ties": {"VDD": [...], "VSS": [...]}}``.
    """
    parsed = nl if nl is not None else g.parse_netlist(netlist_path)
    term_supply = _resolved_supply_map(parsed, top_name)
    pad_cache: dict[int, dict[str, kdb.Point]] = {}
    ds: dict[str, list[dict]] = {"VDD": [], "VSS": []}
    ties: dict[str, list[dict]] = {"VDD": [], "VSS": []}

    def walk(sub: str, path: tuple[str, ...], trans: kdb.Trans) -> None:
        cell = layout.cell(sub)
        for ni, gi in _pair_instances(layout, cell, parsed[sub]):
            if ni.ref in ("bitcell", "bl_pair"):
                continue
            tt = trans * gi.trans
            if ni.ref in g.DEVICE_REFS:
                dc = layout.cell(gi.cell_index)
                ci = dc.cell_index()
                if ci not in pad_cache:
                    pad_cache[ci] = _device_pad_centers(layout, dc)
                p_str = "/".join(path)
                for term, lpt in pad_cache[ci].items():
                    snet = term_supply.get((p_str, ni.name, term))
                    if snet is None:
                        continue
                    pt = tt * lpt
                    rec = {
                        "net": snet,
                        "path": p_str,
                        "device": ni.name,
                        "term": term,
                        "x": round(pt.x * layout.dbu, 3),
                        "y": round(pt.y * layout.dbu, 3),
                    }
                    if term in ("D", "S"):
                        ds[snet].append(rec)
                    elif term == "B":
                        ties[snet].append(rec)
            else:
                walk(ni.ref, path + (ni.name,), tt)

    walk(top_name, (), kdb.Trans())
    return {"ds": ds, "ties": ties}


def supply_ds_terminals(
    layout: kdb.Layout,
    top_name: str = g.TOP,
    netlist_path: str = g.NETLIST,
    nl: dict[str, g.Subckt] | None = None,
) -> dict[str, list[dict]]:
    """Netlist-expected periphery D/S supply pads per supply net (``VDD``, ``VSS``)."""
    return netlist_supply_pads(layout, top_name=top_name, netlist_path=netlist_path, nl=nl)["ds"]


def _trunks_from_layout(layout: kdb.Layout) -> dict[str, tuple[float, float]]:
    rails = layout.cell("rails")
    assert rails is not None, "layout has no 'rails' cell"
    lbl = layout.layer(*g.L_METAL5_LBL)
    pts: dict[str, tuple[float, float]] = {}
    for s in rails.shapes(lbl).each():
        if s.is_text() and s.text_string in g.SUPPLY_NETS:
            t = s.text
            pts[s.text_string] = (round(t.x * layout.dbu, 3), round(t.y * layout.dbu, 3))
    assert set(pts) == set(g.SUPPLY_NETS), f"expected VDD/VSS Metal5 labels in 'rails', found {sorted(pts)}"
    return pts


def analyse(
    layout: kdb.Layout,
    top: kdb.Cell,
    gen: g.Gen | None = None,
    netlist_path: str = g.NETLIST,
) -> dict:
    regions = {k: kdb.Region(top.begin_shapes_rec(layout.layer(*lp))).merged() for k, lp in _LAYERS.items()}
    trunk_pts = _trunks_from_layout(layout)
    if gen is not None and hasattr(gen, "trunk_x"):
        seeds = {net: (gen.trunk_x[net], trunk_pts[net][1]) for net in ("VDD", "VSS")}
    else:
        seeds = trunk_pts
    sel = {
        net: _grow(regions, kdb.Region(_box(seeds[net][0], seeds[net][1], 0.01)))
        for net in ("VDD", "VSS")
    }
    short = sum((sel["VDD"][k] & sel["VSS"][k]).count() for k in regions)

    nl = gen.nl if gen is not None else g.parse_netlist(netlist_path)
    pads = netlist_supply_pads(layout, top_name=top.name, netlist_path=netlist_path, nl=nl)

    ties = gen.tie_wiring if (gen is not None and hasattr(gen, "tie_wiring")) else (pads["ties"]["VDD"] + pads["ties"]["VSS"])
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

    ds_report: dict[str, dict] = {}
    for net in ("VDD", "VSS"):
        opp = "VSS" if net == "VDD" else "VDD"
        expected_list = pads["ds"][net]
        probe_reg = kdb.Region()
        for p in expected_list:
            probe_reg.insert(_box(p["x"], p["y"], 0.005))
        assert probe_reg.count() == len(expected_list), (net, probe_reg.count(), len(expected_list))
        on_own = probe_reg.interacting(sel[net]["m1"]).count()
        on_other = probe_reg.interacting(sel[opp]["m1"]).count()
        fl_count = len(expected_list) - on_own
        fl_samples: list[dict] = []
        if fl_count:
            missed = probe_reg - probe_reg.interacting(sel[net]["m1"])
            for p in expected_list:
                if not (kdb.Region(_box(p["x"], p["y"], 0.005)) & missed).is_empty():
                    fl_samples.append(p)
                    if len(fl_samples) >= 10:
                        break
        ds_report[net] = {
            "expected": len(expected_list),
            "on_own_rail": on_own,
            "on_other_rail": on_other,
            "floating": fl_count,
            "floating_samples": fl_samples,
        }

    # bitcell supply risers: one VSS and one VDD probe per cell, in global coordinates
    risers = {}
    if layout.cell("bitcell") is not None:
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
        for net in ("VDD", "VSS"):
            risers[net] = {
                "expected": g.COLS * g.ROWS,
                "on_rail": probes[net].interacting(sel[net]["m1"]).count(),
                "on_other_rail": probes[net].interacting(sel["VSS" if net == "VDD" else "VDD"]["m1"]).count(),
            }
    else:
        for net in ("VDD", "VSS"):
            risers[net] = {"expected": 0, "on_rail": 0, "on_other_rail": 0}

    return {
        "ties_expected": len(ties),
        "ties_on_own_rail": wired,
        "ties_on_other_rail": wrong,
        "ties_floating": len(floating),
        "floating_ties": floating[:10],
        "supply_ds_pads": ds_report,
        "vdd_vss_short_polygons": short,
        "bitcell_risers": risers,
        "polygons_on_rail": {net: {k: v.count() for k, v in sel[net].items()} for net in sel},
    }


def wordline_gap_clearance(layout: kdb.Layout, top: kdb.Cell, gen: g.Gen | None = None) -> dict:
    """Rail geometry inside the wordline fan-out gap (issue #102).

    The gap between the row decoder and the array holds the wordline Metal2 lanes and Metal3
    tracks. Only Metal4 and above may cross it; any rail shape on Metal1..Metal3 or a Via1..Via3
    inside it would sit on a wordline lane or track. The count is over the ``rails`` cell, whose
    shapes are all supply rails.
    """
    rails = layout.cell("rails")
    gap = kdb.Region(kdb.Box(round(-g.WL_FANOUT_GAP * _U), -(10**9), 0, 10**9))
    layers = dict(
        m1=g.bc.L_METAL1,
        v1=g.L_VIA1,
        m2=g.L_METAL2,
        v2=g.L_VIA2,
        m3=g.L_METAL3,
        v3=g.L_VIA3,
        v4=g.L_VIA4,
    )
    inside = {
        k: (kdb.Region(rails.begin_shapes_rec(layout.layer(*lp))) & gap).count()
        for k, lp in layers.items()
    }
    return {
        "gap_um": [-g.WL_FANOUT_GAP, 0.0],
        "rail_shapes_in_gap_below_metal4": inside,
        "total": sum(inside.values()),
    }
