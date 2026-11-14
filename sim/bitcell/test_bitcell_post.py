#!/usr/bin/env python3
"""Tests for sim/bitcell/bitcell_post.py's inscribed-square SNM (pure Python).

Run: python3 sim/bitcell/test_bitcell_post.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bitcell_post  # noqa: E402


def step_vtc(vm: float, w: float, n: int = 201):
    """Near-ideal inverter on [0, 1]: 1 below vm, 0 above, linear across 2w."""
    pts = []
    for i in range(n):
        x = i / (n - 1)
        y = 1.0 if x <= vm - w else 0.0 if x >= vm + w else (vm + w - x) / (2 * w)
        pts.append((x, y))
    return pts


def write_report(path: Path, tflip) -> None:
    """One-corner klt report: BL levels 0..3 flip (d < 0 at both samples), the rest do not."""
    ms = []
    for k in range(bitcell_post.N_LEVELS):
        d = -0.5 if k <= 3 else 0.5
        ms += [{"name": f"d_end_{k}", "value": d}, {"name": f"d_fin_{k}", "value": d}]
    if tflip is not False:
        ms.append({"name": "tflip_0", "value": tflip})
    path.write_text(json.dumps({"corners": [{"corner_id": "c", "status": "pass", "measurements": ms}]}))


def test_flip_time(tmp: Path) -> None:
    check = bitcell_post.flip_time_check
    assert check(0.2e-9, 1.0) == "within_pulse"
    assert check(None, 1.0) == "never_flips"
    assert check(1.2e-9, 1.0) == "after_pulse_end"  # flips, but only after the wordline fell
    assert check(0.6e-9, 0.5) == "after_pulse_end"
    for tflip, want in ((0.2e-9, "within_pulse"), (None, "never_flips"), (False, "never_flips")):
        rep = tmp / "r.json"
        write_report(rep, tflip)
        c = bitcell_post.cmd_write(str(rep), "t")["corners"][0]
        assert c["write_margin_v"] == 0.075 and c["flip_time_check"] == want, c
        assert c["flip_time_s"] == (tflip if tflip is not False else None)


def test_sweep_request(tmp: Path) -> None:
    here = Path(__file__).resolve().parent
    cell = tmp / "cell.spice"
    cell.write_text("* cell\n")
    for pw, t_end, t_fin, stop in ((0.5, "0.8n", "2n", "2.5n"), (1.0, "1.3n", "2.5n", "3n"), (2.0, "2.3n", "3.5n", "4n")):
        out = tmp / f"pw{pw}"
        bitcell_post.cmd_sweep_request(str(here / "request_write.json"), str(here / "bench_write.cir"), str(out), pw, str(cell))
        req = json.load(open(out / "request.json"))
        by = {m["name"]: m["spice"] for m in req["measurements"]}
        assert f"AT={t_end}" in by["d_end_5"] and f"AT={t_fin}" in by["d_fin_5"], by["d_end_5"]
        assert req["analysis"]["args"] == f"5p {stop}", req["analysis"]
        assert "tflip_0" in by and req["corners"] == bitcell_post.SWEEP_CORNERS
        bench = (out / "bench_write.cir").read_text()
        assert f".param pw={pw:g}n" in bench and ".include ./cell.spice" in bench
        assert (out / "cell.spice").exists()
    # the 1 ns sweep point reproduces the 45-corner request's sampling
    base = json.load(open(here / "request_write.json"))
    one = json.load(open(tmp / "pw1.0" / "request.json"))
    assert base["measurements"] == one["measurements"] and base["analysis"] == one["analysis"]


def test_write_sweep(tmp: Path) -> None:
    for ns, tf in ((0.5, None), (1.0, 0.2e-9)):
        write_report(tmp / f"w{ns}.json", tf if tf is not None else False)
        (tmp / f"w{ns}.out").write_text(json.dumps(bitcell_post.cmd_write(str(tmp / f"w{ns}.json"), "t", ns)))
    s = bitcell_post.cmd_write_sweep("s", [(1.0, str(tmp / "w1.0.out")), (0.5, str(tmp / "w0.5.out"))])
    assert s["pulse_widths_ns"] == [0.5, 1.0]
    bp = s["corners"][0]["by_pulse"]
    assert bp["0.5n"]["flip_time_check"] == "never_flips" and bp["1n"]["flip_time_check"] == "within_pulse"


def main() -> int:
    ideal = step_vtc(0.5, 0.005)
    sq = bitcell_post.signed_snm(ideal, ideal)[0]
    assert sq is not None and abs(sq - 0.5) < 0.02, sq  # two 0.5 x 0.5 eyes
    # the vertical-gap method of snm_extract.py over-reads the square
    import snm_extract
    vgap = min(snm_extract.snm(ideal, ideal))
    assert vgap > sq, (vgap, sq)
    # a gain < 1 inverter pair is monostable: no eyes, caller falls back
    flat = [(i / 100, 1.0 - 0.2 * (i / 100) - 0.4) for i in range(101)]
    assert bitcell_post.signed_snm(flat, flat)[0] < 0
    # a weaker, skewed pair (switch point 0.4 / 0.6) shrinks the smaller eye
    skew = bitcell_post.square_snm(step_vtc(0.4, 0.005), step_vtc(0.6, 0.005))
    assert skew is not None and skew < sq, skew
    with tempfile.TemporaryDirectory() as d:
        test_flip_time(Path(d))
        test_sweep_request(Path(d))
        test_write_sweep(Path(d))
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
