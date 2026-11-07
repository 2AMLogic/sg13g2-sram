#!/usr/bin/env python3
"""Post-processing for sim/bitcell/run_bitcell.sh (hold/read SNM, write margin).

Subcommands (all inputs are `klt sim` report envelopes, plain or .json.gz):

  typical-request <in.json> <out.json> [--netlist PATH]
      Derive the single-point request (mos_tt, 1.20 V, 27 C) from a grid request.
  negctl-bench <bench.cir> <out.cir> <cell.spice>
      Rewrite a bench's .include to point at a different cell netlist.
  snm <report> <unused> <curves-dir> <label>
      Hold/read SNM per corner from the returned DC waveforms, extracted with
      sim/lib/common/snm_extract.py (pair mode: two independent VTCs). Writes
      the four VTC curves per corner as CSV into <curves-dir>, prints JSON.
  write <report> <label> [--pulse-ns N]
      Write margin per corner from the flip flags of the 33 bit-line levels, and
      the BL = 0 V flip time (tflip_0) against the N ns wordline window (default 1).
  sweep-request <request.json> <bench.cir> <out-dir> <pulse-ns> <cell.spice>
      Derive the request and bench for a wordline pulse of <pulse-ns> (sampling
      times follow the pulse) and the sweep corner subset, into <out-dir>.
  write-sweep <label> <pulse-ns>=<write.json> ...
      Tabulate write margin and flip time per corner across pulse widths.

SNM is the inscribed-square side (square_snm, the Seevinck construction klt's own
`snm` measurement uses). snm_extract.py's vertical-gap value is recorded beside it
as `*_snm_vgap_v`; it over-reads the square. A cell with no butterfly eye falls
back to snm_extract.py's signed bistability deficit (<= 0), so a failing corner
is counted, not dropped.
Everything printed is labelled `simulated`.
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib" / "common"))
import snm_extract  # noqa: E402

BL_STEP_V = 0.025
N_LEVELS = 33
WL_T0_NS = 0.3  # wordline rise start in bench_write.cir
WL_EDGE_NS = 0.02  # wordline rise/fall time in bench_write.cir
# end-of-pulse sample sits at WL_T0_NS + pw, the final sample 1.2 ns later and the run
# ends 0.5 ns after that: 1.3 / 2.5 / 3 ns at pw = 1 ns, as in the first record
FINAL_AFTER_END_NS = 1.2
STOP_AFTER_FINAL_NS = 0.5
# 3 worst write-margin corners of the 45-corner record are mos_sf/1.08 V/-40 C (0.250 V),
# mos_sf/1.08 V/25 C (0.275 V) and a tie at 0.300 V (mos_ss and mos_tt, 1.08 V, -40 C);
# klt corners are a Cartesian grid, so the sweep runs the grid that contains all four
SWEEP_CORNERS = {"process": ["mos_sf", "mos_ss", "mos_tt"], "supply_v": {"vdd": [1.08]}, "temperature_c": [-40, 25]}


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


def load_report(path: str) -> dict:
    p = Path(path)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "rt") as f:
        return json.load(f)


def cmd_typical_request(src: str, dst: str, netlist: str | None) -> None:
    r = json.load(open(src))
    r["corners"] = {"process": ["mos_tt"], "supply_v": {"vdd": [1.2]}, "temperature_c": [27]}
    if netlist:
        r["netlist"] = netlist
    json.dump(r, open(dst, "w"), indent=2)
    open(dst, "a").write("\n")


def _ns(x: float) -> str:
    return f"{x:.6g}n"


def cmd_sweep_request(src: str, bench: str, out_dir: str, pulse_ns: float, cell: str) -> None:
    """Write <out-dir>/{request.json,bench_write.cir,<cell>}: the write request with the
    wordline pulse width, the two sampling times and the run length set from pulse_ns,
    restricted to the sweep corners. The cell netlist is copied beside the bench."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    t_end = WL_T0_NS + pulse_ns
    t_fin = t_end + FINAL_AFTER_END_NS
    text = open(bench).read()
    if ".param pw=1n" not in text:
        raise SystemExit("sweep-request: bench has no '.param pw=1n' line")
    out = []
    for line in text.splitlines():
        if line.startswith(".param pw="):
            line = f".param pw={_ns(pulse_ns)}"
        elif line.startswith(".include"):
            line = f".include ./{Path(cell).name}"
        out.append(line)
    (d / "bench_write.cir").write_text("\n".join(out) + "\n")
    (d / Path(cell).name).write_text(open(cell).read())
    r = json.load(open(src))
    r["corners"] = SWEEP_CORNERS
    r["netlist"] = "bench_write.cir"
    r["analysis"]["args"] = f"5p {_ns(t_fin + STOP_AFTER_FINAL_NS)}"
    for m in r["measurements"]:
        m["spice"] = m["spice"].replace("AT=1.3n", f"AT={_ns(t_end)}").replace("AT=2.5n", f"AT={_ns(t_fin)}")
    json.dump(r, open(d / "request.json", "w"), indent=2)
    open(d / "request.json", "a").write("\n")


def flip_time_check(flip_time_s: float | None, pulse_ns: float) -> str:
    """Classify the BL = 0 V flip time (50 % WL rise to Q = QB) against the wordline
    window, which at 50 % points is the pulse width plus one edge time."""
    if flip_time_s is None:
        return "never_flips"
    return "within_pulse" if flip_time_s * 1e9 <= pulse_ns + WL_EDGE_NS else "after_pulse_end"


def cmd_negctl_bench(bench: str, dst: str, cell: str) -> None:
    text = open(bench).read()
    out = []
    for line in text.splitlines():
        if line.startswith(".include"):
            line = f".include {cell}"
        out.append(line)
    open(dst, "w").write("\n".join(out) + "\n")


