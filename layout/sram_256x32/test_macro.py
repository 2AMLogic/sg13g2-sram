"""Macro generator tests: determinism, array count, pin set vs the netlist,
net-tracing of the array-interface routing (wordlines, bit lines) and of the
leaf-cell signal routing (flat-net resolution, router, per-cell connectivity).

    cd layout/sram_256x32 && uv run --with pytest --with klayout pytest -q test_macro.py
"""

import os
import random
import re
import sys
from functools import cache
from pathlib import Path

import klayout.db as kdb
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as g  # noqa: E402

LEF = os.path.join(g.HERE, "macro.lef")


@cache
def _cached_build():
    """Build the shared, read-only reference macro on first use."""
    return g.build()


def _built():
    """Copy the layout for tests that flatten or damage it. The generator is read-only."""
    original, gen, _ = _cached_build()
    layout = original.dup()
    return layout, gen, layout.cell("macro")


def _bytes(layout, path):
    layout.write(str(path), g.save_options())
    return path.read_bytes()


def test_deterministic(tmp_path):
    first = _bytes(_cached_build()[0], tmp_path / "a.gds")
    assert first == _bytes(g.build()[0], tmp_path / "b.gds")


def test_committed_gds_is_current(tmp_path):
    generated = _bytes(_cached_build()[0], tmp_path / "c.gds")
    assert generated == Path(g.GDS_PATH).read_bytes()


def test_bitcell_count_and_top():
    layout, _, top = _built()
    assert top.name == "macro"
    assert [c.name for c in layout.top_cells()] == ["macro"]
    bit = layout.cell("bitcell")
    n = 0
    for inst in top.begin_instances_rec():
        if inst.inst_cell().cell_index() == bit.cell_index():
            n += 1
    assert n == g.ROWS * g.COLS == 8192


def test_array_is_mirror_abutted():
    layout, _, _ = _built()
    pair = layout.cell("bl_pair")
    h = round(g.bc.H_CELL / g.DBU)
    ys = sorted(i.trans.disp.y - (h if i.trans.is_mirror() else 0) for i in pair.each_inst())
    assert len(ys) == 128 and all(b - a == h for a, b in zip(ys, ys[1:]))
    assert [i.trans.is_mirror() for i in pair.each_inst()].count(True) == 64


def test_pins_match_netlist_ports():
    ports = g.parse_netlist(g.NETLIST)["macro"].ports
    _, gen, _ = _built()
    assert sorted(p["name"] for p in gen.pin_list) == sorted(ports)


def test_lef_pins_match_netlist_ports():
    ports = set(g.parse_netlist(g.NETLIST)["macro"].ports)
    lef = open(LEF).read()
    assert re.search(r"^MACRO macro$", lef, re.M)
    pins = set(re.findall(r"^\s*PIN (\S+)$", lef, re.M))
    assert pins == ports


def test_bus_ends_present():
    _, gen, _ = _built()
    names = {p["name"] for p in gen.pin_list}
    assert {"A[7]", "A[0]", "D[31]", "D[0]", "Q[31]", "Q[0]"} <= names


# ---- array-interface routing: net tracing on the generated layout -------------
_CONN = (("poly", "cont"), ("cont", "m1"), ("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3"))


def _extract(mutate=None):
    """Flat connectivity of the generated layout (GatPoly-Cont-Metal1-Via1-Metal2-
    Via2-Metal3). ``mutate(layout, top)`` may damage the layout first."""
    layout, gen, top = _built()
    if mutate:
        mutate(layout, top)
    top.flatten(True)
    bc = g.bc
    names = dict(poly=bc.L_GATPOLY, cont=bc.L_CONT, m1=bc.L_METAL1, v1=g.L_VIA1,
                 m2=g.L_METAL2, v2=g.L_VIA2, m3=g.L_METAL3)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(layout, top, []))
    ly = {n: l2n.make_layer(layout.layer(*lp), n) for n, lp in names.items()}
    for a, b in _CONN:
        l2n.connect(ly[a], ly[b])
    for n in ly:
        l2n.connect(ly[n])
    l2n.extract_netlist()

    def net(layer, x, y):
        n = l2n.probe_net(ly[layer], kdb.DPoint(x, y))
        return None if n is None else n.cluster_id

    return gen, net


def _wl_ids(gen, net, rows):
    out = {}
    for r in rows:
        tx, ty = gen.wl_terms[r]
        out[r] = (net("poly", 1.0, gen.wl_y(r)), net("m1", tx, ty))
    return out


def _bl_ids(gen, net, cols):
    out = {}
    for c in cols:
        s, col = divmod(c, 2)
        for nm in (f"BL{col}", f"BLB{col}"):
            a = net("m1", gen.bl_stripe_x[nm] + s * 2 * g.bc.W_CELL, 100.3)
            ends = [net("m1", tx + s * 2 * g.bc.W_CELL, ty) for tx, ty in gen.bl_terms[nm]]
            out[(c, nm)] = (a, ends)
    return out


def _wl_ok(ids):
    return {r: a is not None and a == b for r, (a, b) in ids.items()}


def _bl_ok(ids):
    return {k: a is not None and len(ends) == 2 and all(e == a for e in ends) for k, (a, ends) in ids.items()}


def test_wordlines_connected_end_to_end():
    gen, net = _extract()
    ids = _wl_ids(gen, net, range(g.ROWS))
    ok = _wl_ok(ids)
    assert ok[0] and ok[127]
    assert all(ok.values()), [r for r, v in ok.items() if not v]
    # no wordline shorted to another wordline
    assert len({a for a, _ in ids.values()}) == g.ROWS


