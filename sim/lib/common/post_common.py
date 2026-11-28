"""Helpers shared by the SPICE post-processors (sim/bitcell, sim/column, sim/array).

Report loading, `klt sim` request boilerplate, the negative-control bench rewrite, waveform
column/CSV helpers and the SNM reduction. Pure Python, no simulator.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import snm_extract  # noqa: E402

OSDI = ["psp103", "psp103_nqs", "r3_cmc", "mosvar"]
MODELS = {"pdk": "ihp-sg13g2", "lib": "libs.tech/ngspice/models/cornerMOSlv.lib"}


def load_report(path: str) -> dict:
    p = Path(path)
    with (gzip.open if p.suffix == ".gz" else open)(p, "rt") as f:
        return json.load(f)


def meas(name: str, expr: str, at: str, unit: str = "V") -> dict:
    return {"name": name, "unit": unit, "spice": f".meas tran {name} FIND par('{expr}') AT={at}"}


def base_request(corners: dict, netlist: str, analysis: dict, measurements: list[dict],
                 timeout_s: int, **options) -> dict:
    """The `klt sim` request skeleton: ngspice, SG13G2 models, batch backend, OSDI preload."""
    pdk = "$PDK_ROOT/ihp-sg13g2/libs.tech/ngspice/osdi"
    return {
        "engine": "ngspice",
        "models": dict(MODELS),
        "corners": corners,
        "netlist": netlist,
        "backend": "batch",
        "analysis": analysis,
        "measurements": measurements,
        "options": {"osdi_preload": [f"{pdk}/{n}.osdi" for n in OSDI], **options, "timeout_s": timeout_s},
    }


def negctl_bench(bench: str, dst: str, replace: dict[str, str], sae_delay: str | None = None) -> None:
    """Copy a bench so its .include lines resolve from dst's directory; `replace` maps an included
    file name to a substitute path; `sae_delay` (ns) moves the Vsae pulse rise."""
    here = Path(bench).resolve().parent
    dst_dir = Path(dst).resolve().parent
    out = []
    for line in Path(bench).read_text().splitlines():
        mi = re.match(r"\.include\s+(\S+)", line)
        if mi:
            name = os.path.basename(mi.group(1))
            target = replace.get(name) or str((here / mi.group(1)).resolve())
            line = f".include {os.path.relpath(target, dst_dir) if not target.startswith('./') else target}"
        if sae_delay and line.startswith("Vsae"):
            line = re.sub(r"PULSE\(0 1\.2 \S+", f"PULSE(0 1.2 {sae_delay}n", line)
        out.append(line)
    Path(dst).write_text("\n".join(out) + "\n")


def parse_negctl_args(a: list[str], start: int, flags: tuple[str, ...] = ("--replace",)) -> tuple[dict, dict]:
    """Parse `--replace NAME=PATH` (repeatable) and other value flags from a[start:];
    returns (replace, {flag: value})."""
    replace: dict[str, str] = {}
    other: dict[str, str] = {}
    i = start
    while i < len(a):
        if a[i] == "--replace":
            k, v = a[i + 1].split("=", 1)
            replace[k] = v
        elif a[i] in flags:
            other[a[i]] = a[i + 1]
        i += 2
    return replace, other


def columns(wave_json: str) -> dict[str, list[float]]:
    d = json.load(open(wave_json))
    names = [v["name"] for v in d["variables"]]
    cols = {n: [] for n in names}
    for row in d["points"]:
        for n, v in zip(names, row):
            cols[n].append(v)
    return cols


def write_csv(path: Path, x: list[float], y: list[float]) -> None:
    path.write_text("".join(f"{a:.9g} {b:.9g}\n" for a, b in zip(x, y)))


def square_snm(p1: list[tuple[float, float]], p2: list[tuple[float, float]]) -> float | None:
    """Largest inscribed-square side of the butterfly of two VTCs, in volts.

    p1 = (Q, QB) samples of VTC 1, p2 = (QB, Q) samples of VTC 2. In the Q-QB
    plane the curves are C1 = {(q, f1(q))} and C2 = {(f2(qb), qb)}. Rotating by
    45 deg (u = (X-Y)/sqrt2, v = (X+Y)/sqrt2) makes the vertical gap between
    them at one u the diagonal of an inscribed square, so each eye's side is
    max(+-gap)/sqrt2 (Seevinck). The gap is piecewise linear, so its extremes
    sit at the knots of either curve. Returns min over the two eyes, or None
    when no gap was measurable. It does not decide bistability: use signed_snm().
    Same method as klt sim's
    native `snm` measurement, which the fleet runner does not support yet.
    """
    r2 = 2.0 ** 0.5
    c1 = [((x - y) / r2, (x + y) / r2) for x, y in p1]
    c2 = sorted((((x - y) / r2, (x + y) / r2) for y, x in p2))
    c1.sort()

    def interp(c, at):
        if at < c[0][0] or at > c[-1][0]:
            return None
        lo, hi = 0, len(c) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if c[mid][0] <= at:
                lo = mid
            else:
                hi = mid
        (u0, v0), (u1, v1) = c[lo], c[hi]
        return v0 if u1 == u0 else v0 + (v1 - v0) * (at - u0) / (u1 - u0)

    gaps = []
    for u in sorted({q[0] for q in c1} | {q[0] for q in c2}):
        a, b = interp(c1, u), interp(c2, u)
        if a is not None and b is not None:
            gaps.append(a - b)
    if not gaps:
        return None
    upper, lower = max(gaps) / r2, max(-g for g in gaps) / r2
    return min(upper, lower) if min(upper, lower) > 0 else None


def signed_snm(p1, p2) -> tuple[float | None, float | None]:
    """(snm, vgap). snm is the inscribed-square side when the cell is bistable;
    when snm_extract.py finds no three fixed points (monostable) it is that
    script's signed bistability deficit (< 0), so a failing corner is counted.
    vgap is snm_extract.py's vertical-gap value (over-reads), None on error."""
    try:
        vgap = min(snm_extract.snm(p1, p2))
    except ValueError:
        return square_snm(p1, p2), None
    if vgap <= 0:
        return vgap, vgap
    return square_snm(p1, p2), vgap
