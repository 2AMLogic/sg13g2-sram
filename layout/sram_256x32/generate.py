#!/usr/bin/env python3
"""Generate the SG13G2 SRAM macro layout (GDS) from the committed netlists.

The 256 x 32 macro is organised mux-2 (``design/macro/README.md``): 128 rows x
64 physical columns, 32 ``bit_slice`` of 2 bit-line pairs each. Top cell
``macro``. Run from the repo root::

    uv run --with klayout python3 layout/sram_256x32/generate.py

Output (byte-stable; GDS timestamps are disabled): ``layout/sram_256x32/macro.gds``
and ``layout/sram_256x32/macro.socket.json`` (the socket descriptor that
``klt lef-abstract`` consumes).

What is drawn
-------------
* **Array**: the ``bitcell`` of ``layout/bitcell/generate.py`` (imported, so the
  geometry has one source), tiled 128 x 64 with mirror abutment (odd rows
  mirrored in Y, odd columns in X). ``bl_pair`` is one column of 128 cells;
  ``bit_slice`` is two ``bl_pair`` (left normal, right X-mirrored) over the
  column path. Bit lines are continuous Metal1 stripes and wordlines
  continuous GatPoly rows across the whole array; no edge or corner dummies are
  drawn (ties are in-cell, ``layout/README.md``).
* **Periphery devices**: every other subcircuit in ``design/macro/macro.spice``
  (precharge, column mux, sense amp, write driver, gates, latches, predecoders,
  wordline drivers, control) is built as a cell of that name whose leaf
  devices are real transistors (Activ, GatPoly, Cont, Metal1, NWell, pSD) of
  the netlist's W and L, with Metal1 source/drain bars and a gate pad, each
  labelled with its net name. Devices are shelf-packed; the column-path cells
  are packed to fit the 2-column slice pitch directly under their bit lines.
* **Macro pins**: Metal2 squares on the macro boundary, each labelled on
  Metal2 text (10/25), named as in ``.subckt macro``.

What is NOT drawn (disclosed, not hidden)
-----------------------------------------
No signal routing inside the periphery and none to the pins (#95). The ``VDD``/``VSS``
pin squares are not connected to the rails. The array interface (wordlines, bit lines) is
routed; the macro is placed, tapped and supplied, not fully signal-connected. LVS (#30) and
power delivery checks (#31) are the checks that must be run once routing exists.

Supply rails (issues #92, #102)
-------------------------------
The decoder-to-array gap holds the wordline Metal2 lanes and Metal3 tracks, so no rail uses
Metal1-Metal3 or Via1-Via3 there; only Metal4 crosses it.

* **Array**: every row seam carries a Metal1 pad on the VDD/VSS risers of each column (odd seams
  VDD, even seams VSS, as the mirror abutment merges the risers there), a Via1, and a Metal2
  strap across the array width, continued right of the array to the trunk (Via2, Metal3 pad,
  Via3, Metal4 pad, Via4). Seam 0 sits on the bit-line stacks, so it is a pad per column and a
  Metal4 strap.
* **Trunks**: two Metal5 stripes right of the array (VSS inner, VDD outer).
* **Periphery**: each device's tie Metal1 pad carries a Via1 and a Metal2 pad. A Metal2 stub,
  clear of the signal Metal2/Metal3, runs from it to a Via2/Metal3 pad/Via3 on the nearest Metal4
  lane of its net inside the same floorplan region (lanes every ``RAIL_LANE_PITCH``, VDD/VSS
  interleaved); lanes reach the trunk through a Via4.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from dataclasses import dataclass, field

import klayout.db as kdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NETLIST = os.path.join(ROOT, "design", "macro", "macro.spice")
GDS_PATH = os.path.join(HERE, "macro.gds")
SOCKET_PATH = os.path.join(HERE, "macro.socket.json")
TOP = "macro"

_spec = importlib.util.spec_from_file_location(
    "sg13g2_bitcell_generate", os.path.join(ROOT, "layout", "bitcell", "generate.py")
)
bc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = bc
_spec.loader.exec_module(bc)

DBU = 0.001
GRID = 5  # manufacturing grid in dbu (0.005 um)

L_METAL2 = (10, 0)
L_METAL2_LBL = (10, 25)
L_VIA1 = (19, 0)
L_VIA2 = (29, 0)
L_METAL3 = (30, 0)
LAYER_NAMES = dict(bc._LAYER_NAMES)
LAYER_NAMES[L_VIA1] = "Via1"
LAYER_NAMES[L_VIA2] = "Via2"
LAYER_NAMES[L_METAL3] = "Metal3"
LAYER_NAMES[L_METAL2] = "Metal2"
LAYER_NAMES[L_METAL2_LBL] = "Metal2_text"

L_VIA3 = (49, 0)
L_METAL4 = (50, 0)
L_VIA4 = (66, 0)
L_METAL5 = (67, 0)
LAYER_NAMES[L_VIA3] = "Via3"
LAYER_NAMES[L_METAL4] = "Metal4"
LAYER_NAMES[L_VIA4] = "Via4"
LAYER_NAMES[L_METAL5] = "Metal5"
LAYER_NAMES[(67, 25)] = "Metal5_text"

VIA = 0.19  # V1.a / V2.a / V3.a: fixed 0.19 square
VIA_ENC = 0.05  # metal enclosure of a via, kept at 0.05 on all sides (deck minimum is smaller)
VIA_PAD = VIA + 2 * VIA_ENC  # 0.29
LANE_W = 0.40  # Metal4 lane
RAIL_LANE_PITCH = 4.0  # um between lanes of one net inside a region (VDD and VSS interleave at pitch / 2)
TRUNK_W = 0.80  # Metal5 trunk
TRUNK_OFFSET = 1.5  # um from the array right edge to the inner (VSS) trunk
TRUNK_PITCH = 1.4  # um between the VSS and VDD trunks
ROWS = 128
COLS = 64
SLICES = 32
PACK_GAP = 0.65  # um between packed cells (> NW.b 0.62; wells are inside the bbox)
BLOCK_GAP = 3.0  # um between floorplan blocks
SLICE_MARGIN = 0.4  # um kept clear on each side of a slice's column path
PIN = 0.5  # um, macro pin square on Metal2
PIN_PITCH = 1.0  # um between left-edge pins

# ---- inter-block routing (rule values from `klt deck rules --deck sg13g2`) ----
V1 = 0.19  # V1.a: Via1 is a fixed 0.19 square
V1_SPACE = 0.22  # V1.b
M1_ENC_V1 = 0.01  # V1.c: Metal1 enclosure of Via1
M1_V1_PAD = V1 + 2 * M1_ENC_V1  # 0.21: Metal1 landing pad for a Via1 on a 0.20 wire
M2_W = 0.20  # M2.a
M2_SPACE = 0.21  # M2.b
V2 = 0.19  # V2.a
V2_SPACE = 0.22  # V2.b
M3_W = 0.20  # M3.a
M3_SPACE = 0.21  # M3.b
# Metal2/3 wires are 0.20 wide, so a Via (0.19) is enclosed by 0.005 per side (V2.c 0.005)
M2_ENC_V2 = 0.005
TRACK_PITCH = M3_W + M3_SPACE  # 0.41: private Metal3 track pitch (M2: same widths)
LANE_PITCH = 0.42  # Metal2 lane pitch in the wordline gap (>= M2_W + M2_SPACE)
TRACK_OFFSET = 0.5  # first private track above its decoder terminal row
LANE_MARGIN = 1.0  # um clear of the decoder edge / the array edge
WL_PAD_X = -0.25  # x of the wordline contact column, left of the array edge
BL_VIA_Y = -0.15  # y of the Via1 stack under each bit-line stripe
WL_FANOUT_GAP = round(2 * LANE_MARGIN + (ROWS - 1) * LANE_PITCH, 3)  # decoder-to-array gap
STUB_W = M2_W  # Metal2 stub from a tie to its lane


def dbu(v: float) -> int:
    return int(round(v / DBU))


def snap(v: float) -> float:
    """Round to the 0.005 um manufacturing grid."""
    return round(v / (GRID * DBU)) * (GRID * DBU)


# ---------------------------------------------------------------------------
# Netlist parsing
# ---------------------------------------------------------------------------
@dataclass
class Inst:
    name: str
    nets: list[str]
    ref: str
    params: dict[str, str]


@dataclass
class Subckt:
    name: str
    ports: list[str]
    insts: list[Inst] = field(default_factory=list)


def parse_netlist(path: str) -> dict[str, Subckt]:
    lines: list[str] = []
    for raw in open(path):
        raw = raw.rstrip("\n")
        if not raw.strip() or raw.lstrip().startswith("*"):
            continue
        if raw.startswith("+") and lines:
            lines[-1] += " " + raw[1:].strip()
        else:
            lines.append(raw.strip())
    subckts: dict[str, Subckt] = {}
    cur: Subckt | None = None
    for ln in lines:
        t = ln.split()
        head = t[0].lower()
        if head == ".subckt":
            cur = Subckt(t[1], t[2:])
            subckts[cur.name] = cur
        elif head == ".ends":
            cur = None
        elif cur is not None and t[0][0] in "Xx":
            params = dict(x.split("=", 1) for x in t[1:] if "=" in x)
            pos = [x for x in t[1:] if "=" not in x]
            cur.insts.append(Inst(t[0], pos[:-1], pos[-1], params))
    return subckts


def micron(s: str) -> float:
    m = re.fullmatch(r"([0-9.]+)u", s)
    if not m:
        raise ValueError(f"unsupported dimension {s!r}")
    return float(m.group(1))


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
class Gen:
    def __init__(self) -> None:
        self.layout = kdb.Layout()
        self.layout.dbu = DBU
        for lp, name in LAYER_NAMES.items():
            self.layout.set_info(self.layout.layer(*lp), kdb.LayerInfo(lp[0], lp[1], name))
        self.devs: dict[tuple[str, float, float], tuple[kdb.Cell, dict]] = {}
        self.cells: dict[str, kdb.Cell] = {}
        self.nl = parse_netlist(NETLIST)
        # placement record: subckt -> {instance name: (dx, dy in dbu)}; devices
        # also keep their D/G/S terminal points (um, in the parent's frame)
        self.place_of: dict[str, dict[str, tuple[int, int]]] = {}
        self.dev_pts: dict[str, dict[str, dict[str, tuple[float, float]]]] = {}

    def li(self, lp: tuple[int, int]) -> int:
        return self.layout.layer(*lp)

    def box(self, cell: kdb.Cell, lp, x0: float, y0: float, x1: float, y1: float) -> None:
        cell.shapes(self.li(lp)).insert(kdb.Box(dbu(x0), dbu(y0), dbu(x1), dbu(y1)))

    def text(self, cell: kdb.Cell, lp, s: str, x: float, y: float) -> None:
        cell.shapes(self.li(lp)).insert(kdb.Text(s, kdb.Trans(dbu(x), dbu(y))))

    # ---- one transistor ---------------------------------------------------
    def mos(self, kind: str, w: float, l: float) -> tuple[kdb.Cell, dict]:
        key = (kind, w, l)
        if key in self.devs:
            return self.devs[key]
        pad, gap = bc.PAD, bc.GAP
        assert w >= pad - 1e-9, f"W={w} below the contact-pad height {pad}"
        h = w
        name = f"sg13_lv_{kind}_w{w:g}_l{l:g}".replace(".", "p")
        c = self.layout.create_cell(name)
        x_s = (0.0, pad)
        x_g = (pad + gap, pad + gap + l)
        x_d = (x_g[1] + gap, x_g[1] + gap + pad)
        xw = x_d[1]
        self.box(c, bc.L_ACTIV, 0.0, 0.0, xw, h)
        # contacts: as many as fit at Cnt.b 0.18 spacing, centred, on grid
        n = int((h - 2 * bc.CO_ENC_ACT + 0.18) // (bc.CO + 0.18))
        while True:
            total = n * bc.CO + (n - 1) * 0.18
            m = math.floor(((h - total) / 2) / 0.005 + 1e-9) * 0.005
            if m >= bc.CO_ENC_ACT - 1e-9 and (h - total - m) >= bc.CO_ENC_ACT - 1e-9:
                break
            n -= 1
        ys = [m + i * (bc.CO + 0.18) for i in range(n)]
        for xs in (x_s, x_d):
            cx = 0.5 * (xs[0] + xs[1])
            for y in ys:
                self.box(c, bc.L_CONT, cx - bc.CO / 2, y, cx + bc.CO / 2, y + bc.CO)
            self.box(c, bc.L_METAL1, cx - bc.M1_W / 2, ys[0] - bc.CO_ENC_M1, cx + bc.M1_W / 2, ys[-1] + bc.CO + bc.CO_ENC_M1)
        # gate: poly over the channel with a landing pad above
        gx = 0.5 * (x_g[0] + x_g[1])
        y_pad0 = h + bc.GATE_ENDCAP
        self.box(c, bc.L_GATPOLY, x_g[0], -bc.GATE_ENDCAP, x_g[1], y_pad0 + 0.02)
        self.box(c, bc.L_GATPOLY, gx - 0.15, y_pad0, gx + 0.15, y_pad0 + bc.POLY_PAD)
        gcy = y_pad0 + bc.POLY_PAD / 2
        self.box(c, bc.L_CONT, gx - bc.CO / 2, gcy - bc.CO / 2, gx + bc.CO / 2, gcy + bc.CO / 2)
        self.box(c, bc.L_METAL1, gx - bc.CO / 2 - bc.CO_ENC_M1, gcy - bc.CO / 2 - bc.CO_ENC_M1, gx + bc.CO / 2 + bc.CO_ENC_M1, gcy + bc.CO / 2 + bc.CO_ENC_M1)
        # body tie: one PAD-square Activ with one Cont and a Metal1 pad, to the right of
        # the drain. pSD of the device (PMOS) or of the tie (NMOS p-tap) is kept
        # PSD_TO_NACT from the other polarity's Activ (pSD.e class), which sets the offset.
        tx0 = xw + bc.PSD_ENC_ACT + bc.PSD_TO_NACT
        tx0 = math.ceil(tx0 / 0.005 - 1e-9) * 0.005
        tx1 = tx0 + bc.PAD
        ty0 = (h - bc.PAD) / 2 if h > bc.PAD else 0.0
        ty0 = math.floor(ty0 / 0.005 + 1e-9) * 0.005
        ty1 = ty0 + bc.PAD
        self.box(c, bc.L_ACTIV, tx0, ty0, tx1, ty1)
        tcx, tcy = 0.5 * (tx0 + tx1), 0.5 * (ty0 + ty1)
        self.box(c, bc.L_CONT, tcx - bc.CO / 2, tcy - bc.CO / 2, tcx + bc.CO / 2, tcy + bc.CO / 2)
        # Metal1 pad grown to hold a Via1 (VIA_PAD square), then Via1 and a Metal2 pad (issue #92)
        hp = VIA_PAD / 2
        self.box(c, bc.L_METAL1, tcx - hp, tcy - hp, tcx + hp, tcy + hp)
        self.box(c, L_VIA1, tcx - VIA / 2, tcy - VIA / 2, tcx + VIA / 2, tcy + VIA / 2)
        self.box(c, L_METAL2, tcx - hp, tcy - hp, tcx + hp, tcy + hp)
        if kind == "pmos":
            self.box(c, bc.L_PSD, -bc.PSD_ENC_ACT, -bc.PSD_ENC_ACT, xw + bc.PSD_ENC_ACT, h + bc.PSD_ENC_ACT)
            # n-well tie (n+ Activ, no pSD) inside the device's well
            self.box(c, bc.L_NWELL, -bc.NW_ENC_PACT, -bc.NW_ENC_PACT, tx1 + bc.NW_ENC_NACT, h + bc.NW_ENC_PACT)
        else:
            # p-substrate tie: pSD over the tie
            self.box(c, bc.L_PSD, tx0 - bc.PSD_ENC_ACT, ty0 - bc.PSD_ENC_ACT, tx1 + bc.PSD_ENC_ACT, ty1 + bc.PSD_ENC_ACT)
        pts = {
            "D": (0.5 * (x_s[0] + x_s[1]), h / 2),
            "G": (gx, gcy),
            "S": (0.5 * (x_d[0] + x_d[1]), h / 2),
            "B": (tcx, tcy),
        }
        self.devs[key] = (c, pts)
        return c, pts

    # ---- packing ----------------------------------------------------------
    def pack(self, items: list[kdb.Cell], max_w: float) -> tuple[list[tuple[kdb.Cell, int, int]], int, int]:
        """Shelf-pack cells by bbox. Returns [(cell, dx, dy)] placing each
        bbox's lower-left at the shelf position, plus the packed width/height."""
        gap, mw = dbu(PACK_GAP), dbu(max_w)
        out: list[tuple[kdb.Cell, int, int]] = []
        x = y = row_h = used = 0
        for c in items:
            bb = c.bbox()
            if x > 0 and x + bb.width() > mw:
                y += row_h + gap
                x = row_h = 0
            dx, dy = x - bb.left, y - bb.bottom
            assert dx % GRID == 0 and dy % GRID == 0, (c.name, dx, dy)
            out.append((c, dx, dy))
            x += bb.width() + gap
            row_h = max(row_h, bb.height())
            used = max(used, x - gap)
        return out, used, y + row_h

    def place(self, parent: kdb.Cell, child: kdb.Cell, dx: int, dy: int, trans: kdb.Trans | None = None) -> None:
        t = trans or kdb.Trans.R0
        parent.insert(kdb.CellInstArray(child.cell_index(), kdb.Trans(t.rot, t.is_mirror(), dx, dy)))

    # ---- generic subcircuit ----------------------------------------------
    def subckt(self, name: str, max_w: float | None = None) -> kdb.Cell:
        if name in self.cells:
            return self.cells[name]
        sc = self.nl[name]
        cell = self.layout.create_cell(name)
        self.cells[name] = cell
        items: list[kdb.Cell] = []
        meta: list[tuple[Inst, kdb.Cell, dict | None]] = []
        for inst in sc.insts:
            if inst.ref in ("sg13_lv_nmos", "sg13_lv_pmos"):
                kind = inst.ref.rsplit("_", 1)[1]
                dc, pts = self.mos(kind, micron(inst.params["w"]), micron(inst.params["l"]))
                items.append(dc)
                meta.append((inst, dc, pts))
            else:
                ch = self.build(inst.ref)
                items.append(ch)
                meta.append((inst, ch, None))
        area = sum(c.bbox().width() * c.bbox().height() for c in items) * DBU * DBU
        widest = max(c.bbox().width() for c in items) * DBU
        mw = max_w if max_w is not None else max(widest, math.sqrt(area) * 1.6)
        placed, _, _ = self.pack(items, mw)
        self.place_of[name] = {}
        self.dev_pts[name] = {}
        for (inst, ch, pts), (_, dx, dy) in zip(meta, placed):
            self.place(cell, ch, dx, dy)
            self.place_of[name][inst.name] = (dx, dy)
            if pts is not None:
                self.dev_pts[name][inst.name] = {t: (p[0] + dx * DBU, p[1] + dy * DBU) for t, p in pts.items()}
                # SPICE order: d g s b (B is the body tie)
                for term, net in zip("DGSB", inst.nets[:4]):
                    px, py = pts[term]
                    self.text(cell, bc.L_METAL1_LBL, net, px + dx * DBU, py + dy * DBU)
        return cell

    def build(self, name: str) -> kdb.Cell:
        if name == "bitcell":
            return self.bitcell()
        if name == "bl_pair":
            return self.bl_pair()
        if name == "bit_slice":
            return self.bit_slice()
        if name in ("precharge", "column_mux", "sense_amp", "write_driver"):
            return self.subckt(name, max_w=2 * bc.W_CELL - 2 * SLICE_MARGIN)
        return self.subckt(name)


    # ---- routing ----------------------------------------------------------
    def terminal(self, cellname: str, net: str) -> tuple[float, float] | None:
        """Metal1 terminal point (um, in ``cellname``'s frame) of the first
        device in the subcircuit hierarchy whose D/G/S is on ``net`` (a port of
        ``cellname``), from the placement record."""
        for inst in self.nl[cellname].insts:
            off = self.place_of[cellname].get(inst.name)
            if off is None:
                continue
            if inst.name in self.dev_pts[cellname]:
                for t, n in zip("DGS", inst.nets[:3]):
                    if n == net:
                        return self.dev_pts[cellname][inst.name][t]
            else:
                sub = self.nl[inst.ref]
                for port, n in zip(sub.ports, inst.nets):
                    if n == net:
                        r = self.terminal(inst.ref, port)
                        if r is not None:
                            return (r[0] + off[0] * DBU, r[1] + off[1] * DBU)
        return None

    def rect(self, cell: kdb.Cell, lp, cx: float, cy: float, w: float, h: float) -> None:
        self.box(cell, lp, snap(cx - w / 2), snap(cy - h / 2), snap(cx + w / 2), snap(cy + h / 2))

    def via_pad(self, cell: kdb.Cell, via, x: float, y: float) -> None:
        self.rect(cell, via, x, y, V1, V1)

    def seg(self, cell: kdb.Cell, lp, w: float, x0: float, y0: float, x1: float, y1: float) -> None:
        """Manhattan wire of width w between two centre points (square ends)."""
        self.box(cell, lp, snap(min(x0, x1) - w / 2), snap(min(y0, y1) - w / 2),
                 snap(max(x0, x1) + w / 2), snap(max(y0, y1) + w / 2))

    def m1_via1(self, cell: kdb.Cell, x: float, y: float) -> None:
        """Via1 on a Metal1 landing pad, with a Metal2 pad over it."""
        self.rect(cell, bc.L_METAL1, x, y, M1_V1_PAD, M1_V1_PAD)
        self.via_pad(cell, L_VIA1, x, y)
        self.rect(cell, L_METAL2, x, y, M2_W, M2_W)

    def route_bitlines(self, cell: kdb.Cell) -> None:
        """Bit-line stripe bottoms to one BL/BLB terminal of the precharge and of
        the column mux. Per net: Via1 stack under the stripe, a Metal3 lane at the
        stripe's own x, and a Metal2 jog from each terminal to the lane (the jog
        y moves down in 0.1 um steps until it clears the other nets' Metal2)."""
        self.bl_terms: dict[str, list[tuple[float, float]]] = {}
        sl = {}  # net -> (stripe x, [terminal (x, y)])
        for inst in self.nl["bit_slice"].insts:
            if inst.ref != "bl_pair":
                continue
            col = int(inst.name[-1])
            fx = (lambda x, c=col: (c + 1) * bc.W_CELL - x if c % 2 else c * bc.W_CELL + x)
            sl[f"BL{col}"] = (snap(fx(bc.xc("pad_bl"))), [])
            sl[f"BLB{col}"] = (snap(fx(bc.xc("pad_blb"))), [])
        for inst in self.nl["bit_slice"].insts:
            off = self.place_of["bit_slice"].get(inst.name)
            if off is None or inst.ref not in ("precharge", "column_mux"):
                continue
            sub = self.nl[inst.ref]
            for port, n in zip(sub.ports, inst.nets):
                if n in sl:
                    t = self.terminal(inst.ref, port)
                    assert t is not None, (inst.name, port)
                    sl[n][1].append((snap(t[0] + off[0] * DBU), snap(t[1] + off[1] * DBU)))
        # every net's Metal2 pads are obstacles for the others from the start
        def pad_region(x: float, y: float) -> kdb.Region:
            return kdb.Region(kdb.Box(dbu(x - M2_W / 2), dbu(y - M2_W / 2), dbu(x + M2_W / 2), dbu(y + M2_W / 2)))

        # the periphery tie pads (Metal2, issue #92) are obstacles for every net
        supply = kdb.Region()
        for t in self.ties(cell):
            h = dbu(VIA_PAD / 2)
            supply.insert(kdb.Box(dbu(t["x"]) - h, dbu(t["y"]) - h, dbu(t["x"]) + h, dbu(t["y"]) + h))
        placed: dict[str, kdb.Region] = {}
        for net, (xs, terms) in sl.items():
            placed[net] = pad_region(xs, BL_VIA_Y)
            for tx, ty in terms:
                placed[net] += pad_region(tx, ty)
        for net, (xs, terms) in sl.items():
            self.m1_via1_stripe(cell, xs)
            mine = kdb.Region()
            lane_bot = BL_VIA_Y
            for tx, ty in sorted(terms, key=lambda t: -t[1]):
                self.m1_via1(cell, tx, ty)
                for k in range(0, 40):
                    yh = snap(ty - 0.1 * k)
                    cand = kdb.Region()
                    for (x0, y0, x1, y1) in ((tx, ty, tx, yh), (tx, yh, xs, yh)):
                        w = M2_W
                        cand.insert(kdb.Box(dbu(min(x0, x1) - w / 2), dbu(min(y0, y1) - w / 2),
                                            dbu(max(x0, x1) + w / 2), dbu(max(y0, y1) + w / 2)))
                    other = supply.dup()
                    for n2, rg in placed.items():
                        if n2 != net:
                            other += rg
                    if (cand.sized(dbu(M2_SPACE) - 1) & other).is_empty():
                        break
                else:
                    raise AssertionError(f"no clear Metal2 jog for {net} at {tx},{ty}")
                self.seg(cell, L_METAL2, M2_W, tx, ty, tx, yh)
                self.seg(cell, L_METAL2, M2_W, tx, yh, xs, yh)
                self.via_pad(cell, L_VIA2, xs, yh)
                mine += cand
                lane_bot = min(lane_bot, yh)
                self.bl_terms.setdefault(net, []).append((tx, ty))
            self.seg(cell, L_METAL3, M3_W, xs, BL_VIA_Y, xs, lane_bot)
            placed[net] = placed[net] + mine
        self.bl_stripe_x = {n: v[0] for n, v in sl.items()}

    def m1_via1_stripe(self, cell: kdb.Cell, xs: float) -> None:
        """Via1/Via2 stack just below the bottom of a Metal1 stripe (the stripe
        itself is not altered; the pad abuts its bottom end)."""
        pad_bot = BL_VIA_Y - V1 / 2 - M1_ENC_V1
        self.box(cell, bc.L_METAL1, snap(xs - M1_V1_PAD / 2), snap(pad_bot), snap(xs + M1_V1_PAD / 2), 0.0)
        self.via_pad(cell, L_VIA1, xs, BL_VIA_Y)
        self.rect(cell, L_METAL2, xs, BL_VIA_Y, M2_W, M2_W)
        self.via_pad(cell, L_VIA2, xs, BL_VIA_Y)

    def wl_y(self, r: int) -> float:
        """y centre of wordline r's GatPoly row (odd rows are Y-mirrored)."""
        yc = 0.5 * (bc.Y_WL[0] + bc.Y_WL[1])
        return snap(r * bc.H_CELL + yc if r % 2 == 0 else (r + 1) * bc.H_CELL - yc)

    def route_wordlines(self, top: kdb.Cell) -> None:
        """Wordline r: poly pad at the array's left edge -> Cont -> Metal1 -> Via1 ->
        Metal2/Via2 -> Metal3 (y = wl_y) -> Metal2 lane (private x) -> Metal3 track
        (private y above the decoder terminal) -> Via1 on the wl_driver output."""
        rd = self.place_of[TOP]["row_decoder"]
        x_e = rd[0] * DBU + self.cells["row_decoder"].bbox().right * DBU
        self.wl_terms: dict[int, tuple[float, float]] = {}
        for r in range(ROWS):
            t = self.terminal("row_decoder", f"WL[{r}]")
            assert t is not None, r
            self.wl_terms[r] = (snap(t[0] + rd[0] * DBU), snap(t[1] + rd[1] * DBU))
        # private Metal3 track per net, stacked above its terminal row
        rows: dict[float, list[int]] = {}
        for r, (_, ty) in self.wl_terms.items():
            rows.setdefault(round(ty, 2), []).append(r)
        track: dict[int, float] = {}
        ys_sorted = sorted(rows)
        for i, ty in enumerate(ys_sorted):
            nets = sorted(rows[ty], key=lambda r: -self.wl_terms[r][0])
            for k, r in enumerate(nets):
                track[r] = snap(self.wl_terms[r][1] + TRACK_OFFSET + k * TRACK_PITCH)
            if i + 1 < len(ys_sorted):  # the next row's Metal2 pad must stay clear
                assert track[nets[-1]] + M2_W / 2 + M2_SPACE <= ys_sorted[i + 1] - M2_W / 2, ty
        # lane order: a before b when a's decoder track is within Metal3 spacing of
        # b's array-side run (so a's run ends before b's starts)
        pitch = M3_W + M3_SPACE
        before = {r: set() for r in range(ROWS)}
        for a in range(ROWS):
            for b in range(ROWS):
                if a != b and abs(track[a] - self.wl_y(b)) < pitch - 1e-6:
                    before[b].add(a)
        order: list[int] = []
        done: set[int] = set()
        while len(order) < ROWS:
            ready = [r for r in range(ROWS) if r not in done and before[r] <= done]
            assert ready, "cyclic wordline lane constraints"
            order.append(ready[0])
            done.add(ready[0])
        lane = {r: snap(x_e + LANE_MARGIN + i * LANE_PITCH) for i, r in enumerate(order)}
        assert max(lane.values()) + M2_W / 2 + M2_SPACE <= WL_PAD_X - M2_W / 2, "lanes overrun the array pad column"
        # periphery tie pads (Metal2, issue #92) the terminal stub must keep M2.b clear of
        tie_pads = [kdb.DBox(t["x"] - VIA_PAD / 2, t["y"] - VIA_PAD / 2, t["x"] + VIA_PAD / 2, t["y"] + VIA_PAD / 2)
                    for t in self.ties(top)]
        for r in range(ROWS):
            tx, ty = self.wl_terms[r]
            ya, yt, xl = self.wl_y(r), track[r], lane[r]
            self.m1_via1(top, tx, ty)
            # stub up to the private track; if a tie pad sits beside it, jog right (toward the track) first
            for jog in [0.0] + [round(0.2 * i, 3) for i in range(2, 16)]:
                sx = snap(tx + jog)
                parts = [kdb.DBox(sx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, yt + M2_W / 2)]
                if jog:
                    parts.append(kdb.DBox(tx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, ty + M2_W / 2))
                grown = [pt.enlarged(M2_SPACE, M2_SPACE) for pt in parts]
                if not any(gr.overlaps(tp) for gr in grown for tp in tie_pads):
                    break
            else:
                raise AssertionError(f"no tie-clear Metal2 stub for wordline {r}")
            if jog:
                self.seg(top, L_METAL2, M2_W, tx, ty, sx, ty)
            self.seg(top, L_METAL2, M2_W, sx, ty, sx, yt)
            self.via_pad(top, L_VIA2, sx, yt)
            self.seg(top, L_METAL3, M3_W, sx, yt, xl, yt)
            self.via_pad(top, L_VIA2, xl, yt)
            self.seg(top, L_METAL2, M2_W, xl, yt, xl, ya)  # private lane to the wordline's y
            self.via_pad(top, L_VIA2, xl, ya)
            self.seg(top, L_METAL3, M3_W, xl, ya, WL_PAD_X, ya)
            self.via_pad(top, L_VIA2, WL_PAD_X, ya)
            self.m1_via1(top, WL_PAD_X, ya)
            # Cont on a GatPoly landing pad, joined to the row's left end
            self.rect(top, bc.L_GATPOLY, WL_PAD_X, ya, bc.POLY_PAD, bc.POLY_PAD)
            self.box(top, bc.L_GATPOLY, snap(WL_PAD_X + bc.POLY_PAD / 2), snap(ya - 0.08), 0.0, snap(ya + 0.08))
            self.rect(top, bc.L_CONT, WL_PAD_X, ya, bc.CO, bc.CO)
            self.rect(top, bc.L_METAL1, WL_PAD_X, ya, bc.CO + 2 * bc.CO_ENC_M1, bc.CO + 2 * bc.CO_ENC_M1)
        self.wl_lane = lane
        self.wl_track = track

    # ---- array ------------------------------------------------------------
    def bitcell(self) -> kdb.Cell:
        if "bitcell" not in self.cells:
            c = self.layout.create_cell("bitcell")
            bc.draw(self.layout, c, with_labels=False)
            self.cells["bitcell"] = c
        return self.cells["bitcell"]

    def bl_pair(self) -> kdb.Cell:
        """One bit-line pair: 128 bitcells, odd rows mirrored in Y."""
        if "bl_pair" in self.cells:
            return self.cells["bl_pair"]
        cell = self.layout.create_cell("bl_pair")
        self.cells["bl_pair"] = cell
        leaf = self.bitcell()
        w, h = dbu(bc.W_CELL), dbu(bc.H_CELL)
        for r in range(ROWS):
            if r % 2:
                self.place(cell, leaf, 0, (r + 1) * h, kdb.Trans.M0)
            else:
                self.place(cell, leaf, 0, r * h)
            # wordline label at the left end of the poly row
            self.text(cell, bc.L_GATPOLY_LBL, f"WL[{r}]", 0.5 * (bc.X["g_wl_l"][0] + bc.X["g_wl_l"][1]), (r + 0.5) * bc.H_CELL)
        # supply taps at every row seam: mirror abutment merges the risers there (even seams VSS,
        # odd seams VDD). Metal1 pad on the riser, Via1, and a Metal2 strap across the column.
        xcp, hp = bc.xc("pad_c"), VIA_PAD / 2
        for k in range(ROWS + 1):
            ys = k * bc.H_CELL
            self.box(cell, bc.L_METAL1, xcp - hp, ys - hp, xcp + hp, ys + hp)
            self.box(cell, L_VIA1, xcp - VIA / 2, ys - VIA / 2, xcp + VIA / 2, ys + VIA / 2)
            if k == 0:
                # the bottom seam sits on the bit-line Via1/Via2 stacks below the array: a full-width
                # strap would short every bit line, so it is a pad and the rails leave on Metal4
                self.box(cell, L_METAL2, xcp - hp, ys - hp, xcp + hp, ys + hp)
            else:
                self.box(cell, L_METAL2, 0.0, ys - hp, bc.W_CELL, ys + hp)
        return cell

    def bit_slice(self) -> kdb.Cell:
        """Two bl_pairs over their column path (precharge x2, mux, SA, write driver)."""
        if "bit_slice" in self.cells:
            return self.cells["bit_slice"]
        cell = self.layout.create_cell("bit_slice")
        self.cells["bit_slice"] = cell
        w = dbu(bc.W_CELL)
        pair = self.bl_pair()
        arr_h = dbu(ROWS * bc.H_CELL)
        for inst in self.nl["bit_slice"].insts:
            if inst.ref == "bl_pair":
                col = int(inst.name[-1])
                if col % 2:
                    self.place(cell, pair, (col + 1) * w, 0, kdb.Trans.M90)
                else:
                    self.place(cell, pair, col * w, 0)
        y = -dbu(2.0)
        self.colpath_top = y
        self.place_of["bit_slice"] = {}
        for inst in self.nl["bit_slice"].insts:
            if inst.ref in ("bl_pair",) or inst.ref in ("sg13_lv_nmos", "sg13_lv_pmos"):
                continue
            ch = self.build(inst.ref)
            bb = ch.bbox()
            dx = dbu(SLICE_MARGIN) - bb.left
            dy = y - bb.top
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(cell, ch, dx, dy)
            self.place_of["bit_slice"][inst.name] = (dx, dy)
            y = y - bb.height() - dbu(PACK_GAP)
        self.colpath_bottom = y + dbu(PACK_GAP)
        assert arr_h > 0
        self.route_bitlines(cell)
        return cell

    # ---- macro ------------------------------------------------------------
    def macro(self) -> kdb.Cell:
        top = self.layout.create_cell(TOP)
        self.cells[TOP] = top
        ports = self.nl[TOP].ports
        sl_w = 2 * dbu(bc.W_CELL)
        bs = self.bit_slice()
        for inst in self.nl[TOP].insts:
            m = re.fullmatch(r"XS\[(\d+)\]", inst.name)
            if m:
                self.place(top, bs, int(m.group(1)) * sl_w, 0)
        col_bottom = bs.bbox().bottom
        arr_w = SLICES * sl_w

        # left block: address latch, control, row decoder, right-aligned to the array
        by = 0
        right = -dbu(WL_FANOUT_GAP)
        regions: list[kdb.Box] = []
        for ref in ("addr_latch", "control", "row_decoder"):
            ch = self.build(ref)
            bb = ch.bbox()
            dx = right - bb.right
            dy = by - bb.bottom
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(top, ch, dx, dy)
            regions.append(bb.moved(dx, dy))
            self.place_of.setdefault(TOP, {})[ref] = (dx, dy)
            by += bb.height() + dbu(BLOCK_GAP)

        # bottom block: data latch and output latch under the column path
        y = col_bottom - dbu(BLOCK_GAP)
        for ref in ("data_latch", "out_latch"):
            ch = self.build(ref)
            bb = ch.bbox()
            dx = 0 - bb.left
            dy = y - bb.top
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(top, ch, dx, dy)
            regions.append(bb.moved(dx, dy))
            y -= bb.height() + dbu(BLOCK_GAP)
        regions.append(kdb.Box(0, bs.bbox().bottom, arr_w, self.colpath_top))  # the 32 column paths

        # column labels (unique per column) and the supplies, at macro level
        for c in range(COLS):
            fx = (lambda x, c=c: (c + 1) * bc.W_CELL - x if c % 2 else c * bc.W_CELL + x)
            self.text(top, bc.L_METAL1_LBL, f"BL{c}", fx(bc.xc("pad_bl")), 0.5 * bc.H_CELL)
            self.text(top, bc.L_METAL1_LBL, f"BLB{c}", fx(bc.xc("pad_blb")), 0.5 * bc.H_CELL)
        self.text(top, bc.L_METAL1_LBL, "VSS", bc.xc("pad_c"), 0.5 * (bc.Y_PTIE[1] + bc.Y_N[0]))
        self.text(top, bc.L_METAL1_LBL, "VDD", bc.xc("pad_c"), 0.5 * (bc.Y_P[1] + bc.Y_NTIE[0]))

        self.route_wordlines(top)

        # pins on the content bounding box
        bb = top.bbox()
        pins = self.pins(top, bb, ports, arr_w)
        self.pin_list = pins
        before = top.bbox()
        self.rails(top, regions, arr_w)
        after = top.bbox()
        assert (after.left, after.bottom, after.top) == (before.left, before.bottom, before.top), \
            "rails may extend the macro to the right only (pins sit on the left and bottom edges)"
        top.shapes(self.li(bc.L_PRBOUNDARY)).insert(top.bbox())
        return top

    # ---- supply rails (issue #92) -------------------------------------------
    def ties(self, top: kdb.Cell) -> list[dict]:
        """Centre of every periphery tie (Metal1/Via1/Metal2 pad) under ``top``, by netlist bulk net."""
        found: list[dict] = []
        dev = {c.cell_index(): ("VDD" if "pmos" in c.name else "VSS", pts["B"]) for c, pts in self.devs.values()}
        skip = {self.cells["bitcell"].cell_index(), self.cells["bl_pair"].cell_index()}

        def walk(cell: kdb.Cell, t: kdb.Trans) -> None:
            for inst in cell.each_inst():
                ci = inst.cell_index
                if ci in skip:
                    continue
                tt = t * inst.trans
                if ci in dev:
                    net, (px, py) = dev[ci]
                    p = tt * kdb.Point(dbu(px), dbu(py))
                    found.append({"net": net, "x": round(p.x * DBU, 3), "y": round(p.y * DBU, 3)})
                else:
                    walk(self.layout.cell(ci), tt)

        walk(top, kdb.Trans())
        return found

    def signal_boxes(self, top: kdb.Cell, lp, skip: list[kdb.DBox]) -> list[kdb.DBox]:
        """Flat boxes of a routing layer already in ``top``, minus the supply pads in ``skip`` (centre match)."""
        out: list[kdb.DBox] = []
        it = top.begin_shapes_rec(self.layout.layer(*lp))
        skipc = {(round(b.center().x, 3), round(b.center().y, 3)) for b in skip}
        while not it.at_end():
            ib = it.shape().bbox().transformed(it.trans())
            b = kdb.DBox(ib.left * DBU, ib.bottom * DBU, ib.right * DBU, ib.top * DBU)
            if (round(b.center().x, 3), round(b.center().y, 3)) not in skipc:
                out.append(b)
            it.next()
        return out

    def rails(self, top: kdb.Cell, regions: list[kdb.Box], arr_w: int) -> None:
        """Supply rails. Metal4 lanes run in free tracks, Metal5 trunks sit right of the array; nothing but
        Metal4 crosses the wordline fan-out gap, whose Metal2/Metal3 lanes and tracks belong to the signals."""
        rc = self.layout.create_cell("rails")
        top.insert(kdb.CellInstArray(rc.cell_index(), kdb.Trans()))
        hp = VIA_PAD / 2
        arr_um = arr_w * DBU
        trunk_x = {"VSS": round(arr_um + TRUNK_OFFSET, 3), "VDD": round(arr_um + TRUNK_OFFSET + TRUNK_PITCH, 3)}
        self.trunk_x = trunk_x

        def via(lp_lo, lp_via, lp_hi, x: float, y: float) -> None:
            self.box(rc, lp_via, x - VIA / 2, y - VIA / 2, x + VIA / 2, y + VIA / 2)
            for lp in (lp_lo, lp_hi):
                if lp is not None:
                    self.box(rc, lp, x - hp, y - hp, x + hp, y + hp)

        # array straps: the Metal2 strap of each row seam continues right of the array to its trunk
        # (even seams VSS, odd seams VDD)
        seam_pads: dict[str, list[float]] = {"VDD": [], "VSS": []}
        for k in range(ROWS + 1):
            net = "VSS" if k % 2 == 0 else "VDD"
            y = round(k * bc.H_CELL, 3)
            tx = trunk_x[net]
            if k == 0:  # Via2/Metal3/Via3 on each column's pad, a Metal4 strap along the seam to the trunk
                xs0 = [(c + 1) * bc.W_CELL - bc.xc("pad_c") if c % 2 else c * bc.W_CELL + bc.xc("pad_c")
                       for c in range(COLS)]
                for xc0 in xs0:
                    via(None, L_VIA2, L_METAL3, xc0, y)
                    via(None, L_VIA3, L_METAL4, xc0, y)
                self.box(rc, L_METAL4, min(xs0) - hp, y - hp, tx + hp, y + hp)
            else:
                self.box(rc, L_METAL2, arr_um, y - hp, tx + hp, y + hp)
                via(None, L_VIA2, L_METAL3, tx, y)
                via(None, L_VIA3, L_METAL4, tx, y)
            self.box(rc, L_VIA4, tx - VIA / 2, y - VIA / 2, tx + VIA / 2, y + VIA / 2)
            seam_pads[net].append(y)

        ties = self.ties(top)
        tie_pads = [kdb.DBox(t["x"] - hp, t["y"] - hp, t["x"] + hp, t["y"] + hp) for t in ties]
        # Metal2 / Metal3 obstacles in a 5 um hash: [(net-or-None, DBox)]. Signals are net None.
        obst: dict[tuple[int, int], list[tuple[str | None, kdb.DBox]]] = {}
        obst3: dict[tuple[int, int], list[kdb.DBox]] = {}

        def put(h: dict, item, b: kdb.DBox) -> None:
            for gx in range(int(b.left // 5), int(b.right // 5) + 1):
                for gy in range(int(b.bottom // 5), int(b.top // 5) + 1):
                    h.setdefault((gx, gy), []).append(item)

        def add_obst(net: str | None, b: kdb.DBox) -> None:
            put(obst, (net, b), b)

        def cells_of(b: kdb.DBox):
            for gx in range(int(b.left // 5), int(b.right // 5) + 1):
                for gy in range(int(b.bottom // 5), int(b.top // 5) + 1):
                    yield gx, gy

        def clear(net: str, b: kdb.DBox) -> bool:
            e = b.enlarged(M2_SPACE + 0.01, M2_SPACE + 0.01)
            for c in cells_of(e):
                for n, ob in obst.get(c, ()):
                    if e.overlaps(ob) and (n != net or not b.touches(ob)):
                        return False  # other net, or same net but neither merged nor 0.21 apart
            return True

        def clear3(b: kdb.DBox) -> bool:
            e = b.enlarged(M3_SPACE + 0.01, M3_SPACE + 0.01)
            return not any(e.overlaps(ob) for c in cells_of(e) for ob in obst3.get(c, ()))

        for ob in self.signal_boxes(top, L_METAL2, tie_pads):
            add_obst(None, ob)
        for ob in self.signal_boxes(top, L_METAL3, []):
            put(obst3, ob, ob)
        for t, tp in zip(ties, tie_pads):
            add_obst(t["net"], tp)

        # Metal4 lanes: per region, VDD at y0 + 0.6 + j * pitch, VSS half a pitch above. A lane keeps clear of every
        # strap pad (Metal4 pad at a trunk) inside its x-range and of the other net's lanes; it moves (nearest free
        # spot) rather than the pitch.
        lanes: dict[tuple[int, str], list[float]] = {}
        for ri, rb in enumerate(regions):
            y0, y1 = rb.bottom * DBU, rb.top * DBU
            span = {n: (min(rb.left * DBU, trunk_x[n] - hp), max(rb.right * DBU, trunk_x[n] + hp)) for n in trunk_x}
            pads = {n: [y for m in trunk_x if span[n][0] <= trunk_x[m] + hp and trunk_x[m] - hp <= span[n][1]
                        for y in seam_pads[m]] for n in trunk_x}
            lanes[(ri, "VDD")], lanes[(ri, "VSS")] = [], []
            for j in range(int((y1 - 0.3 - y0) // RAIL_LANE_PITCH) + 1):
                for net, off in (("VDD", 0.6), ("VSS", 0.6 + RAIL_LANE_PITCH / 2)):
                    nominal = y0 + off + j * RAIL_LANE_PITCH
                    if nominal > y1 - 0.3:
                        continue
                    other = "VSS" if net == "VDD" else "VDD"
                    for d in [0.0] + [s_ * 0.1 * i for i in range(1, 16) for s_ in (1, -1)]:
                        y = nominal + d
                        if y0 + 0.3 > y or y > y1 - 0.3:
                            continue
                        if any(abs(y - o) < LANE_W / 2 + hp + M3_SPACE for o in pads[net]):
                            continue
                        if any(abs(y - o) < LANE_W + M3_SPACE for o in lanes[(ri, other)]):
                            continue
                        break
                    else:
                        raise AssertionError(f"no lane position near y={nominal} in region {ri}")
                    lanes[(ri, net)].append(round(y, 3))
        self.tie_wiring: list[dict] = []
        used: dict[tuple[int, str], set[float]] = {}
        via2_at: dict[tuple[int, str, float], list[float]] = {}
        for t in ties:
            net, x, y = t["net"], t["x"], t["y"]
            ri = next((i for i, rb in enumerate(regions) if rb.contains(kdb.Point(dbu(x), dbu(y)))), None)
            assert ri is not None, (net, x, y, [str(r) for r in regions])
            # candidates: nearest lanes first, vertical stub straight up/down from the pad, else jogged
            # sideways at the tie's own height (Metal2 horizontal, then vertical)
            chosen = None
            hw = STUB_W / 2
            for ly in sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]:
                lo, hi = min(y, ly), max(y, ly)
                for dx in sorted([round(0.2 * i, 3) for i in range(-30, 31)], key=abs):
                    # a stub beside its own pad must clear it by M2.b (otherwise the joint is a notch or a sliver)
                    if dx and abs(dx) < hp + M2_SPACE + STUB_W / 2 + 0.01:
                        continue
                    xs = round(x + dx, 3)
                    # Via2 (and its Metal3 pad) keep V2.b / M3.b to the other Via2 on the same lane
                    if any(0 < abs(xs - ox) < VIA_PAD + M3_SPACE for ox in via2_at.get((ri, net, ly), ())):
                        continue
                    if not clear3(kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)):
                        continue
                    # vertical first (up/down from the pad, then along the lane's height), else sideways first
                    for variant in (0, 1):
                        if variant == 0:  # horizontal at the tie's height, vertical at xs
                            parts = [kdb.DBox(xs - hw, lo - hp, xs + hw, hi + hp)]
                            if dx:
                                parts.append(kdb.DBox(min(x, xs) - hp, y - hw, max(x, xs) + hp, y + hw))
                        else:  # vertical at the tie's x, horizontal at the lane height
                            if not dx or abs(ly - y) < hp + M2_SPACE + STUB_W / 2 + 0.01:
                                continue
                            parts = [kdb.DBox(x - hw, lo - hp, x + hw, hi + hp),
                                     kdb.DBox(min(x, xs) - hp, ly - hw, max(x, xs) + hp, ly + hw)]
                        if all(clear(net, pt) for pt in parts):
                            chosen = (ly, xs, parts)
                            break
                    if chosen:
                        break
                if chosen:
                    break
            if chosen is None:
                raise AssertionError(f"no clear Metal2 stub for {net} tie at ({x}, {y}); lanes {sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]}, region {ri}")
            ly, xs, parts = chosen
            for pt in parts:
                self.box(rc, L_METAL2, pt.left, pt.bottom, pt.right, pt.top)
                add_obst(net, pt)
            via(None, L_VIA2, L_METAL3, xs, ly)
            via(None, L_VIA3, L_METAL4, xs, ly)
            pad3 = kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)
            put(obst3, pad3, pad3)
            via2_at.setdefault((ri, net, ly), []).append(xs)
            used.setdefault((ri, net), set()).add(ly)
            self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": xs, "region": ri})
        # lanes that serve at least one tie run on Metal4 out to the trunk of their net
        for (ri, net), ys in sorted(used.items()):
            rb = regions[ri]
            tx = trunk_x[net]
            x0 = rb.left * DBU
            for ly in sorted(ys):
                self.box(rc, L_METAL4, x0, ly - LANE_W / 2, tx + hp, ly + LANE_W / 2)
                via(None, L_VIA4, L_METAL4, tx, ly)
        # Metal5 trunks span every lane and strap of their net
        for net in ("VDD", "VSS"):
            ys = list(seam_pads[net]) + [ly for (_, n), v in used.items() if n == net for ly in v]
            tx = trunk_x[net]
            self.box(rc, L_METAL5, tx - TRUNK_W / 2, min(ys) - hp, tx + TRUNK_W / 2, max(ys) + hp)
            self.text(rc, (67, 25), net, tx, min(ys))

    def pins(self, top: kdb.Cell, bb: kdb.Box, ports: list[str], arr_w: int) -> list[dict]:
        out: list[dict] = []
        sl_w = 2 * bc.W_CELL

        def add(name: str, x0: float, y0: float, direction: str, use: str) -> None:
            self.box(top, L_METAL2, x0, y0, x0 + PIN, y0 + PIN)
            self.text(top, L_METAL2_LBL, name, x0 + PIN / 2, y0 + PIN / 2)
            out.append({"name": name, "x": round(x0 + PIN / 2, 3), "y": round(y0 + PIN / 2, 3),
                        "direction": direction, "use": use})

        left, bottom = bb.left * DBU, bb.bottom * DBU
        # bottom edge: D[i], Q[i] either side of slice i's centre, just outside the content so the
        # periphery's Metal2 (issue #92) keeps its spacing to them
        for i in range(SLICES):
            xc = (i + 0.5) * sl_w
            add(f"D[{i}]", round(xc - 1.5, 3), round(bottom - PIN, 3), "INPUT", "SIGNAL")
            add(f"Q[{i}]", round(xc + 1.0, 3), round(bottom - PIN, 3), "OUTPUT", "SIGNAL")
        # left edge: control, address, supplies
        left_pins = [(f"A[{i}]", "INPUT", "SIGNAL") for i in range(7, -1, -1)]
        left_pins += [("CEN", "INPUT", "SIGNAL"), ("CLK", "INPUT", "CLOCK"), ("GWEN", "INPUT", "SIGNAL"),
                      ("WEN", "INPUT", "SIGNAL"), ("VDD", "INOUT", "POWER"), ("VSS", "INOUT", "GROUND")]
        for k, (name, d, u) in enumerate(left_pins):
            add(name, left, round(bottom + PIN_PITCH * (k + 1), 3), d, u)
        assert sorted(p["name"] for p in out) == sorted(ports), "pin set differs from .subckt macro"
        return out


def socket(gen: Gen, top: kdb.Cell) -> dict:
    bb = top.bbox()
    return {
        "schema": "klt.socket/1",
        "name": "sg13g2-sram macro",
        "outline": {"x0": bb.left * DBU, "y0": bb.bottom * DBU, "x1": bb.right * DBU, "y1": bb.top * DBU},
        "pins": [
            {"name": p["name"], "layer": list(L_METAL2_LBL), "metal_layer": list(L_METAL2),
             "x": p["x"], "y": p["y"], "tolerance_um": 0.01,
             "width_um": PIN, "height_um": PIN, "direction": p["direction"], "use": p["use"]}
            for p in gen.pin_list
        ],
    }


def build() -> tuple[kdb.Layout, Gen, kdb.Cell]:
    gen = Gen()
    top = gen.macro()
    return gen.layout, gen, top


def save_options() -> kdb.SaveLayoutOptions:
    opts = kdb.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    return opts


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else GDS_PATH
    layout, gen, top = build()
    layout.write(out, save_options())
    if out == GDS_PATH:
        with open(SOCKET_PATH, "w") as f:
            json.dump(socket(gen, top), f, indent=2)
            f.write("\n")
    bb = top.dbbox()
    print(f"wrote {out}")
    print(f"macro bbox: {bb.width():.3f} x {bb.height():.3f} um  ({bb.width() * bb.height():.1f} um^2)")


if __name__ == "__main__":
    main()