def test_bitlines_connected_end_to_end():
    gen, net = _extract()
    ids = _bl_ids(gen, net, range(g.COLS))
    ok = _bl_ok(ids)
    assert ok[(0, "BL0")] and ok[(0, "BLB0")] and ok[(63, "BL1")] and ok[(63, "BLB1")]
    assert all(ok.values()), [k for k, v in ok.items() if not v]
    # all 128 bit-line nets distinct from each other and from every wordline
    bl = {a for a, _ in ids.values()}
    wl = {a for a, _ in _wl_ids(gen, net, range(g.ROWS)).values()}
    assert len(bl) == 2 * g.COLS and not (bl & wl)


def _erase_at(cell, lp, x, y):
    layer = cell.layout().layer(*lp)
    hit = [sh for sh in cell.shapes(layer).each() if sh.dbox.contains(x, y)]
    assert hit, (cell.name, lp, x, y)
    for sh in hit:
        cell.shapes(layer).erase(sh)


def test_wordline_trace_has_teeth():
    def cut(layout, top):
        gen = _built()[1]  # the coordinates of the layout under test
        _erase_at(top, g.L_VIA2, g.WL_PAD_X, gen.wl_y(0))

    gen, net = _extract(cut)
    ok = _wl_ok(_wl_ids(gen, net, [0, 127]))
    assert not ok[0] and ok[127]


def test_bitline_trace_has_teeth():
    def cut(layout, top):
        gen = _built()[1]
        _erase_at(layout.cell("bit_slice"), g.L_VIA1, gen.bl_stripe_x["BL0"], g.BL_VIA_Y)

    gen, net = _extract(cut)
    ok = _bl_ok(_bl_ids(gen, net, [0, 63]))
    assert not ok[(0, "BL0")] and ok[(0, "BLB0")]


def test_every_periphery_device_has_a_body_tie():
    """Each transistor cell carries a tie Activ with a Cont and a Metal1 label for its bulk net."""
    layout, _, _ = _built()
    li = lambda lp: layout.layer(*lp)
    devs = [c for c in layout.each_cell() if c.name.startswith("sg13_lv_")]
    assert devs
    for c in devs:
        assert c.shapes(li(g.bc.L_ACTIV)).size() == 2, c.name  # channel + tie
        kind_p = "pmos" in c.name
        psd = [b for b in (s.box for s in c.shapes(li(g.bc.L_PSD)).each())]
        tie = sorted((s.box for s in c.shapes(li(g.bc.L_ACTIV)).each()), key=lambda b: b.left)[-1]
        in_psd = any(b.contains(tie.p1) and b.contains(tie.p2) for b in psd)
        assert in_psd == (not kind_p), c.name  # p-tap sits in pSD; n-tap does not


def test_tie_labels_name_the_netlist_bulk():
    layout, _, _ = _built()
    nets = {i.nets[3] for sc in g.parse_netlist(g.NETLIST).values() for i in sc.insts
            if i.ref in ("sg13_lv_nmos", "sg13_lv_pmos")}
    assert nets == {"VSS", "VDD"}
    texts = set()
    for c in layout.each_cell():
        if c.name.startswith("sg13_lv_") or c.name in g.Gen().nl:
            for s in c.shapes(layout.layer(*g.bc.L_METAL1_LBL)).each():
                texts.add(s.text_string)
    assert {"VSS", "VDD"} <= texts


def _analysis(mutate=None):
    import rails_check

    layout, gen, top = _built()
    if mutate:
        mutate(layout, gen)
    return rails_check.analyse(layout, top, gen), gen


def test_every_tie_and_riser_reaches_its_rail():
    res, gen = _analysis()
    assert res["ties_expected"] == len(gen.tie_wiring) > 2000
    assert res["ties_on_own_rail"] == res["ties_expected"], res["floating_ties"]
    assert res["ties_on_other_rail"] == 0 and res["ties_floating"] == 0
    assert res["vdd_vss_short_polygons"] == 0
    for net in ("VDD", "VSS"):
        assert res["bitcell_risers"][net]["on_rail"] == g.ROWS * g.COLS, net
        assert res["bitcell_risers"][net]["on_other_rail"] == 0, net


def test_removing_a_tie_via_floats_that_tie():
    """Teeth: delete the Via2 of one tie's stub; that tie (at least) must stop reaching its rail."""
    def cut(layout, gen):
        w = gen.tie_wiring[0]
        rails = layout.cell("rails")
        li = layout.layer(*g.L_VIA2)
        hit = [s for s in rails.shapes(li).each()
               if abs(s.bbox().center().x * g.DBU - w["lane_x"]) < 0.01 and abs(s.bbox().center().y * g.DBU - w["lane_y"]) < 0.01]
        assert hit, "tie's Via2 not found"
        for s in hit:
            rails.shapes(li).erase(s)

    res, _ = _analysis(cut)
    assert res["ties_floating"] >= 1
    assert res["ties_on_own_rail"] < res["ties_expected"]


def test_rail_pitch_does_not_alias_the_wordline_lane_pitch():
    assert g.LANE_PITCH == 0.42 and g.RAIL_LANE_PITCH != g.LANE_PITCH
    assert g.WL_FANOUT_GAP == round(2 * g.LANE_MARGIN + (g.ROWS - 1) * 0.42, 3)


def test_no_rail_shape_below_metal4_in_the_wordline_gap():
    import rails_check

    layout, gen, top = _built()
    res = rails_check.wordline_gap_clearance(layout, top, gen)
    assert res["total"] == 0, res
    # the lanes do cross the gap, on Metal4 only
    gap = g.WL_FANOUT_GAP
    m4 = layout.cell("rails").dbbox_per_layer(layout.layer(*g.L_METAL4))
    assert m4.left < -gap and m4.right > 0


def test_gap_clearance_check_has_teeth():
    import rails_check

    layout, gen, top = _built()
    gen.box(layout.cell("rails"), g.L_VIA2, -10.0, 20.0, -9.81, 20.19)
    assert rails_check.wordline_gap_clearance(layout, top, gen)["rail_shapes_in_gap_below_metal4"]["v2"] == 1


