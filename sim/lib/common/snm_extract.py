#!/usr/bin/env python3
"""Static noise margin (SNM) extraction from one or two half-cell VTC sweeps.

Why one sweep is enough for the *deterministic* PVT-corner claim: `bitcell_6t`'s
two storage inverters (MPL/MNL and MPR/MNR in design/netlist/bitcell_6t.spice)
are identical devices under a cross-coupled connection when no per-instance
mismatch is injected. For a cell built from two identical inverters, the
classic "butterfly curve" (the two inverters' voltage-transfer curves plotted
against each other, one mirrored across the line Vout=Vin) can be constructed
from a *single* inverter's VTC sweep: the first branch is the sweep itself,
y = f(x); the second branch is that same inverter's curve reflected across the
diagonal, i.e. the *inverse* relation x = f(y), which -- because the two
inverters are identical devices -- is exactly the transfer curve the other
half-cell would produce. This is a standard simplification for symmetric 6T
SRAM SNM extraction (see e.g. E. Seevinck et al., "Static-Noise Margin
Analysis of MOS SRAM Cells," IEEE JSSC 1987, for the general two-curve method
this specializes).

Why two sweeps are used for the Monte Carlo / yield claim (issue #26): device
mismatch (`sw_stat_mismatch=1` in the gf180mcu model file) draws an
independent per-instance threshold/mobility offset for every transistor
instantiated -- so under MC the two half-cells are no longer identical, and
self-composing one curve would silently assume away exactly the effect an
inter-inverter-mismatch SNM campaign exists to measure. `sim/lib/
run_mc_campaign.py` instead runs the same half-cell fixture *twice* per MC
trial, once per half-cell, each with its own independent `.option seed`, and
this script's `--pair` mode combines the two independently-mismatched curves
into a (possibly asymmetric) butterfly SNM -- the direct two-curve
generalization of the single-curve method below, per Seevinck et al. 1987's
original (non-symmetric) construction.

SNM is the side length of the largest axis-aligned square that fits between
the two curves within one lobe of the butterfly plot. In the single-curve
case, because the second curve is the exact mirror image of the first about
y=x, the maximum vertical gap between the sweep curve and its own inverse --
found for x in one lobe -- equals that maximum square's side length; in the
two-curve case the same holds between curve 1 and the *inverse of curve 2*.

Finding the two curves' intersections (f1(x) = f2^-1(x)) is equivalent to
finding the fixed points of f2 composed with f1: f2(f1(x)) = x. (The
single-curve case sets f2 = f1, recovering the familiar f(f(x)) = x.) This
script uses that composition directly, evaluated with forward interpolation
only (never constructing an explicit inverse-of-f table). That matters in
practice: a naive "swap the (x, y) pairs and sort" way of building f^-1 is
numerically fragile wherever f's sampled *output* changes extremely slowly
(its slope near either rail can under/overflow float resolution over a wide
span of x), which biases a sorted-table inverse and silently drops a real
crossing. Forward interpolation of the original, evenly-sampled-in-x sweep has
no such flat-tail pathology, so composing it with itself (or with a second,
independent curve) is the robust way to find the same roots.

Signed SNM (why a monostable draw reports a negative number, not an error):
a Monte Carlo yield campaign has to be able to *count* a failure. A draw
whose two mismatched half-cells no longer latch has no butterfly lobe and
therefore no square to measure -- reporting it as a measurement error would
push it into `klt yield`'s `errored` bucket, which is excluded from every
statistic, so the very draws the campaign exists to find would silently
vanish from the yield estimate (confirmed empirically during issue #26: a
deliberately-degraded negative control came back `not_detected` for exactly
this reason). Instead, a monostable draw reports `-d`, where `d` is the
bistability deficit -- how far the composed loop map misses re-crossing the
diagonal, in volts (see `bistability_deficit`). `d -> 0` at the bifurcation,
so the reported quantity is continuous through zero: strictly positive
values are the classical Seevinck SNM, zero is the bistability boundary, and
negative values measure how far past it a failing draw sits. Only a draw
with no measurable structure at all is still reported as an open result.

Input: one or two two-column whitespace-separated ASCII data files (Vin,
Vout), as written by ngspice's `wrdata` from a DC sweep, monotonically
increasing in Vin. Output: prints `RESULT: <label> = <value>` (volts) to
stdout, and exits 1 with a diagnostic on stderr if the curve(s) are
degenerate beyond even that signed continuation -- a reportable open result,
never silently coerced to a passing number.

Usage:
    snm_extract.py <data-file> <label>
        Single-curve / self-composed mode (unchanged since this script's
        original version) -- used by sim/lib/run_corner_sweep.sh for the
        deterministic 27-corner PVT claim.

    snm_extract.py --pair <data-file-1> <data-file-2> <label>
        Two-curve mode -- used by sim/lib/run_mc_campaign.py for the
        mismatch-driven Monte Carlo claim (issue #26). <data-file-1> and
        <data-file-2> are independent half-cell sweeps (same fixture, same
        corner, independent `.option seed`/mismatch draw per file).
"""
from __future__ import annotations

