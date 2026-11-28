#!/usr/bin/env python3
"""Request generation and post-processing for sim/column/run_column.sh.

Subcommands (reports are `klt sim` envelopes, plain or .json.gz):

  request read|write <out.json> [--netlist PATH]
      Write the single-point (mos_tt, 1.20 V, 27 C) `klt sim` request for a bench.
  negctl-bench <bench.cir> <out.cir> [--replace NAME.spice=PATH] [--sae-delay-ns X]
      Copy a bench for a negative control: re-point its design includes so they
      resolve from <out.cir>'s directory, optionally swap one block netlist, and
      optionally move the SAE rise earlier.
  sizing <label> <width_um>=<report> ...
      Write-driver width sweep summary (flip time and verdict per width and case).
  read|write <report> <label>
      Per-case verdicts from the measurements; prints JSON, every number `simulated`.

Pass/fail limits here are the bench's functional criteria, not spec values.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib" / "common"))
from post_common import base_request, load_report, meas as _meas, negctl_bench, parse_negctl_args  # noqa: E402

VDD = 1.2
T_WL_MID_NS = 0.51          # bench_write.cir: 50 % point of the WL rise
PULSE_NS = 1.0
RESOLVED_V = 1.0            # |OUT-OUTB| after latching
RETAIN_V = 0.8              # |Q-QB| of a retained cell
PRE_V = 1.15                # bit line level before WL (precharge done)
EQ_V = 0.02                 # |BL-BLB| before WL (equalize done)
HS_BL_MIN_V = 0.6           # half-selected column bit line must not collapse

# case -> (instance, stored value of the selected cell before the access)
READ_CASES = {"a": ("xa", 1), "b": ("xb", 0)}
WRITE_CASES = {"c": ("xc", 1), "d": ("xd", 0)}   # written value is the opposite


def measurements(kind: str) -> list[dict]:
    m = []
    if kind == "read":
        for c, (x, _) in READ_CASES.items():
            o, ob = {"a": ("oa", "oba"), "b": ("ob", "obb")}[c]
            m += [_meas(f"rd_{c}", f"v({o})-v({ob})", "2.0n"),
                  _meas(f"eq_{c}", f"v({x}.bl0)-v({x}.blb0)", "0.78n"),
                  _meas(f"pre_{c}", f"v({x}.bl0)", "0.78n"),
                  _meas(f"eq1_{c}", f"v({x}.bl1)-v({x}.blb1)", "0.78n"),
                  _meas(f"dbl_{c}", f"v({x}.bl0)-v({x}.blb0)", "1.2n"),
                  _meas(f"ret_{c}", f"v({x}.q0)-v({x}.qb0)", "2.8n"),
                  _meas(f"hs_{c}", f"v({x}.q1)-v({x}.qb1)", "2.8n"),
                  {"name": f"hsbl_{c}", "unit": "V",
                   "spice": f".meas tran hsbl_{c} MIN par('min(v({x}.bl1),v({x}.blb1))') FROM=0.8n TO=1.9n"}]
    else:
        for c, (x, _) in WRITE_CASES.items():
            m += [_meas(f"fl_{c}", f"v({x}.q0)-v({x}.qb0)", "1.5n"),
                  _meas(f"ff_{c}", f"v({x}.q0)-v({x}.qb0)", "2.8n"),
                  _meas(f"hs_{c}", f"v({x}.q1)-v({x}.qb1)", "2.8n"),
                  _meas(f"blw_{c}", f"v({x}.bl0)-v({x}.blb0)", "1.4n"),
                  {"name": f"tf_{c}", "unit": "s",
                   "spice": f".meas tran tf_{c} WHEN v({x}.q0)=v({x}.qb0) CROSS=1 TD=0.45n"},
                  {"name": f"hsbl_{c}", "unit": "V",
                   "spice": f".meas tran hsbl_{c} MIN par('min(v({x}.bl1),v({x}.blb1))') FROM=0.5n TO=1.6n"}]
    return m


def make_request(kind: str, netlist: str | None = None) -> dict:
    return base_request({"process": ["mos_tt"], "supply_v": {"vdd": [1.2]}, "temperature_c": [27]},
                        netlist or f"bench_{kind}.cir", {"kind": "tran", "args": "5p 3n"},
                        measurements(kind), timeout_s=600)


def verdict_read(m: dict) -> dict:
    """Per-case verdict for the read bench from a {measurement: value} dict."""
    out = {}
    for c, (_, stored) in READ_CASES.items():
        e = 1 if stored else -1
        g = lambda k: m.get(f"{k}_{c}")
        try:
            row = {"stored": stored, "dout_v": g("rd"), "bl_diff_at_sae_v": g("dbl"),
                   "precharge_bl_v": g("pre"), "equalize_err_v": max(abs(g("eq")), abs(g("eq1"))),
                   "selected_cell_after_v": g("ret"), "half_selected_cell_after_v": g("hs"),
                   "half_selected_bl_min_v": g("hsbl")}
            row["checks"] = {
                "sense_resolves_stored_value": e * row["dout_v"] > RESOLVED_V,
                "bit_line_differential_has_right_sign": e * row["bl_diff_at_sae_v"] > 0,
                "precharged": row["precharge_bl_v"] > PRE_V,
                "equalized": row["equalize_err_v"] < EQ_V,
                "selected_cell_retained": e * row["selected_cell_after_v"] > RETAIN_V,
                "half_selected_cell_retained": -e * row["half_selected_cell_after_v"] > RETAIN_V,
                "unselected_column_bit_lines_hold": row["half_selected_bl_min_v"] > HS_BL_MIN_V,
            }
        except (KeyError, TypeError):
            row = {"error": "missing or non-numeric measurement"}
            row["checks"] = {}
        row["pass"] = bool(row["checks"]) and all(row["checks"].values())
        out[c] = row
    return out


def verdict_write(m: dict) -> dict:
    out = {}
    for c, (_, stored) in WRITE_CASES.items():
        w = -1 if stored else 1          # sign of Q-QB once the written value has taken
        g = lambda k: m.get(f"{k}_{c}")
        try:
            tf = g("tf")
            row = {"stored_before": stored, "written": 1 - stored,
                   "q_minus_qb_at_pulse_end_v": g("fl"), "q_minus_qb_at_2p8ns_v": g("ff"),
                   "flip_time_ns": None if tf is None else round(tf * 1e9 - T_WL_MID_NS, 4),
                   "bl_split_during_write_v": g("blw"),
                   "half_selected_cell_after_v": g("hs"), "half_selected_bl_min_v": g("hsbl")}
            flip = row["flip_time_ns"]
            row["checks"] = {
                "flipped_within_1ns_pulse": w * row["q_minus_qb_at_pulse_end_v"] > RETAIN_V - 0.3
                                             and flip is not None and flip < PULSE_NS,
                "written_value_holds": w * row["q_minus_qb_at_2p8ns_v"] > RETAIN_V,
                "half_selected_cell_retained": (1 if stored == 0 else -1) * row["half_selected_cell_after_v"] > RETAIN_V,
                "unselected_column_bit_lines_hold": row["half_selected_bl_min_v"] > HS_BL_MIN_V,
            }
        except (KeyError, TypeError):
            row = {"error": "missing or non-numeric measurement", "checks": {}}
        row["pass"] = bool(row["checks"]) and all(row["checks"].values())
        out[c] = row
    return out


def cmd_verdict(kind: str, report: str, label: str) -> dict:
    corner = load_report(report)["corners"][0]
    m = {x["name"]: x["value"] for x in corner.get("measurements", [])}
    out = {"label": label, "kind": "simulated", "corner_id": corner["corner_id"],
           "klt_status": corner["status"], "cases": (verdict_read if kind == "read" else verdict_write)(m)}
    if not m:
        out["error"] = "; ".join(d["message"] for d in corner.get("diagnostics", []))[:300] or "no measurements"
    out["all_pass"] = all(c["pass"] for c in out["cases"].values())
    out["any_fail"] = not out["all_pass"]
    return out


def cmd_sizing(label: str, items: list[str]) -> dict:
    """Summarise a write-driver width sweep; items are `<width_um>=<report>`."""
    rows = []
    for it in items:
        w, rep = it.split("=", 1)
        v = cmd_verdict("write", rep, f"{label}_w{w}")
        rows.append({"width_um": float(w), "klt_status": v["klt_status"], "pass": v["all_pass"],
                     "flip_time_ns": {c: x.get("flip_time_ns") for c, x in v["cases"].items()},
                     "failed_checks": {c: [k for k, ok in x["checks"].items() if not ok]
                                       for c, x in v["cases"].items() if not x["pass"]}})
    rows.sort(key=lambda r: r["width_um"])
    passing = [r["width_um"] for r in rows if r["pass"]]
    return {"label": label, "kind": "simulated", "corner": "mos_tt/1.200V/27C", "pulse_ns": PULSE_NS,
            "widths": rows, "min_passing_width_um": min(passing) if passing else None}


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr)
        return 2
    if a[0] == "request" and len(a) >= 3:
        json.dump(make_request(a[1], a[4] if len(a) > 4 and a[3] == "--netlist" else None), open(a[2], "w"), indent=2)
        open(a[2], "a").write("\n")
    elif a[0] == "negctl-bench" and len(a) >= 3:
        rep, other = parse_negctl_args(a, 3, ("--sae-delay-ns",))
        negctl_bench(a[1], a[2], rep, other.get("--sae-delay-ns"))
    elif a[0] == "sizing" and len(a) >= 3:
        print(json.dumps(cmd_sizing(a[1], a[2:]), indent=2))
    elif a[0] in ("read", "write") and len(a) >= 3:
        print(json.dumps(cmd_verdict(a[0], a[1], a[2]), indent=2))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