# ---- the rails obstacle model (issue #163) ---------------------------------------
def test_obstacle_clear_rejects_other_net_and_signal_shapes():
    obs = g.Obstacles()
    obs.add("VSS", kdb.DBox(0.0, 0.0, 1.0, 0.2))
    assert not obs.clear("VDD", kdb.DBox(0.5, 0.05, 1.5, 0.25))  # interior overlap
    assert not obs.clear("VDD", kdb.DBox(1.0, 0.0, 2.0, 0.2))  # even a bare edge touch violates M2.b
    assert not obs.clear("VDD", kdb.DBox(1.21, 0.0, 2.0, 0.2))  # 0.21 away: still inside the 0.22 check margin
    assert obs.clear("VDD", kdb.DBox(1.22, 0.0, 2.0, 0.2))  # past the check margin it is clear
    sig = g.Obstacles()
    sig.add(None, kdb.DBox(0.0, 0.0, 1.0, 0.2))  # a signal shape blocks every net
    assert not sig.clear("VDD", kdb.DBox(0.5, 0.05, 1.5, 0.25))
    assert not sig.clear("VSS", kdb.DBox(0.5, 0.05, 1.5, 0.25))


def test_obstacle_clear_same_net_merge_and_sliver():
    obs = g.Obstacles()
    obs.add("VSS", kdb.DBox(0.8, 0.0, 1.8, 0.2))
    assert obs.clear("VSS", kdb.DBox(0.0, 0.0, 1.0, 0.2))  # merged: the overlap is a full stub width deep
    obs2 = g.Obstacles()
    obs2.add("VSS", kdb.DBox(0.9, 0.0, 1.9, 0.2))
    assert not obs2.clear("VSS", kdb.DBox(0.0, 0.0, 1.0, 0.2))  # a 0.1 um-deep corner overlap is a sliver under M2.a


def test_obstacle_hash_spans_its_grid_cells():
    obs = g.Obstacles()
    obs.add("VDD", kdb.DBox(4.9, 4.9, 5.1, 5.1))  # straddles the 5 um grid line
    assert {(0, 0), (1, 0), (0, 1), (1, 1)} <= set(obs.m2)
    assert not obs.clear("VSS", kdb.DBox(5.0, 5.0, 5.5, 5.2))


def test_obstacle_clear3_and_cross_layer_independence():
    obs = g.Obstacles()
    obs.add_m3(kdb.DBox(0.0, 0.0, 1.0, 0.2))
    assert not obs.clear3(kdb.DBox(0.5, 0.05, 1.5, 0.25))
    assert not obs.clear3(kdb.DBox(1.0, 0.0, 2.0, 0.2))  # even a bare edge touch violates M3.b
    assert not obs.clear3(kdb.DBox(1.21, 0.0, 2.0, 0.2))  # 0.21 away: still inside the 0.22 check margin
    assert obs.clear3(kdb.DBox(1.22, 0.0, 2.0, 0.2))  # past the check margin it is clear
    assert any(obs.m3.values())
    assert obs.clear("VSS", kdb.DBox(0.5, 0.05, 1.5, 0.25))  # the Metal3 hash does not gate the Metal2 check


# ---- flat-net resolution (issue #104) -------------------------------------------
def _device_count(nl, name):
    n = 0
    for inst in nl[name].insts:
        if inst.ref in g.DEVICE_REFS:
            n += 1
        elif inst.ref in nl and inst.ref != "bitcell":
            n += _device_count(nl, inst.ref)
    return n


def test_flat_nets_partition_every_device_terminal():
    nl = g.parse_netlist(g.NETLIST)
    flat = g.flat_nets(nl)
    terms = [t for v in flat.values() for t in v["terminals"]]
    assert len(terms) == len(set(terms)) == 4 * _device_count(nl, g.TOP) == 4 * 2796


def test_flat_nets_resolve_across_the_hierarchy():
    flat = g.flat_nets(g.parse_netlist(g.NETLIST))
    pre = flat["PRE_B"]  # control output -> the precharge gates of all 32 slices
    assert not pre["excluded"]
    slices = {t[0].split("/")[0] for t in pre["terminals"] if t[0].startswith("XS[")}
    assert len(slices) == 32
    assert sum(1 for t in pre["terminals"] if t[0].startswith("XS[") and t[2] == "G") == 32 * 2 * 3
    assert any(t[0].startswith("XCTL") for t in pre["terminals"])
    # the latched address bit AL[0] reaches both the address latch and the control
    al0 = {t[0].split("/")[0] for t in flat["AL[0]"]["terminals"]}
    assert {"XAL", "XCTL"} <= al0
    # a net internal to an instance is named by its path
    assert any(k.startswith("XAL/") and k.endswith("/N1") for k in flat)


def test_flat_nets_exclude_supply_bit_lines_and_wordlines():
    flat = g.flat_nets(g.parse_netlist(g.NETLIST))
    why = {k: v["excluded"] for k, v in flat.items()}
    assert why["VDD"] == why["VSS"] == "supply"
    assert why["WL[0]"] == why["WL[127]"] == "wordline"
    bl = [k for k in flat if g.excluded_net(k.rsplit("/", 1)[-1]) == "bit line"]
    assert bl and all(why[k] == "bit line" for k in bl)
    assert not why["PRE_B"] and not why["D[0]"] and not why["DOUT[3]"]


# ---- the router (issue #104) ----------------------------------------------------
def _scratch_extract(layout, cell, points):
    """Net ids of ``points`` ({name: (layer, x, y)}) over Metal2-Via2-Metal3 of ``cell`` (Metal1/Via1 landings aside)."""
    names = dict(m2=g.L_METAL2, v2=g.L_VIA2, m3=g.L_METAL3)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(layout, cell, []))
    ly = {n: l2n.make_layer(layout.layer(*lp), n) for n, lp in names.items()}
    l2n.connect(ly["m2"], ly["v2"])
    l2n.connect(ly["v2"], ly["m3"])
    for n in ly:
        l2n.connect(ly[n])
    l2n.extract_netlist()
    out = {}
    for k, (layer, x, y) in points.items():
        n = l2n.probe_net(ly[layer], kdb.DPoint(x, y))
        out[k] = None if n is None else n.cluster_id
    return out