import sys

Point = tuple[float, float]
Curve = list[Point]


def read_xy(path: str) -> Curve:
    pts: Curve = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("*", "#")):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            try:
                x, y = float(parts[0]), float(parts[1])
            except ValueError:
                continue
            pts.append((x, y))
    return pts


def interp(pts: Curve, x: float) -> float:
    """Linear interpolation of y at x over a curve sorted ascending by x.

    Queries outside [pts[0].x, pts[-1].x] clamp to the nearest endpoint.
    """
    xs_lo, xs_hi = pts[0][0], pts[-1][0]
    if x <= xs_lo:
        return pts[0][1]
    if x >= xs_hi:
        return pts[-1][1]
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid][0] <= x:
            lo = mid
        else:
            hi = mid
    x0, y0 = pts[lo]
    x1, y1 = pts[hi]
    if x1 == x0:
        return y0
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def solve_inverse(pts: Curve, target_y: float) -> float:
    """Find x such that interp(pts, x) == target_y, via bisection.

    Assumes `pts` (sorted ascending by x) is monotonic in y -- true for any
    single-stage CMOS inverter's VTC. Bisection only ever evaluates the
    well-behaved forward `interp`, so it is immune to the flat-tail
    pathology a sorted-and-swapped inverse table hits (see module
    docstring).
    """
    lo, hi = pts[0][0], pts[-1][0]
    y_lo, y_hi = pts[0][1], pts[-1][1]
    decreasing = y_lo >= y_hi
    for _ in range(80):
        mid = (lo + hi) / 2
        y_mid = interp(pts, mid)
        above = y_mid >= target_y
        if above == decreasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def find_crossings(pts1: Curve, pts2: Curve | None = None) -> list[float]:
    """x-values where f1(x) = f2^-1(x), found as the fixed points of f2 o f1.

    `pts2` defaults to `pts1` (the original single-curve/self-composed mode).

    This is *not* the same as f1(x) = x: for two cross-coupled inverters with
    output-vs-input curves f1 (left) and f2 (right), the two stable states
    (Q, QB) = (a, b) and (b, a) satisfy f1(a) = b and f2(b) = a, so
    f2(f1(a)) = f2(b) = a -- i.e. a is a fixed point of f2 o f1, generally
    *not* of f1 alone (unless a = b, the metastable point, which trivially
    satisfies both, and unless f1 = f2, the symmetric case, which collapses
    to f o f). Scanning h(x) = f2(f1(x)) - x for sign changes recovers all 3
    fixed points (low stable, metastable, high stable) for a bistable cell,
    using only forward interpolation of the two original sweeps -- evaluated
    over pts1's own x grid (both curves are sampled from the same `.dc VIN 0
    VDDC 0.005` sweep, so they share a grid; a mismatched grid would only
    affect where h() is evaluated, not correctness, since interp() clamps).
    """
    if pts2 is None:
        pts2 = pts1

    def h(x: float, y_at_x: float) -> float:
        return interp(pts2, y_at_x) - x

    raw_crossings = []
    h_values = [h(x, y) for x, y in pts1]
    for i in range(len(pts1) - 1):
        prev_x, prev_h = pts1[i][0], h_values[i]
        cur_x, cur_h = pts1[i + 1][0], h_values[i + 1]
        if prev_h == 0:
            raw_crossings.append(prev_x)
        elif (prev_h > 0) != (cur_h > 0):
            denom = cur_h - prev_h
            frac = -prev_h / denom if denom != 0 else 0.0
            raw_crossings.append(prev_x + frac * (cur_x - prev_x))
    if h_values[-1] == 0:
        raw_crossings.append(pts1[-1][0])

    # A fixed point that sits exactly at (or a hair past, by solver
    # tolerance) the sweep's own boundary never produces a sign flip --
    # there is no sample beyond the boundary to flip against -- so it
    # would otherwise go undetected even though h is essentially zero
    # there. This is the common case for an inverter whose VTC saturates
    # very close to (but not exactly at) a rail: treat "close enough to
    # zero" at the two sweep endpoints as a boundary crossing too, using a
    # tolerance tied to the sweep's own y-span (SPICE convergence is
    # typically far coarser than float precision, so 0.1% of the swept
    # output range is a conservative, still-tight, band).
    y_span = max(y for _, y in pts1) - min(y for _, y in pts1)
    boundary_tol = max(y_span * 1e-3, 1e-6)
    if abs(h_values[0]) <= boundary_tol and (not raw_crossings or abs(raw_crossings[0] - pts1[0][0]) > 1e-12):
        raw_crossings.insert(0, pts1[0][0])
    if abs(h_values[-1]) <= boundary_tol and (not raw_crossings or abs(raw_crossings[-1] - pts1[-1][0]) > 1e-12):
        raw_crossings.append(pts1[-1][0])

    if not raw_crossings:
        return []
    # Dedupe crossings closer together than 0.5% of the swept x-span --
    # numerical noise near a near-tangent crossing can otherwise register
    # as two adjacent detections instead of one.
    span = pts1[-1][0] - pts1[0][0]
    eps = max(span * 0.005, 1e-9)
    deduped = [raw_crossings[0]]
    for c in raw_crossings[1:]:
        if c - deduped[-1] > eps:
            deduped.append(c)
    return deduped


