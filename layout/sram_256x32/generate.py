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
No signal routing in the periphery and none between the array and the column
path, the decoder, or the pins; no supply rails. Each periphery transistor has
its own body tie (Activ + Cont + Metal1 pad, labelled with the bulk net) but the
ties are not yet wired to a rail. The macro is placed and tapped, not connected. DRC (#29), LVS (#30) and power
delivery (#31) are the checks that must be run once routing exists.
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
        self.box(c, bc.L_METAL1, tcx - bc.M1_W / 2, tcy - bc.CO / 2 - bc.CO_ENC_M1, tcx + bc.M1_W / 2, tcy + bc.CO / 2 + bc.CO_ENC_M1)
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
                    other = kdb.Region()
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
        for r in range(ROWS):
            tx, ty = self.wl_terms[r]
            ya, yt, xl = self.wl_y(r), track[r], lane[r]
            self.m1_via1(top, tx, ty)
            self.seg(top, L_METAL2, M2_W, tx, ty, tx, yt)  # stub up to the private track
            self.via_pad(top, L_VIA2, tx, yt)
            self.seg(top, L_METAL3, M3_W, tx, yt, xl, yt)
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
        for ref in ("addr_latch", "control", "row_decoder"):
            ch = self.build(ref)
            bb = ch.bbox()
            dx = right - bb.right
            dy = by - bb.bottom
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(top, ch, dx, dy)
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
            y -= bb.height() + dbu(BLOCK_GAP)

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
        top.shapes(self.li(bc.L_PRBOUNDARY)).insert(top.bbox())
        self.pin_list = pins
        return top

    def pins(self, top: kdb.Cell, bb: kdb.Box, ports: list[str], arr_w: int) -> list[dict]:
        out: list[dict] = []
        sl_w = 2 * bc.W_CELL

        def add(name: str, x0: float, y0: float, direction: str, use: str) -> None:
            self.box(top, L_METAL2, x0, y0, x0 + PIN, y0 + PIN)
            self.text(top, L_METAL2_LBL, name, x0 + PIN / 2, y0 + PIN / 2)
            out.append({"name": name, "x": round(x0 + PIN / 2, 3), "y": round(y0 + PIN / 2, 3),
                        "direction": direction, "use": use})

        left, bottom = bb.left * DBU, bb.bottom * DBU
        # bottom edge: D[i], Q[i] either side of slice i's centre
        for i in range(SLICES):
            xc = (i + 0.5) * sl_w
            add(f"D[{i}]", round(xc - 1.5, 3), bottom, "INPUT", "SIGNAL")
            add(f"Q[{i}]", round(xc + 1.0, 3), bottom, "OUTPUT", "SIGNAL")
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
