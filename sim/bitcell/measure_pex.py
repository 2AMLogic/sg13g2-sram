#!/usr/bin/env python3
"""Measurement harness for `klt pex --measure-command` on the bitcell (issue #228).

`klt pex` runs this command twice -- once per leg -- appending the netlist of
the leg under measurement as the final argument (also $KLT_PEX_NETLIST, with
$KLT_PEX_SIDE naming the leg):

  schematic leg: design/bitcell/bitcell.spice (the --reference-netlist)
  extracted leg: the parasitic-annotated extraction klt pex just wrote

For each leg this harness stages, under $KLT_PEX_ARTIFACTS_DIR:

  dut.spice         the handed netlist verbatim + the pin-order wrapper from
                    sim/bitcell/pex_reference.spice, whose inner X0 call is
                    rewritten to the handed netlist's own top and pin order
                    (both legs' benches then differ only in their DUT)
  bench_snm.cir     sim/bitcell/bench_snm.cir with the .include repointed at
  bench_write.cir   dut.spice and every X ... bitcell instance rewritten from
                    the schematic pin order (BL BLB WL VDD VSS Q QB) to the
                    extracted/common one (BL BLB Q QB VDD VSS WL)
  request_snm.json  sim/bitcell/request_{snm,write}.json with `netlist`
  request_write.json repointed at the staged bench and `corners` narrowed to
                    the four-point `corners.units` list below (bounding
                    corners + typical)

then submits each request with `klt sim --backend batch` (batch only, never a
local loop, per sim/README.md; the klt invocation is $PEX_KLT, default "klt")
and reduces the reports with the existing bitcell_post.py reducers. One JSON
measurement document is printed on stdout -- the contract klt pex expects:

  {"corners": [{"corner_id": ..., "measurements": [{name, value, status}]}]}

Rows: hold_snm, read_snm (V, inscribed square; <= 0 is a failing margin and
is preserved as such) and write_margin (V, 25 mV grid; a no-flip corner is
value null with the reason in `message`). Everything else this script wants
to keep (batch job ids, report digests) rides in a "provenance" key, which
the measurement contract ignores.

--stage-only writes the staged files and exits without simulating (for
inspecting the pin-order adaptation; nothing is printed on stdout).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bitcell_post  # noqa: E402

# The extracted top's pin order (klt extract writes pins in this order); the
# checked-in benches and design/bitcell/bitcell.spice use SCHEMATIC instead.
COMMON = ["BL", "BLB", "Q", "QB", "VDD", "VSS", "WL"]
SCHEMATIC = ["BL", "BLB", "WL", "VDD", "VSS", "Q", "QB"]
DUT_CELL = "bitcell_pexrc"

# The four measurement points (issue #228): the corner that bounds each
# margin in the schematic 45-corner grid (sim/bitcell/records/20261028T143337Z)
# plus the typical point, kept separate from the grid's 25 C middle exactly as
# run_bitcell.sh does.
POINTS = [
    ("mos_fs", 1.08, 125),  # worst read SNM in the schematic grid
    ("mos_sf", 1.08, -40),  # worst write margin
    ("mos_ff", 1.08, 125),  # worst hold SNM
    ("mos_tt", 1.20, 27),   # typical point
]


def corner_id(process: str, vdd: float, temp: int) -> str:
    return f"{process}/{vdd:.3f}V/{temp}C"


def parse_top(text: str) -> tuple[str, list[str]]:
    """(top subckt name, pin list) of the first .SUBCKT in a DUT netlist."""
    for line in text.splitlines():
        if line.lower().startswith(".subckt"):
            tokens = line.split()
            return tokens[1], tokens[2:]
    raise SystemExit(f"measure_pex.py: no .SUBCKT found in the handed netlist")


def stage(side: str, netlist_path: Path, art: Path) -> list[Path]:
    """Write dut.spice, both staged benches and both staged requests."""
    art.mkdir(parents=True, exist_ok=True)
    netlist_text = netlist_path.read_text()
    top, pins = parse_top(netlist_text)
    if sorted(pins) != sorted(COMMON):
        raise SystemExit(
            f"measure_pex.py: handed netlist top '{top}' pins {pins} are not the "
            f"bitcell pin set {sorted(COMMON)} -- refusing to guess a pin mapping"
        )

    # Pin-order wrapper: the committed pex_reference.spice block, with the
    # inner call rewritten to the handed top using that top's own pin order
    # (with the schematic leg's netlist the rewrite is the identity).
    ref = (HERE / "pex_reference.spice").read_text().splitlines()
    start = next(i for i, l in enumerate(ref) if l.upper().startswith((".SUBCKT " + DUT_CELL).upper()))
    end = next(i for i, l in enumerate(ref) if l.upper().startswith((".ENDS " + DUT_CELL).upper()))
    block = ref[start : end + 1]
    inner = "X0 " + " ".join(pins) + f" {top}"
    block = [inner if l.startswith("X0 ") else l for l in block]
    dut = art / "dut.spice"
    dut.write_text(
        f"* staged by measure_pex.py: side={side} top={top} pins={' '.join(pins)}\n"
        + netlist_text.rstrip("\n")
        + "\n\n"
        + "\n".join(block)
        + "\n"
    )

    # Benches: repoint the single .include at the staged DUT and rewrite every
    # positional X call from the schematic pin order to the common one.
    perm = [SCHEMATIC.index(p) for p in COMMON]  # node at COMMON[i] is bench token perm[i]
    staged = []
    for bench_name in ("bench_snm.cir", "bench_write.cir"):
        out = []
        for line in (HERE / bench_name).read_text().splitlines():
            if line.startswith(".include") or line.lower().startswith(".inc "):
                line = ".include dut.spice"
            else:
                tokens = line.split()
                if tokens and tokens[0].upper().startswith("X") and tokens[-1] == "bitcell":
                    if len(tokens) != 9:
                        raise SystemExit(
                            f"measure_pex.py: {bench_name}: unexpected X line '{line}' "
                            "(expected 7 nodes + cell name)"
                        )
                    nodes = tokens[1:8]
                    line = tokens[0] + " " + " ".join(nodes[i] for i in perm) + " " + DUT_CELL
                elif line.startswith("*") and sorted(tokens[1:]) == sorted(SCHEMATIC):
                    line = "*               " + "  ".join(COMMON)
            out.append(line)
        path = art / bench_name
        path.write_text("\n".join(out) + "\n")
        staged.append(path)

    # Requests: same document, staged bench, four explicit corner units.
    for req_name, bench in (("request_snm.json", "bench_snm.cir"), ("request_write.json", "bench_write.cir")):
        r = json.loads((HERE / req_name).read_text())
        r["netlist"] = bench
        r["corners"] = {
            "units": [
                {"process": p, "temperature_c": t, "supply_v": {"vdd": v}}
                for p, v, t in POINTS
            ]
        }
        path = art / req_name
        path.write_text(json.dumps(r, indent=2) + "\n")
        staged.append(path)
    return staged


def run_sim(klt: list[str], req: Path, art: Path, name: str, stderr_log: Path) -> Path:
    """One batch `klt sim`; returns the report path. Exit 0/3 are results; 4 is
    tolerated only with a non-empty report; anything else is a hard error."""
    report = art / f"report-{name}.json.gz"
    proc = subprocess.run(
        klt + [
            "sim", str(req), "--backend", "batch", "--wait-for-capacity", "600",
            "-o", str(art / name), "--report-out", str(report), "--format", "json",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    stderr_log.write_text(proc.stderr)
    if proc.returncode not in (0, 3) and not (
        proc.returncode == 4 and report.exists() and report.stat().st_size > 0
    ):
        tail = "\n".join(proc.stderr.splitlines()[-10:])
        raise SystemExit(
            f"measure_pex.py: klt sim {name} exited {proc.returncode}; batch error, "
            f"no local fallback. stderr tail:\n{tail}"
        )
    return report


def _report_meta(report: Path) -> dict:
    opener = gzip.open if report.suffix == ".gz" else open
    with opener(report, "rt") as f:
        env = json.load(f).get("environment", {})
    remote = env.get("remote", {})
    return {
        "report": report.name,
        "report_sha256": "sha256:" + hashlib.sha256(report.read_bytes()).hexdigest(),
        "batch_job_id": remote.get("job_id"),
        "runner_klt_version": remote.get("runner_klt_version"),
        "engine_version_banner": (env.get("engine_build", {}) or {}).get("version_banner"),
    }


def measure(side: str, netlist_path: Path, art: Path) -> dict:
    klt = shlex.split(os.environ.get("PEX_KLT", "klt"))
    art.mkdir(parents=True, exist_ok=True)
    curves = art / "curves"
    meta: dict[str, dict] = {}

    report = run_sim(klt, art / "request_snm.json", art, "snm", art / "snm.stderr")
    snm = bitcell_post.cmd_snm(str(report), "", str(curves), side)
    meta["snm"] = _report_meta(report)

    report = run_sim(klt, art / "request_write.json", art, "write", art / "write.stderr")
    wr = bitcell_post.cmd_write(str(report), side)
    meta["write"] = _report_meta(report)

    write_by_corner = {c["corner_id"]: c for c in wr["corners"]}
    corners = []
    for entry in snm["corners"]:
        cid = entry["corner_id"]
        measurements = []
        for name, key in (("hold_snm", "hold_snm_v"), ("read_snm", "read_snm_v")):
            v = entry.get(key)
            if v is None:
                measurements.append(
                    {"name": name, "value": None, "status": "error",
                     "message": entry.get("error") or "SNM not extractable on this corner"}
                )
            else:
                # a nonpositive SNM is a real, failing margin: keep the value
                measurements.append(
                    {"name": name, "value": v, "status": "fail" if v <= 0 else "pass"}
                )
        w = write_by_corner.get(cid)
        if w is None:
            measurements.append(
                {"name": "write_margin", "value": None, "status": "error",
                 "message": "write bench reported no such corner"}
            )
        else:
            v = w.get("write_margin_v")
            if v is None:
                measurements.append(
                    {"name": "write_margin", "value": None, "status": "error",
                     "message": w.get("error") or w.get("note") or "write margin not extractable"}
                )
            else:
                measurements.append({"name": "write_margin", "value": v, "status": "pass"})
        corners.append({"corner_id": cid, "measurements": measurements})

    top, pins = parse_top(netlist_path.read_text())
    return {
        "corners": corners,
        "provenance": {
            "side": side,
            "netlist_sha256": "sha256:" + hashlib.sha256(netlist_path.read_bytes()).hexdigest(),
            "top": top,
            "pins": pins,
            "corner_points": [
                {"process": p, "vdd_v": v, "temperature_c": t} for p, v, t in POINTS
            ],
            "batches": meta,
        },
    }


def main() -> int:
    args = sys.argv[1:]
    stage_only = "--stage-only" in args
    args = [a for a in args if a != "--stage-only"]
    side = None
    if "--side" in args:
        i = args.index("--side")
        side = args[i + 1]
        del args[i : i + 2]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    netlist = Path(args[0]).resolve()

    side = side or os.environ.get("KLT_PEX_SIDE", "schematic")
    art = Path(os.environ.get("KLT_PEX_ARTIFACTS_DIR", ".")).resolve() / f"stage-{side}"

    staged = stage(side, netlist, art)
    if stage_only:
        for p in staged:
            print(f"staged: {p}", file=sys.stderr)
        print("stage-only: nothing simulated, nothing printed on stdout", file=sys.stderr)
        return 0

    doc = measure(side, netlist, art)
    out = art / f"measurements-{side}.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps(doc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
