"""Macro generator tests: determinism, array count, pin set vs the netlist,
net-tracing of the array-interface routing (wordlines, bit lines) and of the
leaf-cell signal routing (flat-net resolution, router, per-cell connectivity).

    cd layout/sram_256x32 && uv run --with pytest --with klayout pytest -q test_macro.py
"""

import os
import re
import sys

import klayout.db as kdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as g  # noqa: E402

LEF = os.path.join(g.HERE, "macro.lef")


def _bytes(tmp_path, name):
    layout, _, _ = g.build()
    p = str(tmp_path / name)
    layout.write(p, g.save_options())
    return open(p, "rb").read()


def test_deterministic(tmp_path):
    assert _bytes(tmp_path, "a.gds") == _bytes(tmp_path, "b.gds")


def test_committed_gds_is_current(tmp_path):
    assert _bytes(tmp_path, "c.gds") == open(g.GDS_PATH, "rb").read()


def test_bitcell_count_and_top():
    layout, _, top = g.build()
    assert top.name == "macro"
    assert [c.name for c in layout.top_cells()] == ["macro"]
    bit = layout.cell("bitcell")
    n = 0
    for inst in top.begin_instances_rec():
        if inst.inst_cell().cell_index() == bit.cell_index():
            n += 1
    assert n == g.ROWS * g.COLS == 8192


def test_array_is_mirror_abutted():
    layout, _, _ = g.build()
    pair = layout.cell("bl_pair")
    h = round(g.bc.H_CELL / g.DBU)
    ys = sorted(i.trans.disp.y - (h if i.trans.is_mirror() else 0) for i in pair.each_inst())
    assert len(ys) == 128 and all(b - a == h for a, b in zip(ys, ys[1:]))
    assert [i.trans.is_mirror() for i in pair.each_inst()].count(True) == 64


def test_pins_match_netlist_ports():
    ports = g.parse_netlist(g.NETLIST)["macro"].ports
    _, gen, _ = g.build()
    assert sorted(p["name"] for p in gen.pin_list) == sorted(ports)


def test_lef_pins_match_netlist_ports():
    ports = set(g.parse_netlist(g.NETLIST)["macro"].ports)
    lef = open(LEF).read()
    assert re.search(r"^MACRO macro$", lef, re.M)
    pins = set(re.findall(r"^\s*PIN (\S+)$", lef, re.M))
    assert pins == ports


def test_bus_ends_present():
    _, gen, _ = g.build()
    names = {p["name"] for p in gen.pin_list}
    assert {"A[7]", "A[0]", "D[31]", "D[0]", "Q[31]", "Q[0]"} <= names


# ---- array-interface routing: net tracing on the generated layout -------------
_CONN = (("poly", "cont"), ("cont", "m1"), ("m1", "v1"), ("v1", "m2"), ("m2", "v2"), ("v2", "m3"))


def _extract(mutate=None):
    """Flat connectivity of the generated layout (GatPoly-Cont-Metal1-Via1-Metal2-
    Via2-Metal3). ``mutate(layout, top)`` may damage the layout first."""
    layout, gen, top = g.build()
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
        gen = g.Gen()
        gen.macro()  # same coordinates as the layout under test (deterministic)
        _erase_at(top, g.L_VIA2, g.WL_PAD_X, gen.wl_y(0))

    gen, net = _extract(cut)
    ok = _wl_ok(_wl_ids(gen, net, [0, 127]))
    assert not ok[0] and ok[127]


def test_bitline_trace_has_teeth():
    def cut(layout, top):
        gen = g.Gen()
        gen.macro()
        _erase_at(layout.cell("bit_slice"), g.L_VIA1, gen.bl_stripe_x["BL0"], g.BL_VIA_Y)

    gen, net = _extract(cut)
    ok = _bl_ok(_bl_ids(gen, net, [0, 63]))
    assert not ok[(0, "BL0")] and ok[(0, "BLB0")]


def test_every_periphery_device_has_a_body_tie():
    """Each transistor cell carries a tie Activ with a Cont and a Metal1 label for its bulk net."""
    layout, _, _ = g.build()
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
    layout, _, _ = g.build()
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

    layout, gen, top = g.build()
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

    layout, gen, top = g.build()
    res = rails_check.wordline_gap_clearance(layout, top, gen)
    assert res["total"] == 0, res
    # the lanes do cross the gap, on Metal4 only
    gap = g.WL_FANOUT_GAP
    m4 = layout.cell("rails").dbbox_per_layer(layout.layer(*g.L_METAL4))
    assert m4.left < -gap and m4.right > 0


def test_gap_clearance_check_has_teeth():
    import rails_check

    layout, gen, top = g.build()
    gen.box(layout.cell("rails"), g.L_VIA2, -10.0, 20.0, -9.81, 20.19)
    assert rails_check.wordline_gap_clearance(layout, top, gen)["rail_shapes_in_gap_below_metal4"]["v2"] == 1


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
    layout, gen, _ = g.build()
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
    assert n_checked == sum(len(r["routed"]) for r in gen.leaf_report.values()) == 53


def test_leaf_cell_undrawn_nets_are_listed():
    _, gen, _ = g.build()
    # every net of every leaf cell is either drawn, listed as undrawn, or excluded/single-terminal by rule
    for name in g.LEAF_ROUTED:
        rep = gen.leaf_report[name]
        nets = {n for inst in gen.nl[name].insts if inst.ref in g.DEVICE_REFS for n in inst.nets[:3]}
        listed = set(rep["routed"]) | set(rep["failed"]) | set(rep["single_terminal"]) | set(rep["excluded"])
        assert listed == nets, (name, nets ^ listed)
    # the known gap: the column mux's BLBM is not joined (the bit-line jogs leave no Metal3 crossing)
    undrawn = {(name, n) for name in g.LEAF_ROUTED for n in gen.leaf_report[name]["failed"]}
    assert undrawn == {("column_mux", "BLBM")}, undrawn
    assert gen.leaf_report["inv"]["routed"] == {"A": 2, "Y": 2}
    assert gen.leaf_report["precharge"]["excluded"]["BL"]["reason"] == "bit line"


def test_leaf_cell_trace_has_teeth_via1_landing():
    def probe(mutate):
        layout, gen, _ = g.build()
        if mutate:
            x, y = gen.leaf_terms["nand2"]["Y"][0]
            _erase_at(layout.cell("nand2"), g.L_VIA1, x, y)
        return _leaf_nets(layout, gen, "nand2")

    assert len(set(probe(False)["Y"])) == 1
    cut = probe(True)
    assert len(set(cut["Y"])) > 1 and len(set(cut["A"])) == 1


def test_leaf_cell_trace_has_teeth_via2():
    layout, gen, _ = g.build()
    name, v = next((n, vs[0]) for n, vs in sorted(gen.leaf_vias.items()) if vs)
    _erase_at(layout.cell(name), g.L_VIA2, v["x"], v["y"])
    ids = _leaf_nets(layout, gen, name)
    assert len(set(ids[v["net"]])) > 1, (name, v)


# ---- nets between the leaf cells of the latch and control cells (issue #106) ---------
_HIER = {}


def _hier_build():
    if not _HIER:
        _HIER["layout"], _HIER["gen"], _ = g.build()
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