def _draw_nets(nets, box=3000):
    """Route ``{name: [lattice nodes]}`` on an empty MazeRouter and draw it; returns (layout cell, routed ok, shapes)."""
    gen = g.Gen()
    cell = gen.layout.create_cell("scratch")
    mz = g.MazeRouter(0, 0, box, box)
    ids = {n: k + 1 for k, n in enumerate(nets)}
    for n, ts in nets.items():
        for t in ts:
            mz.pad(0, t, ids[n])
    ok = {n: mz.route_net(ids[n], ts) for n, ts in nets.items()}
    regions = {}
    for n in nets:
        drawn, _ = gen.draw_shapes(cell, mz.shapes.get(ids[n], []))
        for t in nets[n]:
            gen.rect(cell, g.L_METAL2, t[0] * g.STEP * g.DBU, t[1] * g.STEP * g.DBU, g.M2_W, g.M2_W)
        regions[n] = drawn
    return gen, cell, ok, regions


def test_router_crosses_two_nets_without_a_short():
    a, b = [(4, 30), (56, 30)], [(30, 4), (30, 56)]  # an X: the two nets must cross
    gen, cell, ok, regions = _draw_nets({"A": a, "B": b})
    assert ok == {"A": True, "B": True}
    # they do cross in plan view (one on each layer) ...
    assert not ((regions["A"][1] & regions["B"][0]).is_empty() and (regions["A"][0] & regions["B"][1]).is_empty())
    # ... and extraction keeps them apart while joining each one's two ends
    pts = {f"{n}{k}": ("m2", t[0] * g.STEP * g.DBU, t[1] * g.STEP * g.DBU) for n, ts in (("A", a), ("B", b)) for k, t in enumerate(ts)}
    ids = _scratch_extract(gen.layout, cell, pts)
    assert ids["A0"] == ids["A1"] is not None and ids["B0"] == ids["B1"] is not None
    assert ids["A0"] != ids["B0"]


def test_router_single_terminal_net_needs_no_wire_and_unroutable_is_reported():
    mz = g.MazeRouter(0, 0, 3000, 3000)
    assert mz.route_net(1, [(10, 10)]) and not mz.shapes.get(1)
    # a terminal boxed in by another net's hard obstacles cannot be joined: reported, not hidden
    mz = g.MazeRouter(0, 0, 3000, 3000)
    mz.block(0, 0.5, 0.5, 1.5, 1.5)
    mz.block(1, 0.5, 0.5, 1.5, 1.5)
    mz.pad(0, (20, 20), 1)
    mz.pad(0, (50, 50), 1)
    assert not mz.route_net(1, [(20, 20), (50, 50)])


def test_router_keeps_spacing_between_nets():
    gen, cell, ok, regions = _draw_nets({"A": [(4, 30), (56, 30)], "B": [(4, 40), (56, 40)], "C": [(10, 4), (10, 56)]})
    assert all(ok.values())
    for l in (0, 1):
        # nets are separate polygons at least M2.b / M3.b apart
        for x, y in (("A", "B"), ("A", "C"), ("B", "C")):
            assert regions[x][l].merged().separation_check(regions[y][l].merged(), g.dbu(g.M2_SPACE)).count() == 0, (x, y, l)


def _path_cost(path):
    """Cost of a router path under the generator's own model: ``VIA_COST`` to change layer, 1 along the layer's
    preferred direction (Metal2 vertical, Metal3 horizontal), ``WRONG_WAY`` against it."""
    return sum(g.VIA_COST if l != l2 else (1 if (i == i2) == (l == 0) else g.WRONG_WAY)
               for (l, i, j), (l2, i2, j2) in zip(path, path[1:]))


def test_router_aimed_and_unaimed_searches_agree():
    """``MazeRouter.connect`` serves both of ``route_net``'s modes from one search. Aimed with ``toward`` it is an A*
    whose Manhattan heuristic never overestimates a lattice path (the cheapest step costs 1), so for a single goal it
    must agree with the unaimed Dijkstra on whether the goal is reachable and on what a cheapest path there costs."""
    start, goal, routable = (4, 4), (52, 52), 0
    for seed in range(12):
        rnd = random.Random(seed)
        # one obstacle map, two fresh routers: only the search differs between the pair
        bars = [(rnd.randrange(2), rnd.randrange(6, 50), rnd.randrange(6, 50), rnd.randrange(2, 9)) for _ in range(20)]
        pair = []
        for _ in range(2):
            mz = g.MazeRouter(0, 0, 3000, 3000)
            s = g.STEP * g.DBU
            for l, bi, bj, n in bars:
                mz.block(l, bi * s, bj * s, (bi + n) * s, bj * s + g.M2_W)
            mz.pad(0, start, 1)
            mz.pad(0, goal, 1)
            pair.append(mz)
        unaimed = pair[0].connect(1, {(0, *start)}, {(0, *goal)})
        aimed = pair[1].connect(1, {(0, *start)}, {(0, *goal)}, toward=goal)
        assert (unaimed is None) == (aimed is None), seed
        if unaimed is None:
            continue
        routable += 1
        assert unaimed[0] == aimed[0] == (0, *start) and unaimed[-1] == aimed[-1] == (0, *goal), seed
        assert _path_cost(unaimed) == _path_cost(aimed), (seed, _path_cost(unaimed), _path_cost(aimed))
    assert routable >= 8, f"only {routable}/12 obstacle maps were routable: the comparison is not being exercised"


