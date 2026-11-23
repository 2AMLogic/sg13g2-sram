#!/usr/bin/env python3
"""Tests for sim/bitcell/measure_pex.py's staging and measurement-row
emission (pure Python, PDK- and fleet-free: nothing here simulates or
touches klt).

Run: python3 sim/bitcell/test_measure_pex.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bitcell_post  # noqa: E402
import measure_pex  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
SCHEMATIC = REPO / "design/bitcell/bitcell.spice"

# A minimal stand-in for the parasitic extraction klt pex hands the extracted
# leg: the extracted top name, the extracted (common) pin order, one device and
# one parasitic R/C pair, and the .GLOBAL vsubs the real extraction writes.
EXTRACTED_STANDIN = """* extracted by klt extract --deck sg13g2 (test stand-in)
.GLOBAL vsubs
.SUBCKT sg13g2_sram_bitcell_6t BL BLB Q QB VDD VSS WL
X$1 Q WL BL VSS sg13_lv_nmos L=0.13U W=0.3U
RBL_t0 BL__t0 BL 1.9828
CBL BL vsubs 3.26488e-16
Rvsubs_dctie vsubs 0 1e+12
.ENDS sg13g2_sram_bitcell_6t
"""


def _synth_write_report(path: Path, top_by_corner: list[tuple[str, int | None]]) -> None:
    """A `klt sim`-shaped report for cmd_write: both flip measurements
    (d_end_k, d_fin_k) go negative exactly at the levels k <= top (top is
    the highest bit-line level index that flips; None = no level flips)."""
    corners = []
    for cid, top in top_by_corner:
        meas = []
        for k in range(bitcell_post.N_LEVELS):
            v = -1.0 if (top is not None and k <= top) else 1.0
            meas += [{"name": f"d_end_{k}", "value": v},
                     {"name": f"d_fin_{k}", "value": v}]
        corners.append({"corner_id": cid, "status": "pass", "measurements": meas})
    path.write_text(json.dumps({"corners": corners, "environment": {}}))


def _check_measure_rows(art: Path) -> None:
    """measure()'s emitted write-margin rows on synthetic reducer input
    (issue #234): a top = 0 margin of 0.000 V grades fail with its value
    intact, top = 1 grades pass, and a no-flip corner stays error with the
    reason. Only the batch sim call and the SNM reduction are stubbed -- the
    write path runs the real bitcell_post.cmd_write reducer."""
    snm_report = art / "report-snm.json"
    write_report = art / "report-write.json"
    cases = [
        (measure_pex.corner_id("mos_sf", 1.08, -40), 0),     # flips only at BL = 0 V
        (measure_pex.corner_id("mos_tt", 1.20, 27), 1),      # 25 mV of margin
        (measure_pex.corner_id("mos_fs", 1.08, 125), None),  # never flips
    ]
    _synth_write_report(write_report, cases)
    snm_report.write_text(json.dumps({
        "corners": [{"corner_id": cid, "status": "pass"} for cid, _ in cases],
        "environment": {},
    }))

    def fake_run_sim(klt, req, a, name, stderr_log):
        stderr_log.write_text("")
        return {"snm": snm_report, "write": write_report}[name]

    def fake_cmd_snm(report, art_root, curves_dir, label):
        return {"label": label, "kind": "simulated", "corners": [
            {"corner_id": cid, "klt_status": "pass",
             "hold_snm_v": 0.45, "read_snm_v": 0.20}
            for cid, _ in cases
        ]}

    saved = (measure_pex.run_sim, bitcell_post.cmd_snm)
    measure_pex.run_sim, bitcell_post.cmd_snm = fake_run_sim, fake_cmd_snm
    try:
        doc = measure_pex.measure("schematic", SCHEMATIC, art / "m")
    finally:
        measure_pex.run_sim, bitcell_post.cmd_snm = saved

    rows = {c["corner_id"]: next(m for m in c["measurements"]
                                 if m["name"] == "write_margin")
            for c in doc["corners"]}
    zero = rows[measure_pex.corner_id("mos_sf", 1.08, -40)]
    assert zero == {"name": "write_margin", "value": 0.0, "status": "fail"}, zero
    one = rows[measure_pex.corner_id("mos_tt", 1.20, 27)]
    assert one == {"name": "write_margin", "value": 0.025, "status": "pass"}, one
    noflip = rows[measure_pex.corner_id("mos_fs", 1.08, 125)]
    assert noflip["value"] is None and noflip["status"] == "error", noflip
    assert "no flip" in noflip["message"], noflip


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        art = Path(tmp)

        # parse_top: schematic and extracted pin orders
        top, pins = measure_pex.parse_top(SCHEMATIC.read_text())
        assert top == "bitcell" and pins == measure_pex.SCHEMATIC, (top, pins)
        top, pins = measure_pex.parse_top(EXTRACTED_STANDIN)
        assert top == "sg13g2_sram_bitcell_6t" and pins == measure_pex.COMMON, (top, pins)

        # schematic leg: wrapper calls the original cell in schematic order
        measure_pex.stage("schematic", SCHEMATIC, art / "s")
        dut = (art / "s" / "dut.spice").read_text()
        assert "X0 BL BLB WL VDD VSS Q QB bitcell" in dut, dut
        assert ".subckt bitcell BL BLB WL VDD VSS Q QB" in dut

        # benches: include repointed, X calls reordered to the common order
        bench = (art / "s" / "bench_snm.cir").read_text()
        assert ".include dut.spice" in bench
        assert "Xread_a vdd vdd qra qbra vdd 0 vdd bitcell_pexrc" in bench, bench
        assert "Xhold_a vdd vdd qha qbha vdd 0 0 bitcell_pexrc" in bench
        write = (art / "s" / "bench_write.cir").read_text()
        xw = [l for l in write.splitlines() if l.startswith("Xw")]
        assert len(xw) == 33, len(xw)
        assert xw[0] == "Xw0 bl0 vdd q0 qb0 vdd 0 wl bitcell_pexrc", xw[0]
        assert xw[32] == "Xw32 bl32 vdd q32 qb32 vdd 0 wl bitcell_pexrc", xw[32]
        assert not any(l.endswith(" bitcell\n") for l in write.splitlines())

        # header comment follows the common order, not the schematic one
        assert "*               BL  BLB  Q  QB  VDD  VSS  WL" in write

        # requests: staged bench, four explicit corner units, rest untouched
        req = json.loads((art / "s" / "request_snm.json").read_text())
        assert req["netlist"] == "bench_snm.cir"
        assert [u["process"] for u in req["corners"]["units"]] == [
            "mos_fs", "mos_sf", "mos_ff", "mos_tt"
        ]
        assert req["analysis"] == json.loads(
            (REPO / "sim/bitcell/request_snm.json").read_text()
        )["analysis"]

        # extracted leg: wrapper inner call is the identity on the extracted top
        ex_path = art / "extracted.spice"
        ex_path.write_text(EXTRACTED_STANDIN)
        measure_pex.stage("extracted", ex_path, art / "e")
        dut = (art / "e" / "dut.spice").read_text()
        assert "X0 BL BLB Q QB VDD VSS WL sg13g2_sram_bitcell_6t" in dut, dut
        assert ".GLOBAL vsubs" in dut

        # both legs drive byte-identical benches -- only the DUT differs
        for name in ("bench_snm.cir", "bench_write.cir"):
            assert (art / "s" / name).read_text() == (art / "e" / name).read_text(), name

        # a netlist whose top pins are not the bitcell set is refused
        bad = art / "bad.spice"
        bad.write_text(".SUBCKT other A B C\nX0 A B C leaf\n.ENDS other\n")
        try:
            measure_pex.stage("schematic", bad, art / "bad")
        except SystemExit:
            pass
        else:
            raise AssertionError("stage() accepted a foreign pin set")

        # measurement-row emission (issue #234): zero write margin -> fail
        _check_measure_rows(art)

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
