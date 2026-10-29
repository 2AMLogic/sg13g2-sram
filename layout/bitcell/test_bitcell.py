"""Checks on the generated bitcell: determinism, W/L read back, LVS teeth.

Run: uv run --with pytest --with klayout pytest layout/bitcell/test_bitcell.py
The LVS test needs `klt` on PATH and is skipped without it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import klayout.db as kdb
import pytest

import generate as g

ROOT = Path(__file__).resolve().parents[2]
SPICE = ROOT / "design" / "bitcell" / "bitcell.spice"


def _bytes(layout: kdb.Layout, tmp: Path, name: str) -> bytes:
    p = tmp / name
    layout.write(str(p), g.save_options())
    return p.read_bytes()


def test_deterministic(tmp_path):
    assert _bytes(g.build(), tmp_path, "a.gds") == _bytes(g.build(), tmp_path, "b.gds")
    assert _bytes(g.build_tile(), tmp_path, "c.gds") == _bytes(g.build_tile(), tmp_path, "d.gds")


def test_committed_gds_matches_generator(tmp_path):
    committed = ROOT / "layout" / "bitcell" / f"{g.TOP_CELL}.gds"
    assert committed.read_bytes() == _bytes(g.build(), tmp_path, "x.gds")


def _spice_sizes() -> dict[str, list[tuple[float, float]]]:
    out: dict[str, list[tuple[float, float]]] = {"n": [], "p": []}
    for line in SPICE.read_text().splitlines():
        m = re.match(r"X\w+ .* sg13_lv_(nmos|pmos) w=([\d.]+)u l=([\d.]+)u", line)
        if m:
            out[m.group(1)[0]].append((float(m.group(2)), float(m.group(3))))
    return out


def test_device_wl_matches_spice():
    layout = g.build()
    top = layout.top_cell()
    dbu = layout.dbu

    def region(lp):
        return kdb.Region(top.begin_shapes_rec(layout.layer(*lp)))

    activ, poly, psd = region(g.L_ACTIV), region(g.L_GATPOLY), region(g.L_PSD)
    channels = activ & poly
    got = {"n": [], "p": []}
    for poly_ in channels.each_merged():
        bb = poly_.bbox()
        kind = "p" if not (kdb.Region(bb) & psd).is_empty() else "n"
        # gate runs vertically: L is the x extent, W the y extent
        got[kind].append((round(bb.height() * dbu, 3), round(bb.width() * dbu, 3)))
    want = _spice_sizes()
    for k in "np":
        assert sorted(got[k]) == sorted((round(w, 3), round(l, 3)) for w, l in want[k])


@pytest.mark.skipif(shutil.which("klt") is None, reason="klt not on PATH")
def test_lvs_has_teeth(tmp_path):
    def lvs(layout: kdb.Layout, name: str) -> dict:
        gds = tmp_path / f"{name}.gds"
        layout.write(str(gds), g.save_options())
        sp = tmp_path / f"{name}.spice"
        subprocess.run(["klt", "extract", "--deck", "sg13g2", str(gds), "-o", str(sp)],
                       check=True, capture_output=True)
        req = {"layout": {"netlist": str(sp), "top": g.TOP_CELL},
               "reference": {"netlist": str(SPICE), "top": "bitcell", "form": "subckt-call"}}
        p = subprocess.run(["klt", "lvs", json.dumps(req), "--format", "json"],
                           capture_output=True, text=True)
        return json.loads(p.stdout)

    assert lvs(g.build(), "good")["status"] == "match"
    bad = g.build()
    top = bad.top_cell()
    li = bad.layer(*g.L_CONT)
    # open the Q-net cross-couple contact: the gate of MN1/MP1 floats
    x = int(round((g.X["g_r"][1] - 0.5 * g.POLY_PAD) / bad.dbu))
    victims = [s for s in top.shapes(li).each()
               if abs(s.bbox().center().x - x) < 20 and s.bbox().center().y > int(g.Y_JOG1[0] / bad.dbu)
               and s.bbox().center().y < int(g.Y_JOG2[1] / bad.dbu) + 1]
    assert victims
    for s in victims:
        top.shapes(li).erase(s)
    assert lvs(bad, "bad")["status"] != "match"
