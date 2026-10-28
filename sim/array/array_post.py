#!/usr/bin/env python3
"""Request generation, bench generation and post-processing for sim/array/run_array.sh.

Subcommands (reports are `klt sim` envelopes, plain or .json.gz):

  request snm|write|access <out.json> [--netlist PATH] [--typical]
      The `klt sim` request for a bench: the spec's 45-corner grid (5 process x 3 supply x
      3 temperature, spec/sram.md), or with --typical the single point mos_tt / 1.20 V / 25 C (a
      point of the grid, so the negative controls, which run there, compare against a grid corner).
  gen-access <design/macro/macro.spice> <out.cir> [--check]
      Write bench_access.cir from the macro's own top-level connectivity; with --check, exit 1
      if the committed file differs from what would be generated.
  negctl-bench <bench.cir> <out.cir> [--replace NAME.spice=PATH]
      Copy a bench so its .include lines resolve from <out.cir>'s directory, optionally
      pointing one block netlist at a different file.
  weaken <in.spice> <out.spice> snm|write|access
      Negative-control netlist: snm = pull-downs halved and access devices doubled in the
      bitcell (beta 0.25); write, access = write-driver stacks at 0.15 um.
  snm <report> <curves-dir> <label>
      In-situ read SNM per corner (inscribed square of the returned DC butterfly).
  write <report> <label>
      Write margin through the real driver per corner.
  access <report> <label>
      Access time and write completion per corner.

Margins are recorded, not graded against a spec number (spec/sram.md): a corner "passes" when
its margin is strictly positive (SNM, write margin) or when the access cycle completed with the
right data (access). A corner with a missing or non-numeric measurement counts as failing.
Everything printed is labelled `simulated`.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "bitcell"))
import bitcell_post  # noqa: E402  (square_snm / signed_snm / waveform loader)

PROCESS = ["mos_tt", "mos_ss", "mos_ff", "mos_sf", "mos_fs"]
SUPPLY_V = [1.08, 1.2, 1.32]
TEMP_C = [-40, 25, 125]

BL_STEP_V = 0.025
N_LEVELS = 33
PULSE_NS = 1.0
T_WL_RISE_NS = 1.01          # bench_write.cir: 50 % point of the WL rise
T_END_NS = 1.95              # bench_write.cir: end of the pulse (before the WL fall at 2.03)
T_FINAL_NS = 3.4

# bench_access.cir: six cycles of 8 ns, CLK high 3 ns; the CLK rising edges (ns) of each cycle.
# read1 comes first only to put a 1 into the output latch; read1b follows a read of 0, so its Q
# transition is a clean rise.
ACCESS_PERIOD_NS = 8.0
ACCESS_HIGH_NS = 3.0
ACCESS_CYCLES = ["write1", "read1", "write0", "read0", "write1b", "read1b"]
ACCESS_EDGES_NS = {c: 4.0 + ACCESS_PERIOD_NS * i for i, c in enumerate(ACCESS_CYCLES)}
ACCESS_T_STOP_NS = 4.0 + ACCESS_PERIOD_NS * len(ACCESS_CYCLES)
ACCESS_ADDRESS = 0x5A        # A[7:1] = 45 selects WL[45]; A[0] = 0 selects column 0 (control: SEL0 = ~A0L)
ACCESS_ROW = 45
N_DUMMY_SLICES = 31          # bit slices 1..31 of the 32 I/O: control fan-out only
N_DUMMY_WL_CELLS = 62        # the other 31 slices x 2 bit-line pairs on the selected wordline

OSDI = ["psp103", "psp103_nqs", "r3_cmc", "mosvar"]


# --- requests -----------------------------------------------------------------------------

def _corners(typical: bool) -> dict:
    if typical:
        return {"process": ["mos_tt"], "supply_v": {"vdd": [1.2]}, "temperature_c": [25]}
    return {"process": PROCESS, "supply_v": {"vdd": SUPPLY_V}, "temperature_c": TEMP_C}


def _meas(name: str, expr: str, at: str, unit: str = "V") -> dict:
    return {"name": name, "unit": unit, "spice": f".meas tran {name} FIND par('{expr}') AT={at}"}


def _when(name: str, a: str, b: str, edge: str, td: str) -> dict:
    return {"name": name, "unit": "s", "spice": f".meas tran {name} WHEN v({a})=v({b}) {edge}=1 TD={td}"}


def write_measurements() -> list[dict]:
    m = []
    for c, x, bl in (("c", "xc", "bl0"), ("d", "xd", "blb0")):
        m += [_meas(f"fl_{c}", f"v({x}.q0)-v({x}.qb0)", f"{T_END_NS}n"),
              _meas(f"ff_{c}", f"v({x}.q0)-v({x}.qb0)", f"{T_FINAL_NS}n"),
              _meas(f"hs_{c}", f"v({x}.q1)-v({x}.qb1)", f"{T_FINAL_NS}n"),
              _meas(f"ldrv_{c}", f"v({x}.{bl})", f"{T_END_NS}n"),
              {"name": f"tf_{c}", "unit": "s",
               "spice": f".meas tran tf_{c} WHEN v({x}.q0)=v({x}.qb0) CROSS=1 TD=0.9n"}]
    for k in range(N_LEVELS):
        m += [_meas(f"d_end_{k}", f"v(q{k})-v(qb{k})", f"{T_END_NS}n"),
              _meas(f"d_fin_{k}", f"v(q{k})-v(qb{k})", f"{T_FINAL_NS}n")]
    return m


def access_measurements() -> list[dict]:
    e = ACCESS_EDGES_NS
    pre = lambda cyc: f"{e[cyc] - 1.0:g}n"
    end = lambda cyc: f"{e[cyc] + ACCESS_PERIOD_NS - 1.0:g}n"
    m = [{"name": "vdd_check", "unit": "V", "spice": ".meas tran vdd_check FIND par('v(vdd)') AT=1n"}]
    for cyc in ACCESS_CYCLES:
        m.append(_when(f"tclk_{cyc}", "clkm", "thr5", "RISE", pre(cyc)))
    # read: Q crosses 90 % (read of 1) or 10 % (read of 0) of VDD after the clock edge
    m += [_when("tq_read1b", "q0m", "thr9", "RISE", pre("read1b")),
          _when("tq_read0", "q0m", "thr1", "FALL", pre("read0")),
          _meas("qend_read1", "v(q0m)", end("read1")),
          _meas("qend_read0", "v(q0m)", end("read0")),
          _meas("qend_read1b", "v(q0m)", f"{ACCESS_T_STOP_NS - 1.0:g}n")]
    # write: the cell's storage nodes cross, then settle; wordline timing for reference
    for cyc in ("write1", "write0"):
        m += [_when(f"tflip_{cyc}", "cq", "cqb", "CROSS", pre(cyc)),
              _when(f"twl_rise_{cyc}", "wl45m", "thr5", "RISE", pre(cyc)),
              _meas(f"cell_after_{cyc}", "v(cq)-v(cqb)", end(cyc))]
    return m


def make_request(kind: str, typical: bool = False, netlist: str | None = None) -> dict:
    pdk = "$PDK_ROOT/ihp-sg13g2/libs.tech/ngspice/osdi"
    analysis = {"snm": {"kind": "dc", "args": "Vu 0 1 0.005"},
                "write": {"kind": "tran", "args": "5p 3.6n"},
                "access": {"kind": "tran", "args": f"50p {ACCESS_T_STOP_NS:g}n 0 50p"}}[kind]
    meas = {"snm": [{"name": "vdd_check", "unit": "V", "expr": "v(vdd)[0]"}],
            "write": write_measurements(), "access": access_measurements()}[kind]
    return {
        "engine": "ngspice",
        "models": {"pdk": "ihp-sg13g2", "lib": "libs.tech/ngspice/models/cornerMOSlv.lib"},
        "corners": _corners(typical),
        "netlist": netlist or f"bench_{kind}.cir",
        "backend": "batch",
        "analysis": analysis,
        "measurements": meas,
        "options": {"osdi_preload": [f"{pdk}/{n}.osdi" for n in OSDI],
                    "waveforms": kind == "snm", "keep_artifacts": kind == "snm",
                    "timeout_s": 1800 if kind == "access" else 600},
    }


# --- bench generation / negative-control netlists ---------------------------------------------

def _join_continuations(text: str) -> list[str]:
    out: list[str] = []
    for line in text.splitlines():
        if line.startswith("+") and out:
            out[-1] += " " + line[1:].strip()
        else:
            out.append(line)
    return out


def _wrap(line: str, width: int = 130) -> str:
    words, rows, cur = line.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            rows.append(cur)
            cur = "+ " + w
        else:
            cur = f"{cur} {w}" if cur else w
    rows.append(cur)
    return "\n".join(rows)


MACRO_TOP_INSTANCES = ("XAL", "XCTL", "XDEC", "XDL", "XS[0]", "XQL")


def macro_top_lines(macro_spice: str) -> dict[str, str]:
    """The macro subckt's own top-level instance lines (continuations joined), by instance name."""
    lines = _join_continuations(Path(macro_spice).read_text())
    start = next(i for i, l in enumerate(lines) if l.startswith(".subckt macro "))
    end = next(i for i in range(start, len(lines)) if lines[i].startswith(".ends"))
    out = {}
    for l in lines[start:end]:
        name = l.split(None, 1)[0] if l.strip() else ""
        if name in MACRO_TOP_INSTANCES:
            out[name] = l
    missing = [n for n in MACRO_TOP_INSTANCES if n not in out]
    if missing:
        raise SystemExit(f"array_post.py: macro.spice has no top-level instance {missing}")
    return out