def test_router_rejects_aimed_search_at_more_than_one_goal():
    """``connect``'s ``toward`` aims an A* whose Manhattan heuristic is admissible only for the one node it aims at:
    with ``WRONG_WAY`` steps on the lattice, a goal set holding more than ``toward`` alone can pop a
    costlier-than-cheapest goal first (start (4, 4), goals {(0, 4, 12), (0, 8, 4)}, toward (8, 4): aimed cost 16 vs
    optimal 8), silently. The aimed mode therefore asserts ``goals == {(0, *toward)}``; the unaimed Dijkstra over
    any goal set, on either layer, is unaffected, as is the aimed singleton the generator itself calls."""
    start = (4, 4)
    mz = g.MazeRouter(0, 0, 3000, 3000)
    with pytest.raises(AssertionError):
        mz.connect(1, {(0, *start)}, {(0, 4, 12), (0, 8, 4)}, toward=(8, 4))
    with pytest.raises(AssertionError):
        mz.connect(1, {(0, *start)}, {(0, 20, 20)}, toward=(30, 30))
    assert mz.connect(1, {(0, *start)}, {(0, 8, 4)}, toward=(8, 4)) is not None
    assert mz.connect(1, {(0, *start)}, {(0, 4, 12), (0, 8, 4)}) is not None
    assert mz.connect(1, {(0, *start)}, {(1, 4, 12), (1, 8, 4)}) is not None
    assert mz.connect(1, {(0, *start)}, {(0, 20, 20)}) is not None


# ---- leaf-cell nets on the generated layout (issue #104) ----------------------------
def _extract_cell(layout, cell):
    """Hierarchical connectivity of one leaf cell: Cont-Metal1-Via1-Metal2-Via2-Metal3."""
    names = dict(cont=g.bc.L_CONT, m1=g.bc.L_METAL1, v1=g.L_VIA1, m2=g.L_METAL2, v2=g.L_VIA2, m3=g.L_METAL3)
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(layout, cell, []))
    ly = {n: l2n.make_layer(layout.layer(*lp), n) for n, lp in names.items()}
    for a, b in (("cont", "m1"), ("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3")):
        l2n.connect(ly[a], ly[b])
    for n in ly:
        l2n.connect(ly[n])
    l2n.extract_netlist()

    def net(x, y):
        n = l2n.probe_net(ly["m1"], kdb.DPoint(x, y))
        return None if n is None else n.cluster_id

    return net


def _leaf_nets(layout, gen, name):
    """{net: [cluster id of each of its terminals]} for the nets drawn in leaf cell ``name``."""
    net = _extract_cell(layout, layout.cell(name))
    return {n: [net(x, y) for x, y in pts] for n, pts in gen.leaf_terms[name].items()}


def test_leaf_cell_nets_are_one_net_each_and_never_short():
    layout, gen, _ = _built()
    assert set(gen.leaf_report) == set(g.LEAF_ROUTED)
    n_checked = 0
    for name in g.LEAF_ROUTED:
        ids = _leaf_nets(layout, gen, name)
        assert ids, name
        for n, cl in ids.items():
            assert None not in cl and len(set(cl)) == 1, (name, n, cl)
        reps = [cl[0] for cl in ids.values()]
        assert len(set(reps)) == len(reps), (name, "two netlist nets share a cluster")
        n_checked += len(ids)
    assert n_checked == sum(len(r["routed"]) for r in gen.leaf_report.values()) == 54


def test_leaf_cell_undrawn_nets_are_listed():
    _, gen, _ = _built()
    # every net of every leaf cell is either drawn, listed as undrawn, or excluded/single-terminal by rule
    for name in g.LEAF_ROUTED:
        rep = gen.leaf_report[name]
        nets = {n for inst in gen.nl[name].insts if inst.ref in g.DEVICE_REFS for n in inst.nets[:3]}
        listed = set(rep["routed"]) | set(rep["failed"]) | set(rep["single_terminal"]) | set(rep["excluded"])
        assert listed == nets, (name, nets ^ listed)
    # every leaf-cell net is drawn (issue #159 joined the column mux's BLBM, the last undrawn one)
    undrawn = {(name, n) for name in g.LEAF_ROUTED for n in gen.leaf_report[name]["failed"]}
    assert undrawn == set(), undrawn
    assert gen.leaf_report["column_mux"]["routed"]["BLBM"] == 4
    assert gen.leaf_report["inv"]["routed"] == {"A": 2, "Y": 2}
    assert gen.leaf_report["precharge"]["excluded"]["BL"]["reason"] == "bit line"


def test_column_path_ties_recorded_once_per_device():
    # the pads pass only draws landings; the ties are registered once, with the wires (issue #224)
    _, gen, _ = _built()
    for name in g.COLPATH_CELLS:
        ties = gen.leaf_ties[name]
        assert len(ties) == len(set(ties)), (name, "a device's tie is recorded more than once")
        assert set(ties) == {pts["B"] for pts in gen.dev_pts[name].values()}, name


def test_column_mux_blbm_is_one_net_and_has_teeth():
    # the bit-line jogs are pushed below the BLBM terminal bands (``blbm_reserve``) so the net is
    # joined; cutting any one of its traces must split it again (issue #159)
    def probe(mutate):
        layout, gen, _ = _built()
        if mutate:
            x, y = gen.leaf_terms["column_mux"]["BLBM"][0]
            _erase_at(layout.cell("column_mux"), g.L_VIA1, x, y)
        return _leaf_nets(layout, gen, "column_mux")["BLBM"]

    assert len(set(probe(False))) == 1
    assert len(set(probe(True))) > 1


def test_column_mux_blbm_has_teeth_via2():
    layout, gen, _ = _built()
    v = next(v for v in gen.leaf_vias["column_mux"] if v["net"] == "BLBM")
    _erase_at(layout.cell("column_mux"), g.L_VIA2, v["x"], v["y"])
    ids = _leaf_nets(layout, gen, "column_mux")
    assert len(set(ids["BLBM"])) > 1, v