def bistability_deficit(pts1: Curve, pts2: Curve, crossings: list[float]) -> float | None:
    """How far a *monostable* pair is from being bistable, in volts.

    When the cell is bistable, h(x) = f2(f1(x)) - x crosses zero three times
    (low stable / metastable / high stable). Losing bistability is a
    saddle-node bifurcation: two of those roots merge and annihilate, so the
    stretch of h that used to straddle zero now misses it entirely -- coming
    down to within some distance of the axis and turning back. The size of
    that closest approach, measured away from whatever root *does* survive,
    is the natural continuation of "how much noise margin is there" past
    zero: it goes to zero exactly at the bifurcation, from the failing side,
    just as the butterfly square's side length goes to zero from the passing
    side.

    So: `deficit = min |h(x)|` over the sweep, excluding a window around each
    surviving root (whose own neighbourhood trivially has |h| ~ 0 and says
    nothing about bistability). Returns None only when that leaves nothing to
    measure -- which stays a reportable open result rather than a fabricated
    number.

    The *sign* of the reported value is what enters the yield statistic (a
    monostable draw is a failure of `spec/sram.md`'s "> 0" requirement). Its
    *magnitude* is a lower bound on how far past the bifurcation the draw
    sits, not a calibrated margin -- for a draw whose h is monotone away from
    its single root the closest approach is set by the exclusion window
    rather than by any near-tangency. Records must not read a negative
    magnitude as a noise margin.
    """
    span = pts1[-1][0] - pts1[0][0]
    # Same 0.5%-of-span scale find_crossings() already uses to dedupe
    # near-coincident roots, widened to 2% so a root's own shoulder (where
    # |h| is still small purely because h just crossed zero) cannot be
    # mistaken for a near-tangency.
    window = max(span * 0.02, 1e-9)
    best: float | None = None
    for x, y in pts1:
        if any(abs(x - r) <= window for r in crossings):
            continue
        value = abs(interp(pts2, y) - x)
        if best is None or value < best:
            best = value
    return best


