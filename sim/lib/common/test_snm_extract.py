#!/usr/bin/env python3
"""Unit tests for sim/lib/snm_extract.py's butterfly-curve SNM extraction.

These are pure-Python tests over *analytic* voltage-transfer curves -- no
ngspice, no PDK, so they run anywhere `npm run test` runs (CI included),
unlike the testbenches themselves. What they pin down is the extraction
*mathematics*, which is where this repo's SNM numbers actually come from:

  * the self-composed (symmetric, one-sweep) method used for the
    deterministic 27-corner claim,
  * the two-curve `--pair` method used for the Monte Carlo mismatch claim
    (issue #26), including that inter-inverter asymmetry *reduces* the
    reported margin -- the entire reason the MC campaign runs the fixture
    twice per trial instead of self-composing one draw,
  * the signed continuation past zero: a monostable draw must come back as a
    negative number so a yield campaign can count it as a failure, rather
    than as an error that every statistic silently drops.

Run: python3 sim/lib/test_snm_extract.py   (or via `npm run test`)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import snm_extract  # noqa: E402

VDD = 3.3
STEP = 0.005


def vtc(vm: float, k: float, vdd: float = VDD, step: float = STEP) -> list[tuple[float, float]]:
    """A smooth, monotone-decreasing inverter VTC sampled like the real sweep.

    `f(x) = vdd / (1 + exp((x - vm)/k))` rails at `vdd` and 0, is centred on
    `vm`, and has small-signal gain `-vdd/(4k)` at its trip point -- so `k`
    is a direct, monotone knob on how much loop gain a cross-coupled pair
    built from this inverter has. A pair is bistable exactly while that gain
    exceeds 1, i.e. while `k < vdd/4`; sweeping `k` across `vdd/4` walks the
    cell through the saddle-node bifurcation the signed SNM has to be
    continuous across.

    Sampled on the same 0 -> vdd grid at the same 5 mV step the SNM
    testbenches' `.dc VIN 0 {VDDC} 0.005` uses, so the tests exercise the
    same discretisation the real data has.
    """
    n = int(round(vdd / step))
    pts = []
    for i in range(n + 1):
        x = i * step
        pts.append((x, vdd / (1.0 + math.exp((x - vm) / k))))
    return pts


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_symmetric_pair_has_positive_snm() -> None:
    """A high-gain symmetric pair is bistable, and both lobes are equal."""
    curve = vtc(VDD / 2, 0.15)
    lo, hi = snm_extract.snm(curve)
    check(lo > 0 and hi > 0, f"expected two positive lobes, got {lo}, {hi}")
    check(abs(lo - hi) < 1e-3, f"a symmetric pair's lobes should match, got {lo} vs {hi}")
    # Sanity bound: the inscribed square cannot exceed half the supply.
    check(lo < VDD / 2, f"SNM {lo} exceeds the VDD/2 ceiling")


def test_pair_mode_defaults_to_self_composition() -> None:
    """`snm(c)` and `snm(c, c)` are the same computation, not two paths."""
    curve = vtc(VDD / 2, 0.15)
    check(snm_extract.snm(curve) == snm_extract.snm(curve, curve),
          "explicit self-pairing disagreed with the single-curve default")


def test_asymmetry_reduces_the_margin() -> None:
    """Inter-inverter mismatch must *degrade* the reported margin.

    This is the claim sim/lib/run_mc_campaign.py's `snm-pair` mode rests on:
    self-composing a single mismatched draw asks "what if both inverters
    shifted together", which is not the failure mode. Offsetting the two
    trip points in opposite directions -- exactly what independent per-
    instance Vt draws do -- must shrink the minimum lobe.
    """
    matched = vtc(VDD / 2, 0.15)
    lo_matched, hi_matched = snm_extract.snm(matched)
    baseline = min(lo_matched, hi_matched)

    previous = baseline
    for offset in (0.05, 0.10, 0.20):
        left = vtc(VDD / 2 - offset, 0.15)
        right = vtc(VDD / 2 + offset, 0.15)
        lo, hi = snm_extract.snm(left, right)
        worst = min(lo, hi)
        check(worst < previous,
              f"offset {offset} V did not reduce the margin ({worst} vs {previous})")
        previous = worst
    check(previous < baseline,
          "asymmetry left the margin no worse than the matched pair")


def test_monostable_pair_reports_a_negative_margin() -> None:
    """A low-gain pair does not latch: the margin must be negative, not an error.

    Gain at the trip point is VDD/(4k); k = 1.0 puts it at 0.825 < 1, so no
    cross-coupled pair built from this inverter can hold a state.
    """
    curve = vtc(VDD / 2, 1.0)
    lo, hi = snm_extract.snm(curve)
    check(lo < 0 and hi < 0,
          f"a monostable pair must report a negative margin, got {lo}, {hi}")


def test_signed_margin_is_continuous_through_the_bifurcation() -> None:
    """Walking k across VDD/4 must walk the reported margin across zero.

    The point of the signed continuation is that it does not jump: a draw
    just inside the bistable region reports a small positive margin, a draw
    just outside reports a small negative one, and the two meet at zero. A
    discontinuity here would mean the negative branch is a sentinel rather
    than a measurement.
    """
    critical = VDD / 4  # gain = 1 exactly
    margins = []
    for k in (critical * 0.90, critical * 0.98, critical * 1.02, critical * 1.10):
        lo, hi = snm_extract.snm(vtc(VDD / 2, k))
        margins.append(min(lo, hi))

    check(margins[0] > 0 and margins[1] > 0,
          f"below the critical gain the margin must stay positive, got {margins[:2]}")
    check(margins[2] < 0 and margins[3] < 0,
          f"above the critical gain the margin must go negative, got {margins[2:]}")
    check(margins[0] > margins[1] > margins[2] > margins[3],
          f"the signed margin must decrease monotonically through the bifurcation, got {margins}")
    check(abs(margins[1]) < 0.25 and abs(margins[2]) < 0.25,
          f"the margin should pass *through* zero, not jump across it, got {margins[1:3]}")


def test_interp_and_solve_inverse_round_trip() -> None:
    """solve_inverse must invert interp on a monotone curve, both rails included."""
    curve = vtc(VDD / 2, 0.15)
    for x in (0.4, 1.0, VDD / 2, 2.3, 2.9):
        y = snm_extract.interp(curve, x)
        x_back = snm_extract.solve_inverse(curve, y)
        check(abs(x_back - x) < 1e-3, f"round trip at {x} came back as {x_back}")


def test_read_xy_skips_comments_and_short_rows(tmp_path: Path | None = None) -> None:
    """`wrdata` output is parsed leniently but never silently reordered."""
    target = Path(__file__).resolve().parent / ".test_snm_extract_scratch.txt"
    target.write_text("* comment\n# another\n0.0 3.3\nbroken\n0.5 3.2\n\n1.0 1.5\n")
    try:
        pts = snm_extract.read_xy(str(target))
    finally:
        target.unlink()
    check(pts == [(0.0, 3.3), (0.5, 3.2), (1.0, 1.5)], f"unexpected parse: {pts}")


TESTS = [
    test_symmetric_pair_has_positive_snm,
    test_pair_mode_defaults_to_self_composition,
    test_asymmetry_reduces_the_margin,
    test_monostable_pair_reports_a_negative_margin,
    test_signed_margin_is_continuous_through_the_bifurcation,
    test_interp_and_solve_inverse_round_trip,
    test_read_xy_skips_comments_and_short_rows,
]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    if failures:
        print(f"\n{failures} of {len(TESTS)} snm_extract tests failed")
        return 1
    print(f"\nall {len(TESTS)} snm_extract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