def test_leaf_cell_trace_has_teeth_via1_landing():
    def probe(mutate):
        layout, gen, _ = _built()
        if mutate:
            x, y = gen.leaf_terms["nand2"]["Y"][0]
            _erase_at(layout.cell("nand2"), g.L_VIA1, x, y)
        return _leaf_nets(layout, gen, "nand2")

    assert len(set(probe(False)["Y"])) == 1
    cut = probe(True)
    assert len(set(cut["Y"])) > 1 and len(set(cut["A"])) == 1


def test_leaf_cell_trace_has_teeth_via2():
    layout, gen, _ = _built()
    # leaf cells only: a hierarchical cell's via list holds its children's vias, drawn in the children
    name, v = next((n, vs[0]) for n, vs in sorted(gen.leaf_vias.items()) if vs and n in g.LEAF_ROUTED)
    _erase_at(layout.cell(name), g.L_VIA2, v["x"], v["y"])
    ids = _leaf_nets(layout, gen, name)
    assert len(set(ids[v["net"]])) > 1, (name, v)


# ---- nets between the leaf cells of the latch and control cells (issue #106) ---------
_HIER = {}


def _hier_build():
    if not _HIER:
        _HIER["layout"], _HIER["gen"], _ = _built()
    return _HIER["layout"], _HIER["gen"]


def _flat_net(lay, name):
    """Flat connectivity of ``name`` (the cluster ids of a hierarchical extraction are local to each cell)."""
    flat = lay.dup()
    flat.cell(name).flatten(True)
    return _extract_cell(flat, flat.cell(name))


def _hier_points(gen, name):
    """{label: [(x, y) Metal1 point in ``name``'s frame]}: every landing of a routed leaf-cell net, labelled with the net of
    ``name`` it belongs to (the net its instance port is wired to, or ``instance/net`` for a net internal to the leaf)."""
    pts: dict[str, list[tuple[float, float]]] = {}
    for inst in gen.nl[name].insts:
        if inst.ref not in gen.nl or inst.ref in g.DEVICE_REFS:
            continue
        dx, dy = (v * g.DBU for v in gen.place_of[name][inst.name])
        port_net = dict(zip(gen.nl[inst.ref].ports, inst.nets))
        for n, ps in gen.leaf_terms[inst.ref].items():
            label = port_net.get(n, f"{inst.name}/{n}")
            pts.setdefault(label, []).extend((x + dx, y + dy) for x, y in ps)
    for n, ps in gen.hier_terms[name].items():
        pts.setdefault(n, []).extend(ps)
    return pts


def test_hier_cell_nets_are_one_net_each_and_never_short():
    layout, gen = _hier_build()
    assert set(gen.hier_report) == set(g.HIER_ROUTED)
    for name in g.HIER_ROUTED:
        net = _flat_net(layout, name)
        pts = _hier_points(gen, name)
        ids = {label: {net(x, y) for x, y in ps} for label, ps in pts.items()}
        for label, cl in ids.items():
            assert None not in cl and len(cl) == 1, (name, label, cl)
        reps = [next(iter(cl)) for cl in ids.values()]
        assert len(set(reps)) == len(reps), (name, "two nets share a cluster")
        for n in gen.hier_report[name]["routed"]:
            assert n in ids, (name, n)
        # every drawn net joins one terminal per instance port
        assert gen.hier_report[name]["routed"], name


def test_hier_cell_undrawn_nets_are_listed():
    _, gen = _hier_build()
    for name in g.HIER_ROUTED:
        rep = gen.hier_report[name]
        nets = {n for inst in gen.nl[name].insts if inst.ref in gen.nl and inst.ref not in g.DEVICE_REFS for n in inst.nets}
        listed = set(rep["routed"]) | set(rep["failed"]) | set(rep["single_terminal"]) | set(rep["excluded"])
        assert listed == nets, (name, nets ^ listed)


def _hier_split(name, erase_lp, pick):
    """Cluster ids per label after erasing, in a copy of the layout, the shape ``pick(gen, layout)`` -> (x, y) names."""
    layout, gen = _hier_build()
    lay = layout.dup()
    cell = lay.cell(name)
    pts = _hier_points(gen, name)
    net = _flat_net(lay, name)
    assert all(len({net(x, y) for x, y in ps}) == 1 for ps in pts.values())
    x, y = pick(gen, layout)
    _erase_at(cell, erase_lp, x, y)
    net = _flat_net(lay, name)
    return {label: {net(x, y) for x, y in ps} for label, ps in pts.items()}


def test_hier_cell_trace_has_teeth_via2():
    def pick(gen, layout):
        sh = next(iter(layout.cell("control").shapes(layout.layer(*g.L_VIA2)).each()))
        return sh.dbox.center().x, sh.dbox.center().y

    after = _hier_split("control", g.L_VIA2, pick)
    assert any(len(c) > 1 for c in after.values())


def test_hier_cell_trace_has_teeth_wire():
    def pick(gen, layout):
        cell = layout.cell("control")
        sh = max(cell.shapes(layout.layer(*g.L_METAL3)).each(), key=lambda s: s.dbox.width())
        return sh.dbox.center().x, sh.dbox.center().y

    after = _hier_split("control", g.L_METAL3, pick)
    assert any(len(c) > 1 for c in after.values())


# ---- nets between the child cells of the decoder (issue #105) ---------------------------
def test_decoder_nets_are_all_drawn_and_listed():
    _, gen = _hier_build()
    decoder = ("predec3", "predec4", "wl_drivers", "row_decoder")
    assert set(decoder) <= set(g.HIER_ROUTED) and "wl_driver" in g.LEAF_ROUTED
    assert {n: gen.hier_report[n]["failed"] for n in decoder} == {n: [] for n in decoder}
    # the wordlines and the supply are not signal-routed here
    assert {"VDD", "VSS", "WL[0]", "WL[127]"} <= set(gen.hier_report["row_decoder"]["excluded"])
    # the 8 + 16 predecoder outputs reach the wordline drivers
    routed = gen.hier_report["row_decoder"]["routed"]
    assert sum(1 for k in routed if k.startswith(("X[", "Y["))) == 24
    assert set(gen.hier_report["wl_drivers"]["routed"]) == {f"X[{i}]" for i in range(8)} | {f"Y[{i}]" for i in range(16)} | {"WLEN"}


