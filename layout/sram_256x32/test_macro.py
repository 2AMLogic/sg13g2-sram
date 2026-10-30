"""Macro generator tests: determinism, array count, pin set vs the netlist, and
net-tracing of the array-interface routing (wordlines, bit lines).

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