def _bit(n: int, k: int) -> int:
    return (n >> k) & 1


def gen_access(macro_spice: str) -> str:
    top = macro_top_lines(macro_spice)
    L: list[str] = []
    a = L.append
    a("* Access-time bench: clock edge to valid Q, and write completion (circuit body for `klt sim`;")
    a("* no .control/.end). GENERATED by `array_post.py gen-access` from the top-level instances of")
    a("* design/macro/macro.spice; run_array.sh fails if this file is stale.")
    a("*")
    a("* Representative macro: the real address latch, control, row decoder, data latch and out latch")
    a("* (full 32-bit banks), and the real bit slice 0 (2 bit-line pairs x 128 cells, precharge, mux,")
    a("* sense amp, write driver) at the selected address. The other 31 I/O are represented by their")
    a(f"* load only: {N_DUMMY_SLICES} dummy slices (2 precharge, mux, sense amp, write driver on private bit lines)")
    a(f"* on PRE_B / SEL* / SAE / WE / DL[k] / DOUT[k], and {N_DUMMY_WL_CELLS} bitcells (their access gates) on the selected")
    a(f"* wordline WL[{ACCESS_ROW}]. Wordlines of other rows are not loaded: they do not switch at this address.")
    a("* Schematic level: no wire parasitics.")
    a("*")
    a(f"* Address 0x{ACCESS_ADDRESS:02X}: A[7:1] = {ACCESS_ROW} selects WL[{ACCESS_ROW}], A[0] = 0 selects column 0 (SEL0 high).")
    a(f"* Six cycles, {ACCESS_PERIOD_NS:g} ns period, CLK high {ACCESS_HIGH_NS:g} ns (rising 50 % at " +
      ", ".join(f"{ACCESS_EDGES_NS[c] + 0.05:g}" for c in ACCESS_CYCLES) + " ns):")
    a("*   write 1, read (expects 1), write 0, read (expects 0), write 1, read (expects 1).")
    a("* The first read only puts a 1 into the output latch; the last read follows a read of 0, so its Q rise is")
    a("* a clean transition. CEN low, GWEN = WEN low in the write cycles; address, data and controls change in the")
    a("* CLK-low phase (latches transparent), 3 ns before each edge. Every cell starts holding 0 (.ic).")
    a("* All levels scale with VDD (request supply corner).")
    a(".include ../../design/macro/macro.spice")
    a("")
    a("Vdd vdd 0 DC 1.2")
    a("* the macro's VSS port is a net named VSS, not node 0")
    a("Vvss VSS 0 DC 0")
    a("* thresholds that follow the supply corner")
    a("Bthr9 thr9 0 V = 0.9*v(vdd)")
    a("Bthr5 thr5 0 V = 0.5*v(vdd)")
    a("Bthr1 thr1 0 V = 0.1*v(vdd)")
    a("* clock: unit pulse x VDD")
    a(f"Vpclk pclk 0 PULSE(0 1 {ACCESS_EDGES_NS[ACCESS_CYCLES[0]]:g}n 100p 100p {ACCESS_HIGH_NS:g}n {ACCESS_PERIOD_NS:g}n)")
    a("Bclk CLK 0 V = v(pclk)*v(vdd)")
    a("Bclkm clkm 0 V = v(CLK)")
    a("Bcen CEN 0 V = 0")
    a("* GWEN = WEN: low (write) in cycles 1 and 3, high (read) in cycles 2 and 4")
    def pwl(level):   # level(cycle name) -> 0/1, switching 3 ns before each cycle's edge
        pts, prev = [], None
        for cyc in ACCESS_CYCLES:
            t, v = ACCESS_EDGES_NS[cyc] - 3.0, level(cyc)
            if prev is None:
                pts.append(f"0 {v}")
            elif v != prev:
                pts += [f"{t:g}n {prev}", f"{t + 0.1:g}n {v}"]
            prev = v
        return "PWL(" + " ".join(pts) + f" {ACCESS_T_STOP_NS + 5:g}n {prev})"
    a(f"Vpgw pgw 0 {pwl(lambda c: 0 if c.startswith('write') else 1)}")
    a("Bgwen GWEN 0 V = v(pgw)*v(vdd)")
    a("Bwen  WEN  0 V = v(pgw)*v(vdd)")
    a("* D[0]: 1 for the first write, 0 for the second")
    a(f"Vpd0 pd0 0 {pwl(lambda c: 0 if c == 'write0' else 1)}")
    a("Bd0 D[0] 0 V = v(pd0)*v(vdd)")
    for k in range(1, 32):
        a(f"Bd{k} D[{k}] 0 V = 0")
    for k in range(8):
        a(f"Ba{k} A[{k}] 0 V = {'v(vdd)' if _bit(ACCESS_ADDRESS, k) else '0'}")
    a("")
    a("* the macro, minus slices 1..31 (replaced by load below)")
    for name in ("XAL", "XCTL", "XDEC", "XDL", "XS[0]", "XQL"):
        a(_wrap(top[name]))
    a("")
    a(f"* dummy wordline load: the access gates of the other {N_DUMMY_WL_CELLS} cells on the selected row")
    for k in range(N_DUMMY_WL_CELLS):
        a(f"Xwl{k} vdd vdd WL[{ACCESS_ROW}] vdd 0 dq{k} dqb{k} bitcell")
    a("")
    a("* dummy slices: control and data fan-out of I/O 1..31 (bit lines private, otherwise floating)")
    for k in range(1, N_DUMMY_SLICES + 1):
        a(f"Xfp0_{k} PRE_B fb0_{k} fbb0_{k} vdd 0 precharge")
        a(f"Xfp1_{k} PRE_B fb1_{k} fbb1_{k} vdd 0 precharge")
        a(f"Xfm_{k} SEL0 SEL0B SEL1 SEL1B fb0_{k} fbb0_{k} fb1_{k} fbb1_{k} fbm_{k} fbbm_{k} vdd 0 column_mux")
        a(f"Xfs_{k} SAE fbm_{k} fbbm_{k} DOUT[{k}] fdoutb_{k} vdd 0 sense_amp")
        a(f"Xfw_{k} WE DL[{k}] fbm_{k} fbbm_{k} vdd 0 write_driver")
    a("")
    a("* monitors (VCVS, no load) for nets the .meas lines cannot index directly")
    a("Eq0 q0m 0 Q[0] 0 1")
    a(f"Ewl wl45m 0 WL[{ACCESS_ROW}] 0 1")
    a(f"Ecq cq 0 xs[0].xa0.q[{ACCESS_ROW}] 0 1")
    a(f"Ecqb cqb 0 xs[0].xa0.qb[{ACCESS_ROW}] 0 1")
    a("* every cell starts holding 0 (rail-independent levels, as sim/bitcell): no metastable start for the")
    a("* operating point. The selected cell is one of them; the first write puts a 1 into it.")
    for pair in ("xa0", "xa1"):
        for r in range(128):
            a(f".ic v(xs[0].{pair}.q[{r}])=0.3 v(xs[0].{pair}.qb[{r}])=0.9")
    for k in range(N_DUMMY_WL_CELLS):
        a(f".ic v(dq{k})=0.3 v(dqb{k})=0.9")
    return "\n".join(L) + "\n"