def test_decoder_trace_has_teeth_via2():
    """Cutting a Via2 of a net inside ``predec3`` splits that net: the connectivity check can fail."""
    def pick(gen, layout):
        sh = next(iter(layout.cell("predec3").shapes(layout.layer(*g.L_VIA2)).each()))
        return sh.dbox.center().x, sh.dbox.center().y

    after = _hier_split("predec3", g.L_VIA2, pick)
    assert any(len(c) > 1 for c in after.values())


# ---- periphery supply D/S terminal routing (issue #231) ---------------------------------
def _periphery_rail_m1_shapes(rails_cell: kdb.Cell, lm1: int) -> list:
    arr = kdb.DBox(0.0, 0.0, g.COLS * g.bc.W_CELL, g.ROWS * g.bc.H_CELL)
    return [sh for sh in rails_cell.shapes(lm1).each() if not arr.contains(sh.dbox.center())]


def test_every_supply_ds_pad_reaches_its_rail():
    import rails_check

    layout, gen, top = _built()
    res = rails_check.analyse(layout, top, gen)
    assert res["supply_ds_pads"]["VDD"] == {
        "expected": 1038,
        "on_own_rail": 1038,
        "on_other_rail": 0,
        "floating": 0,
        "floating_samples": [],
    }
    assert res["supply_ds_pads"]["VSS"] == {
        "expected": 620,
        "on_own_rail": 620,
        "on_other_rail": 0,
        "floating": 0,
        "floating_samples": [],
    }
    assert res["vdd_vss_short_polygons"] == 0
    # Independent layout+netlist-only check (gen=None) reaches the identical verdict
    indep = rails_check.analyse(layout, top)
    assert indep["supply_ds_pads"] == res["supply_ds_pads"]
    assert indep["ties_expected"] == indep["ties_on_own_rail"] == 2796
    assert indep["ties_floating"] == 0 and indep["ties_on_other_rail"] == 0
    assert indep["vdd_vss_short_polygons"] == 0


def test_supply_ds_probe_detects_unrouted_ds_while_ties_pass():
    """Removing the periphery D/S Metal1 bridges from ``rails`` reproduces the pre-#231 state on the identical
    expected terminal set: all 2,796 body ties and 16,384 risers still pass, while all 1,038 VDD and 620 VSS
    periphery D/S pads are detected as floating."""
    import rails_check

    routed_layout, _, _ = _built()
    expected_routed = rails_check.supply_ds_terminals(routed_layout)

    unrouted_layout, _, unrouted_top = _built()
    rails = unrouted_layout.cell("rails")
    lm1 = unrouted_layout.layer(*g.bc.L_METAL1)
    straps = _periphery_rail_m1_shapes(rails, lm1)
    assert len(straps) == 1038 + 620
    for sh in straps:
        rails.shapes(lm1).erase(sh)

    expected_unrouted = rails_check.supply_ds_terminals(unrouted_layout)
    assert expected_unrouted == expected_routed

    res = rails_check.analyse(unrouted_layout, unrouted_top)
    assert res["ties_expected"] == res["ties_on_own_rail"] == 2796
    assert res["ties_floating"] == 0 and res["ties_on_other_rail"] == 0
    assert res["bitcell_risers"]["VDD"]["on_rail"] == g.ROWS * g.COLS
    assert res["bitcell_risers"]["VSS"]["on_rail"] == g.ROWS * g.COLS
    assert res["vdd_vss_short_polygons"] == 0
    assert res["supply_ds_pads"]["VDD"]["expected"] == 1038
    assert res["supply_ds_pads"]["VDD"]["on_own_rail"] == 0
    assert res["supply_ds_pads"]["VDD"]["on_other_rail"] == 0
    assert res["supply_ds_pads"]["VDD"]["floating"] == 1038
    assert res["supply_ds_pads"]["VSS"]["expected"] == 620
    assert res["supply_ds_pads"]["VSS"]["on_own_rail"] == 0
    assert res["supply_ds_pads"]["VSS"]["on_other_rail"] == 0
    assert res["supply_ds_pads"]["VSS"]["floating"] == 620


def test_removing_one_supply_ds_strap_floats_only_that_pad():
    """Teeth: sever one VDD and one VSS D/S Metal1 bridge; each floats only that single pad while ties stay wired."""
    import rails_check

    layout, gen, top = _built()
    rails = layout.cell("rails")
    vdd_w = next(w for w in gen.ds_wiring if w["net"] == "VDD")
    vss_w = next(w for w in gen.ds_wiring if w["net"] == "VSS")
    for w in (vdd_w, vss_w):
        mx = 0.5 * (w["x"] + w["tie_x"])
        _erase_at(rails, g.bc.L_METAL1, mx, w["y"])
    res = rails_check.analyse(layout, top, gen)
    assert res["ties_floating"] == 0
    assert res["supply_ds_pads"]["VDD"]["floating"] == 1
    assert res["supply_ds_pads"]["VDD"]["on_own_rail"] == 1037
    assert res["supply_ds_pads"]["VSS"]["floating"] == 1
    assert res["supply_ds_pads"]["VSS"]["on_own_rail"] == 619
    assert res["vdd_vss_short_polygons"] == 0


