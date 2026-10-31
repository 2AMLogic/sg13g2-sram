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

SNM is the inscribed-square side (square_snm, the Seevinck construction klt's own
`snm` measurement uses). snm_extract.py's vertical-gap value is recorded beside it
as `*_snm_vgap_v`; it over-reads the square. A cell with no butterfly eye falls
back to snm_extract.py's signed bistability deficit (<= 0), so a failing corner
is counted, not dropped.
Everything printed is labelled `simulated`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib" / "common"))
import snm_extract  # noqa: E402,F401  (re-exported for the tests)
from post_common import (  # noqa: E402,F401
    columns as _columns, load_report, signed_snm, square_snm, write_csv as _write_csv)

BL_STEP_V = 0.025
N_LEVELS = 33


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
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