def cmd_negctl_bench(bench: str, dst: str, replace: dict[str, str]) -> None:
    here = Path(bench).resolve().parent
    dst_dir = Path(dst).resolve().parent
    out = []
    for line in Path(bench).read_text().splitlines():
        mi = re.match(r"\.include\s+(\S+)", line)
        if mi:
            name = Path(mi.group(1)).name
            target = replace.get(name) or str((here / mi.group(1)).resolve())
            line = f".include {target if target.startswith('./') else os.path.relpath(target, dst_dir)}"
        out.append(line)
    Path(dst).write_text("\n".join(out) + "\n")


def weaken(text: str, what: str) -> str:
    if what == "snm":
        text = re.sub(r"(?m)^(XMN[01] .*?w=)0\.30u", r"\g<1>0.15u", text)
        text = re.sub(r"(?m)^(XMN[23] .*?w=)0\.30u", r"\g<1>0.60u", text)
    else:
        text = re.sub(r"(?m)^(XMN[AB][01] .*?w=)3\.0u", r"\g<1>0.15u", text)
    return text


# --- verdicts -----------------------------------------------------------------------------

def _meas_dict(corner: dict) -> dict:
    return {x["name"]: x["value"] for x in corner.get("measurements", [])}


def _err(corner: dict) -> str:
    return "; ".join(d["message"] for d in corner.get("diagnostics", []))[:300] or "missing or non-numeric measurement"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")


