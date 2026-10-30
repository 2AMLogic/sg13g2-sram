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
  write <report> <label>
      Write margin per corner from the flip flags of the 33 bit-line levels.

Monte Carlo (sim/bitcell/run_bitcell_mc.sh; reports from `klt sim` with `monte_carlo`):
  mc-request <base.json> <out.json> <process> <vdd> <temp_c> <n> <seed> [--netlist PATH]
      One corner point as a mismatch Monte Carlo request (`<process>_mismatch` section).
      n = 0 gives the deterministic request instead (plain `<process>` section, no sampling).
  mc-snm <report> <label>      per-sample hold/read SNM and the instance-asymmetry check.
  mc-write <report> <label>    per-sample write margin (single-cell bench_write_mc.cir).
  mc-yield-set <mc-snm.json> <mc-write.json> <out.json>
      A `klt yield` sample-set document: strictly positive lower limit (0 V, exclusive).
  mc-negctl <ref mc-snm.json> <negctl mc-snm.json>
      Exit 0 iff the negative-control read SNM sits clearly below the reference's.
  mc-same <a.json> <b.json>    exit 0 iff two sample files hold identical values.

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


_SNM_NODES = {
    "hold": ("v(qha)", "v(qbha)", "v(qbhb)", "v(qhb)"),
    "read": ("v(qra)", "v(qbra)", "v(qbrb)", "v(qrb)"),
}


def _snm_entry(cols: dict[str, list[float]], cdir: Path | None = None, tag: str = "") -> dict:
    """Hold/read SNM (and the vgap value) from one DC report's columns; the curves
    go to <cdir>/<tag>.<kind>.curve{1,2}.csv when cdir is given. `*_asym_v` is the
    largest difference between the two identical instances' responses at the same
    forced voltage: 0 when the instances are identical, > 0 when mismatch is live."""
    entry: dict = {}
    for kind, (qa, qba, qbb, qb) in _SNM_NODES.items():
        # curve 1: Q -> QB (instance a forces Q); curve 2: QB -> Q (instance b forces QB)
        if cdir is not None:
            _write_csv(cdir / f"{tag}.{kind}.curve1.csv", cols[qa], cols[qba])
            _write_csv(cdir / f"{tag}.{kind}.curve2.csv", cols[qbb], cols[qb])
        p1 = sorted(zip(cols[qa], cols[qba]))
        p2 = sorted(zip(cols[qbb], cols[qb]))
        sq, vgap = signed_snm(p1, p2)
        entry[f"{kind}_snm_v"] = sq
        # snm_extract.py vertical-gap value: over-reads, kept for traceability
        entry[f"{kind}_snm_vgap_v"] = vgap
        entry[f"{kind}_asym_v"] = max(abs(a - b) for a, b in zip(cols[qba], cols[qb]))
    return entry


def cmd_snm(report: str, art_root: str, curves_dir: str, label: str) -> dict:
    rep = load_report(report)
    cdir = Path(curves_dir) if curves_dir else None
    if cdir:
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
        entry.update(_snm_entry(cols, cdir, cid.replace("/", "_")))
        out["corners"].append(entry)
    return out