def snm(pts1: Curve, pts2: Curve | None = None) -> tuple[float, float]:
    """Return (snm_lobe_low, snm_lobe_high) -- the two stable-lobe margins.

    `pts2` defaults to `pts1` (self-composed, symmetric-cell mode). When
    `pts2` is a second, independent curve, this computes the (possibly
    asymmetric) two-curve butterfly SNM directly -- see module docstring.

    A bistable inverter pair has 3 fixed points of f2 o f1: low stable
    point, metastable midpoint, high stable point. The low lobe spans
    [x_low, x_mid]; the high lobe spans [x_mid, x_high]. SNM per spec is
    "the minimum butterfly-curve square side length" -- report both
    lobes; the macro-level claim is the minimum of the two (spec/sram.md's
    "must be > 0 at every corner" applies to both).
    """
    if pts2 is None:
        pts2 = pts1
    crossings = find_crossings(pts1, pts2)
    if len(crossings) < 3:
        # Monostable: the cell has NO static noise margin. Report the signed
        # continuation (-deficit) rather than dropping the draw -- see
        # bistability_deficit() and the module docstring's "Signed SNM"
        # note. Dropping it would understate a failure as a measurement
        # error, which is exactly the failure a Monte Carlo yield campaign
        # exists to count.
        deficit = bistability_deficit(pts1, pts2, crossings)
        if deficit is None:
            raise ValueError(
                f"f2(f1(x))-x has {len(crossings)} root(s), not the 3 required "
                "for a bistable cell (low/meta/high), and no sampled point far "
                "enough from those roots to measure a bistability deficit from "
                "-- not a valid butterfly curve at this corner/trial"
            )
        return -deficit, -deficit
    # Exactly 3 is the common case. If more survive dedup (a noisy or
    # near-tangent corner), take the outermost pair as the stable states
    # and the crossing nearest their midpoint as the metastable point --
    # the two lobes of interest are still bounded by the true extremes.
    x_lo, x_hi = crossings[0], crossings[-1]
    interior = crossings[1:-1]
    x_mid = (
        min(interior, key=lambda c: abs(c - (x_lo + x_hi) / 2))
        if interior
        else (x_lo + x_hi) / 2
    )

    def max_gap(x_start: float, x_end: float) -> float:
        # Sample within [x_start, x_end] over pts1's grid, evaluating the
        # vertical distance between curve 1 (f1(x)) and the mirror image of
        # curve 2 about y=x (f2^-1(x)) -- found by bisection (solve_inverse),
        # not a sorted inverse table. This vertical gap (a constant-x
        # cross-section between the curve and the other curve's reflection
        # about the diagonal) is directly the side length of the largest
        # axis-aligned square inscribed between the two curves, per
        # Seevinck et al. 1987's construction -- no additional geometric
        # factor is needed, symmetric or not.
        best = 0.0
        for x, y in pts1:
            if x_start <= x <= x_end:
                y_inv = solve_inverse(pts2, x)
                best = max(best, abs(y_inv - y))
        return best

    lo_gap = max_gap(x_lo, x_mid)
    hi_gap = max_gap(x_mid, x_hi)
    return lo_gap, hi_gap


def _run(pts1: Curve, pts2: Curve | None, label: str) -> int:
    try:
        lo, hi = snm(pts1, pts2)
    except ValueError as exc:
        print(f"RESULT-ERROR: {label} -- {exc}", file=sys.stderr)
        return 1
    margin = min(lo, hi)
    print(f"RESULT: {label}_lobe_low_v = {lo:.6f}")
    print(f"RESULT: {label}_lobe_high_v = {hi:.6f}")
    print(f"RESULT: {label}_v = {margin:.6f}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--pair":
        if len(args) != 4:
            print("usage: snm_extract.py --pair <data-file-1> <data-file-2> <label>", file=sys.stderr)
            return 2
        path1, path2, label = args[1], args[2], args[3]
        pts1, pts2 = read_xy(path1), read_xy(path2)
        if len(pts1) < 5 or len(pts2) < 5:
            print(f"RESULT-ERROR: {label} -- fewer than 5 data points in {path1} or {path2}", file=sys.stderr)
            return 1
        pts1.sort(key=lambda p: p[0])
        pts2.sort(key=lambda p: p[0])
        return _run(pts1, pts2, label)

    if len(args) < 2:
        print("usage: snm_extract.py <data-file> <label>", file=sys.stderr)
        print("       snm_extract.py --pair <data-file-1> <data-file-2> <label>", file=sys.stderr)
        return 2
    data_path, label = args[0], args[1]
    pts = read_xy(data_path)
    if len(pts) < 5:
        print(f"RESULT-ERROR: {label} -- fewer than 5 data points in {data_path}", file=sys.stderr)
        return 1
    pts.sort(key=lambda p: p[0])
    return _run(pts, None, label)


if __name__ == "__main__":
    raise SystemExit(main())