def cmd_snm(report: str, curves_dir: str, label: str) -> dict:
    rep = bitcell_post.load_report(report)
    cdir = Path(curves_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    out = {"label": label, "kind": "simulated", "corners": []}
    for c in rep["corners"]:
        cid = c["corner_id"]
        entry = {"corner_id": cid, "klt_status": c["status"]}
        wave = (c.get("artifacts") or {}).get("waveform")
        if c["status"] == "error" or not wave:
            entry.update(error=_err(c), pass_=False)
            entry["pass"] = entry.pop("pass_")
            out["corners"].append(entry)
            continue
        cols = bitcell_post._columns(wave)
        tag = cid.replace("/", "_")
        try:
            qa, qba, qbb, qb = cols["v(xa.q0)"], cols["v(xa.qb0)"], cols["v(xb.qb0)"], cols["v(xb.q0)"]
        except KeyError as e:
            entry.update(error=f"waveform has no {e}", **{"pass": False})
            out["corners"].append(entry)
            continue
        bitcell_post._write_csv(cdir / f"{tag}.read.curve1.csv", qa, qba)
        bitcell_post._write_csv(cdir / f"{tag}.read.curve2.csv", qbb, qb)
        sq, vgap = bitcell_post.signed_snm(sorted(zip(qa, qba)), sorted(zip(qbb, qb)))
        entry["read_snm_v"] = sq
        entry["read_snm_vgap_v"] = vgap
        entry["pass"] = _num(sq) and sq > 0
        out["corners"].append(entry)
    return _finish(out)


def verdict_write(m: dict) -> dict:
    """Per-corner write result from a {measurement: value} dict; margin_v None when it cannot be formed."""
    flips = None
    try:
        flips = [m[f"d_end_{k}"] < 0 and m[f"d_fin_{k}"] < 0 for k in range(N_LEVELS)]
    except (KeyError, TypeError):
        pass
    row: dict = {}
    if flips is None:
        return {"error": "missing trip-cell measurements", "pass": False, "cases": {}}
    top = max((k for k, f in enumerate(flips) if f), default=None)
    trip = None if top is None else round(top * BL_STEP_V, 6)
    row["trip_flips"] = "".join("1" if f else "0" for f in flips)
    row["trip_level_v"] = trip
    row["trip_saturated"] = top == N_LEVELS - 1
    cases = {}
    for c, written in (("c", 0), ("d", 1)):
        w = -1 if written == 0 else 1          # sign of Q-QB once the written value has taken
        g = lambda k: m.get(f"{k}_{c}")
        cs: dict = {"written": written}
        try:
            tf = g("tf")
            cs.update(q_minus_qb_at_pulse_end_v=g("fl"), q_minus_qb_final_v=g("ff"),
                      driver_bit_line_low_v=g("ldrv"),
                      flip_time_ns=None if tf is None else round(tf * 1e9 - T_WL_RISE_NS, 4),
                      half_selected_cell_after_v=g("hs"))
            cs["flipped_within_pulse"] = w * cs["q_minus_qb_at_pulse_end_v"] > 0.5 and cs["flip_time_ns"] is not None \
                and cs["flip_time_ns"] < PULSE_NS
            cs["value_holds"] = w * cs["q_minus_qb_final_v"] > 0.5
            cs["half_selected_retained"] = (1 if written == 1 else -1) * cs["half_selected_cell_after_v"] > 0.5
            cs["margin_v"] = None if trip is None else round(trip - cs["driver_bit_line_low_v"], 6)
            cs["pass"] = bool(cs["flipped_within_pulse"] and cs["value_holds"] and cs["half_selected_retained"]
                              and cs["margin_v"] is not None and cs["margin_v"] > 0)
        except (KeyError, TypeError):
            cs = {"written": written, "error": "missing or non-numeric measurement", "pass": False}
        cases[c] = cs
    row["cases"] = cases
    row["write_margin_v"] = min((cs["margin_v"] for cs in cases.values() if cs.get("margin_v") is not None), default=None) \
        if all("margin_v" in cs for cs in cases.values()) else None
    if trip is None:
        row["note"] = "no trip cell flipped even with BL at 0 V: margin not positive"
    row["pass"] = all(cs["pass"] for cs in cases.values())
    return row


def cmd_write(report: str, label: str) -> dict:
    rep = bitcell_post.load_report(report)
    out = {"label": label, "kind": "simulated", "bl_step_v": BL_STEP_V, "pulse_ns": PULSE_NS,
           "margin_definition": "write_margin_v = L_trip - L_drv: L_trip = highest constant bit-line low level (25 mV grid) "
                                "at which a stand-alone cell flips within the pulse; L_drv = bit-line low level the real "
                                "write driver holds in situ at the end of the pulse; worst of write-0 and write-1",
           "corners": []}
    for c in rep["corners"]:
        entry = {"corner_id": c["corner_id"], "klt_status": c["status"]}
        m = _meas_dict(c)
        if not m:
            entry.update(error=_err(c), **{"pass": False})
        else:
            entry.update(verdict_write(m))
        out["corners"].append(entry)
    return _finish(out)


def verdict_access(m: dict) -> dict:
    row: dict = {}
    try:
        vdd = m["vdd_check"]
        for cyc, edge_name in (("read1", "tq_read1b"), ("read0", "tq_read0")):
            t, tc = m[edge_name], m["tclk_read1b" if cyc == "read1" else "tclk_read0"]
            row[f"{cyc}_access_ns"] = round((t - tc) * 1e9, 4) if _num(t) and _num(tc) else None
        row["q_final_read1_first_v"], row["q_final_read0_v"], row["q_final_read1_v"] = \
            m["qend_read1"], m["qend_read0"], m["qend_read1b"]
        for cyc in ("write1", "write0"):
            t, tw, tc = m[f"tflip_{cyc}"], m[f"twl_rise_{cyc}"], m[f"tclk_{cyc}"]
            row[f"{cyc}_flip_after_clk_ns"] = round((t - tc) * 1e9, 4) if _num(t) and _num(tc) else None
            row[f"{cyc}_flip_after_wl_ns"] = round((t - tw) * 1e9, 4) if _num(t) and _num(tw) else None
        row["cell_after_write1_v"], row["cell_after_write0_v"] = m["cell_after_write1"], m["cell_after_write0"]
        row["checks"] = {
            "read1_valid": row["read1_access_ns"] is not None and row["q_final_read1_v"] > 0.9 * vdd
                           and row["q_final_read1_first_v"] > 0.9 * vdd,
            "read0_valid": row["read0_access_ns"] is not None and row["q_final_read0_v"] < 0.1 * vdd,
            "write1_completed": row["write1_flip_after_clk_ns"] is not None and row["cell_after_write1_v"] > 0.9 * vdd,
            "write0_completed": row["write0_flip_after_clk_ns"] is not None and row["cell_after_write0_v"] < -0.9 * vdd,
        }
    except (KeyError, TypeError):
        return {"error": "missing or non-numeric measurement", "checks": {}, "pass": False}
    row["pass"] = all(row["checks"].values())
    return row


def cmd_access(report: str, label: str) -> dict:
    rep = bitcell_post.load_report(report)
    out = {"label": label, "kind": "simulated",
           "definition": "access = CLK 50 % rise to Q[0] crossing 90 % (read of 1) or 10 % (read of 0) of VDD; "
                         "write completion = CLK 50 % rise to the cell's Q = QB crossing, and the cell beyond 90 % of VDD "
                         "from the written rail afterwards",
           "corners": []}
    for c in rep["corners"]:
        entry = {"corner_id": c["corner_id"], "klt_status": c["status"]}
        m = _meas_dict(c)
        if not m:
            entry.update(error=_err(c), **{"pass": False})
        else:
            entry.update(verdict_access(m))
        out["corners"].append(entry)
    return _finish(out)


def _finish(out: dict) -> dict:
    cs = out["corners"]
    out["corner_count"] = len(cs)
    out["failing_corners"] = sorted(c["corner_id"] for c in cs if not c.get("pass"))
    out["all_pass"] = bool(cs) and not out["failing_corners"]
    out["any_fail"] = not out["all_pass"]
    return out


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr)
        return 2
    if a[0] == "request" and len(a) >= 3:
        opts = a[3:]
        net = opts[opts.index("--netlist") + 1] if "--netlist" in opts else None
        Path(a[2]).write_text(json.dumps(make_request(a[1], "--typical" in opts, net), indent=2) + "\n")
    elif a[0] == "gen-access" and len(a) >= 3:
        text = gen_access(a[1])
        if "--check" in a[3:]:
            if Path(a[2]).read_text() != text:
                print(f"array_post.py: {a[2]} is stale against {a[1]} (regenerate: array_post.py gen-access)", file=sys.stderr)
                return 1
        else:
            Path(a[2]).write_text(text)
    elif a[0] == "negctl-bench" and len(a) >= 3:
        rep, i = {}, 3
        while i < len(a):
            if a[i] == "--replace":
                k, v = a[i + 1].split("=", 1)
                rep[k] = v
            i += 2
        cmd_negctl_bench(a[1], a[2], rep)
    elif a[0] == "weaken" and len(a) == 4:
        text = weaken(Path(a[1]).read_text(), a[3])
        if text == Path(a[1]).read_text():
            print("array_post.py: weaken matched nothing", file=sys.stderr)
            return 3
        Path(a[2]).write_text(text)
    elif a[0] == "snm" and len(a) == 4:
        print(json.dumps(cmd_snm(a[1], a[2], a[3]), indent=2))
    elif a[0] == "write" and len(a) == 3:
        print(json.dumps(cmd_write(a[1], a[2]), indent=2))
    elif a[0] == "access" and len(a) == 3:
        print(json.dumps(cmd_access(a[1], a[2]), indent=2))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