def cmd_write(report: str, label: str) -> dict:
    rep = load_report(report)
    out = {"label": label, "kind": "simulated", "bl_step_v": BL_STEP_V,
           "pulse_ns": 1.0, "decision": "flipped iff Q<QB at end of pulse (1.3 ns) and at 2.5 ns",
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


# --- Monte Carlo -----------------------------------------------------------------------------
# Spec (spec/sram.md, Statistical treatment): the margins are statistical rows with a "strictly
# positive" lower limit and no numeric target_yield (none is introduced here).
MC_LIMITS = {"min": 0.0, "exclusive_min": True}
MC_MEASUREMENTS = (("hold_snm_v", "hold_snm_v"), ("read_snm_v", "read_snm_v"), ("write_margin_v", "write_margin_v"))
NEGCTL_SIGMA = 3.0


def cmd_mc_request(base: str, dst: str, process: str, vdd: float, temp: float, n: int, seed: int,
                   netlist: str | None) -> None:
    r = json.load(open(base))
    section = process.removesuffix("_mismatch") + ("_mismatch" if n else "")
    r["corners"] = {"process": [section], "supply_v": {"vdd": [vdd]}, "temperature_c": [temp]}
    r.pop("monte_carlo", None)
    if n:
        r["monte_carlo"] = {"n": n, "seed": seed, "vary": "mismatch"}
    if netlist:
        r["netlist"] = netlist
    json.dump(r, open(dst, "w"), indent=2)
    open(dst, "a").write("\n")


def _mc_wrap(res: dict, report: str) -> dict:
    """Attach the sample index and seeds from the klt report to each per-sample entry."""
    rep = load_report(report)
    info = {c["corner_id"]: c.get("monte_carlo") or {} for c in rep["corners"]}
    mc = rep.get("environment", {}).get("monte_carlo", {})
    res["monte_carlo"] = {k: mc.get(k) for k in ("n", "seed", "vary")}
    res["monte_carlo"]["family_mismatch"] = mc.get("family_mismatch")
    res["samples"] = res.pop("corners")
    for e in res["samples"]:
        e["sample_index"] = info.get(e["corner_id"], {}).get("sample_index")
        e["mismatch_seed"] = info.get(e["corner_id"], {}).get("mismatch_seed")
    res["samples"].sort(key=lambda e: (e["sample_index"] is None, e["sample_index"]))
    return res


def cmd_mc_snm(report: str, label: str) -> dict:
    return _mc_wrap(cmd_snm(report, "", "", label), report)


def cmd_mc_write(report: str, label: str) -> dict:
    return _mc_wrap(cmd_write(report, label), report)


def _stats(vals: list[float]) -> tuple[float, float]:
    mean = sum(vals) / len(vals)
    sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
    return mean, sd


def _values(samples: list[dict], key: str) -> list[float]:
    return [e[key] for e in samples if e.get(key) is not None]


def negctl_detected(ref: list[float], neg: list[float]) -> bool:
    """True iff the negative control's mean sits more than NEGCTL_SIGMA times the larger of the
    two sample standard deviations below the reference's mean ("clearly below"), so overlapping
    distributions do not pass."""
    if len(ref) < 2 or len(neg) < 2:
        return False
    (mr, sr), (mn, sn) = _stats(ref), _stats(neg)
    return mr - mn > NEGCTL_SIGMA * max(sr, sn, 1e-12)


def yield_set(snm: dict, write: dict | None) -> dict:
    """A `klt yield` sample-set document. A sample with no value (no butterfly eye, or no flip even
    with the bit line at 0 V) is counted as a failure through `failed_unmeasurable`, never dropped."""
    meas = []
    for name, key in MC_MEASUREMENTS:
        src = write if name == "write_margin_v" else snm
        if src is None:
            continue
        rows = [e for e in src["samples"] if "error" not in e]
        vals = _values(rows, key)
        meas.append({"name": name, "unit": "V", "samples": vals, "failed_unmeasurable": len(rows) - len(vals),
                     "errored": len(src["samples"]) - len(rows), "limits": dict(MC_LIMITS)})
    return {"measurements": meas}


def same_samples(a: dict, b: dict) -> bool:
    keys = ("hold_snm_v", "read_snm_v", "write_margin_v")
    ra = [tuple(e.get(k) for k in keys) for e in a["samples"]]
    rb = [tuple(e.get(k) for k in keys) for e in b["samples"]]
    return bool(ra) and ra == rb


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
        print(json.dumps(cmd_write(a[1], a[2]), indent=2))
    elif a[0] == "mc-request":
        cmd_mc_request(a[1], a[2], a[3], float(a[4]), float(a[5]), int(a[6]), int(a[7]),
                       a[9] if len(a) > 9 and a[8] == "--netlist" else None)
    elif a[0] == "mc-snm":
        print(json.dumps(cmd_mc_snm(a[1], a[2]), separators=(",", ":")))
    elif a[0] == "mc-write":
        print(json.dumps(cmd_mc_write(a[1], a[2]), separators=(",", ":")))
    elif a[0] == "mc-yield-set":
        w = json.load(open(a[2])) if a[2] != "-" else None
        json.dump(yield_set(json.load(open(a[1])), w), open(a[3], "w"), indent=2)
        open(a[3], "a").write("\n")
    elif a[0] == "mc-negctl":
        r, n = json.load(open(a[1])), json.load(open(a[2]))
        ok = negctl_detected(_values(r["samples"], "read_snm_v"), _values(n["samples"], "read_snm_v"))
        print("detected" if ok else "NOT detected")
        return 0 if ok else 1
    elif a[0] == "mc-same":
        ok = same_samples(json.load(open(a[1])), json.load(open(a[2])))
        print("identical" if ok else "DIFFERENT")
        return 0 if ok else 1
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