def test_supply_ds_probe_catches_wrong_rail_and_vdd_vss_short():
    """Teeth: wiring a VSS D/S pad to a VDD tie flags ``on_other_rail``; bridging the rails flags a short."""
    import rails_check

    layout, gen, top = _built()
    rails = layout.cell("rails")
    vss_w = next(w for w in gen.ds_wiring if w["net"] == "VSS")
    vdd_tie = min(
        (t for t in gen.tie_wiring if t["net"] == "VDD"),
        key=lambda t: abs(t["x"] - vss_w["x"]) + abs(t["y"] - vss_w["y"]),
    )
    _erase_at(rails, g.bc.L_METAL1, 0.5 * (vss_w["x"] + vss_w["tie_x"]), vss_w["y"])
    # Bridge the isolated VSS D/S pad directly to the VDD tie on Metal1 (isolated from VSS trunk, so no trunk short)
    gen.seg(rails, g.bc.L_METAL1, g.bc.M1_W, vss_w["x"], vss_w["y"], vss_w["x"], vdd_tie["y"])
    gen.seg(rails, g.bc.L_METAL1, g.bc.M1_W, vss_w["x"], vdd_tie["y"], vdd_tie["x"], vdd_tie["y"])
    wrong = rails_check.analyse(layout, top, gen)
    assert wrong["supply_ds_pads"]["VSS"]["on_other_rail"] == 1
    assert wrong["supply_ds_pads"]["VSS"]["floating"] == 1
    assert wrong["vdd_vss_short_polygons"] == 0

    # Bridging the Metal5 trunks directly flags vdd_vss_short_polygons
    gen.seg(rails, g.L_METAL5, g.TRUNK_W, gen.trunk_x["VSS"], 10.0, gen.trunk_x["VDD"], 10.0)
    shorted = rails_check.analyse(layout, top, gen)
    assert shorted["vdd_vss_short_polygons"] > 0


def test_supply_ds_routing_uses_resolved_net_not_polarity_and_handles_repeated_instances():
    """A repeated subcircuit whose port is tied to VDD in one instance and to a signal in another, plus cross-polarity
    D terminals (NMOS D on VDD while B is VSS; PMOS D on VSS while B is VDD), must route exactly the supply-resolved
    D/S pads to their assigned rails and leave the signal instance untouched."""
    import rails_check

    gen = g.Gen()
    gen.nl = {
        "rep_cell": g.Subckt(
            "rep_cell",
            ["P", "G", "OUT", "VDD", "VSS"],
            [
                # NMOS with D on port P (VDD in X0, SIG in X1), S on OUT, B on VSS (cross-polarity when P=VDD!)
                g.Inst("XMN", ["P", "G", "OUT", "VSS"], "sg13_lv_nmos", {"w": "0.5u", "l": "0.13u"}),
                # PMOS with D on VSS (cross-polarity to B=VDD!), S on VDD (same-polarity), B on VDD
                g.Inst("XMP", ["VSS", "G", "VDD", "VDD"], "sg13_lv_pmos", {"w": "0.5u", "l": "0.13u"}),
            ],
        ),
        "mini": g.Subckt(
            "mini",
            ["SIG", "G", "O0", "O1", "VDD", "VSS"],
            [
                g.Inst("X0", ["VDD", "G", "O0", "VDD", "VSS"], "rep_cell", {}),
                g.Inst("X1", ["SIG", "G", "O1", "VDD", "VSS"], "rep_cell", {}),
            ],
        ),
    }
    top = gen.layout.create_cell("mini")
    gen.cells["mini"] = top
    gen.place_of["mini"] = {}
    ch = gen.subckt("rep_cell")
    bb = ch.bbox()
    regions = []
    for k, iname in enumerate(("X0", "X1")):
        dx = k * (bb.width() + g.dbu(4.0)) - bb.left
        dy = -bb.bottom
        gen.place(top, ch, dx, dy)
        gen.place_of["mini"][iname] = (dx, dy)
        regions.append(bb.moved(dx, dy).enlarged(g.dbu(2.0), g.dbu(2.0)))
    gen.pre_rail_bb = top.bbox().enlarged(g.dbu(3.0), g.dbu(3.0))
    gen.rails(top, regions, top.bbox().right, top_name="mini")

    res = rails_check.analyse(gen.layout, top, gen)
    # Expected supply D/S pads:
    # VDD: X0/XMN.D (1) + X0/XMP.S (1) + X1/XMP.S (1) = 3
    # VSS: X0/XMP.D (1) + X1/XMP.D (1) = 2
    assert res["supply_ds_pads"]["VDD"]["expected"] == 3
    assert res["supply_ds_pads"]["VDD"]["on_own_rail"] == 3
    assert res["supply_ds_pads"]["VDD"]["on_other_rail"] == 0
    assert res["supply_ds_pads"]["VDD"]["floating"] == 0
    assert res["supply_ds_pads"]["VSS"]["expected"] == 2
    assert res["supply_ds_pads"]["VSS"]["on_own_rail"] == 2
    assert res["supply_ds_pads"]["VSS"]["on_other_rail"] == 0
    assert res["supply_ds_pads"]["VSS"]["floating"] == 0
    assert res["ties_expected"] == res["ties_on_own_rail"] == 4
    assert res["vdd_vss_short_polygons"] == 0

    # And X1/XMN.D (wired to SIG, not VDD) must NOT reach either supply trunk
    x1_dx, x1_dy = gen.place_of["mini"]["X1"]
    sig_x = gen.dev_pts["rep_cell"]["XMN"]["D"][0] + x1_dx * g.DBU
    sig_y = gen.dev_pts["rep_cell"]["XMN"]["D"][1] + x1_dy * g.DBU
    # Check trunk connectivity specifically via rails_check._grow
    regs = {k: kdb.Region(top.begin_shapes_rec(gen.li(lp))).merged() for k, lp in rails_check._LAYERS.items()}
    trunk_pts = rails_check._trunks_from_layout(gen.layout)
    for net in ("VDD", "VSS"):
        grown = rails_check._grow(regs, kdb.Region(rails_check._box(trunk_pts[net][0], trunk_pts[net][1], 0.01)))
        assert (kdb.Region(rails_check._box(sig_x, sig_y, 0.01)) & grown["m1"]).is_empty()

