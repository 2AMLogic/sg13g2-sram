"""Macro generator tests: determinism, array count, pin set vs the netlist.

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