def _columns(wave_json: str) -> dict[str, list[float]]:
    d = json.load(open(wave_json))
    names = [v["name"] for v in d["variables"]]
    cols = {n: [] for n in names}
    for row in d["points"]:
        for n, v in zip(names, row):
            cols[n].append(v)
    return cols


def _write_csv(path: Path, x: list[float], y: list[float]) -> None:
    path.write_text("".join(f"{a:.9g} {b:.9g}\n" for a, b in zip(x, y)))


def cmd_snm(report: str, art_root: str, curves_dir: str, label: str) -> dict:
    rep = load_report(report)
    cdir = Path(curves_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    out = {"label": label, "kind": "simulated", "corners": []}
    for c in rep["corners"]:
        cid = c["corner_id"]
        entry = {"corner_id": cid, "klt_status": c["status"]}
        wave = (c.get("artifacts") or {}).get("waveform")
        if c["status"] == "error" or not wave:
            entry["error"] = "; ".join(d["message"] for d in c.get("diagnostics", []))[:300]
            out["corners"].append(entry)
            continue
        cols = _columns(wave)
        tag = cid.replace("/", "_")
        for kind, (qa, qba, qbb, qb) in {
            "hold": ("v(qha)", "v(qbha)", "v(qbhb)", "v(qhb)"),
            "read": ("v(qra)", "v(qbra)", "v(qbrb)", "v(qrb)"),
        }.items():
            # curve 1: Q -> QB (instance a forces Q); curve 2: QB -> Q (instance b forces QB)
            _write_csv(cdir / f"{tag}.{kind}.curve1.csv", cols[qa], cols[qba])
            _write_csv(cdir / f"{tag}.{kind}.curve2.csv", cols[qbb], cols[qb])
            p1 = sorted(zip(cols[qa], cols[qba]))
            p2 = sorted(zip(cols[qbb], cols[qb]))
            sq, vgap = signed_snm(p1, p2)
            entry[f"{kind}_snm_v"] = sq
            # snm_extract.py vertical-gap value: over-reads, kept for traceability
            entry[f"{kind}_snm_vgap_v"] = vgap
        out["corners"].append(entry)
    return out


def cmd_write(report: str, label: str, pulse_ns: float = 1.0) -> dict:
    rep = load_report(report)
    out = {"label": label, "kind": "simulated", "bl_step_v": BL_STEP_V, "pulse_ns": pulse_ns,
           "decision": f"flipped iff Q<QB at end of pulse ({_ns(WL_T0_NS + pulse_ns)}) and "
                       f"{_ns(WL_T0_NS + pulse_ns + FINAL_AFTER_END_NS)} after it",
           "corners": []}
    for c in rep["corners"]:
        entry = {"corner_id": c["corner_id"], "klt_status": c["status"]}
        m = {x["name"]: x["value"] for x in c.get("measurements", [])}
        try:
            flips = [m[f"d_end_{k}"] < 0 and m[f"d_fin_{k}"] < 0 for k in range(N_LEVELS)]
        except (KeyError, TypeError):
            entry["error"] = "; ".join(d["message"] for d in c.get("diagnostics", []))[:300] or "missing flip measurements"
            out["corners"].append(entry)
            continue
        tf = m.get("tflip_0")
        entry["flip_time_s"] = tf if isinstance(tf, (int, float)) else None
        entry["flip_time_check"] = flip_time_check(entry["flip_time_s"], pulse_ns)
        entry["flips"] = "".join("1" if f else "0" for f in flips)
        top = max((k for k, f in enumerate(flips) if f), default=None)
        entry["monotonic"] = all(flips[k] for k in range(top + 1)) if top is not None else True
        if top is None:
            entry["write_margin_v"] = None
            entry["note"] = "no flip even with BL at 0 V: write margin not positive"
        else:
            entry["write_margin_v"] = round(top * BL_STEP_V, 6)
            entry["saturated"] = top == N_LEVELS - 1
        out["corners"].append(entry)
    return out


def cmd_write_sweep(label: str, runs: list[tuple[float, str]]) -> dict:
    """Per corner: write margin and flip time at every pulse width (runs = (ns, write.json))."""
    by_corner: dict[str, dict] = {}
    for pulse_ns, path in sorted(runs):
        for c in json.load(open(path))["corners"]:
            by_corner.setdefault(c["corner_id"], {})[_ns(pulse_ns)] = {
                k: c.get(k) for k in ("write_margin_v", "flip_time_s", "flip_time_check", "error")
                if k in c}
    return {"label": label, "kind": "simulated", "pulse_widths_ns": [p for p, _ in sorted(runs)],
            "corners": [{"corner_id": cid, "by_pulse": v} for cid, v in sorted(by_corner.items())]}


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr)
        return 2
    if a[0] == "typical-request":
        cmd_typical_request(a[1], a[2], a[4] if len(a) > 4 and a[3] == "--netlist" else None)
    elif a[0] == "negctl-bench":
        cmd_negctl_bench(a[1], a[2], a[3])
    elif a[0] == "snm":
        print(json.dumps(cmd_snm(a[1], a[2], a[3], a[4]), indent=2))
    elif a[0] == "write":
        pulse = float(a[4]) if len(a) > 4 and a[3] == "--pulse-ns" else 1.0
        print(json.dumps(cmd_write(a[1], a[2], pulse), indent=2))
    elif a[0] == "sweep-request":
        cmd_sweep_request(a[1], a[2], a[3], float(a[4]), a[5])
    elif a[0] == "write-sweep":
        print(json.dumps(cmd_write_sweep(a[1], [(float(x.split("=")[0]), x.split("=", 1)[1]) for x in a[2:]]), indent=2))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
