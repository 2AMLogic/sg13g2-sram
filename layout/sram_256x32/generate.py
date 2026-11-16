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

Leaf-cell signal nets (issue #104)
---------------------------------
``MazeRouter`` is the net-aware router the periphery nets are drawn with: a two-layer (Metal2 vertical-
preferred, Metal3 horizontal-preferred, joined by Via2) maze on a 0.05 um lattice. Wires are M2.a wide, a
net keeps M2.b / M3.b to every other net's shape (and V2.b between vias), and nets cross on different layers.
``flat_nets`` resolves the hierarchical nets of ``design/macro/macro.spice`` to flat nets per instance path
(supply, bit-line and wordline nets flagged as excluded). Every net with two or more D/G/S terminals inside
``inv``, ``inv_x4``, ``dlatch``, ``nand2/3/4``, ``nor2``, ``precharge``, ``column_mux``, ``sense_amp`` and
``write_driver`` is joined: Via1 on the terminal's Metal1, then the router. The routes stay inside the cell
bounding box. The column-path cells are routed after the bit-line jogs and lanes, which are obstacles to them;
the other cells are packed ``LEAF_PACK_GAP`` apart to leave room. ``leaf_report`` lists, per cell, the nets
routed, the nets with one terminal, the nets excluded by rule and the nets the router could not join.

Latch and control nets (issue #106)
-----------------------------------
``route_hier`` joins, inside ``addr_latch``, ``data_latch``, ``out_latch`` and ``control``, the nets between their
leaf cells with the same router: one terminal per instance port (the leaf cell already joined its own terminals of
the port), a Via1 landing where the leaf cell drew none. The leaf cells' Metal2 / Metal3 are obstacles except the
shapes of the net being drawn. The leaf cells are packed ``HIER_PACK_GAP`` apart. ``hier_report`` lists, per cell, the
nets routed, the single-terminal nets (the cell's ports to other blocks, #95 children 4, 5), the nets excluded by rule
and the nets the router could not join.

Decoder nets (issue #105)
-------------------------
``route_hier`` also joins, inside ``predec3``, ``predec4``, ``wl_drivers`` and ``row_decoder``, the nets between their
child cells (``wl_driver`` is a routed leaf cell), with the same router, aimed by ``toward``; the children of the first
three are leaf cells, those of ``row_decoder`` are cells that ``route_hier`` already routed. A hierarchically routed cell
hands the cell above what a leaf cell does (``export_hier``: its Metal2 / Metal3 per net, body ties, Via2s, landings), so
the nesting needs no second mechanism. The wordline Metal2 stubs and Metal3 tracks that ``route_wordlines`` draws later
(``wl_reserve``) are obstacles; the stub leaves its terminal ``WL_STUB_DX`` sideways, and the wordline driver rows are far
enough apart to hold the track band.

Fan-out between the blocks (issue #107)
---------------------------------------
``route_fanout`` wires every net of ``.subckt macro`` with a terminal in two or more placed blocks or slices
(``inter_block_nets``: the eight global control nets, ``CLK``, the latched address and control bits, and the
per-slice ``DL[i]`` / ``DOUT[i]`` -- 84 nets). It is a reserved-track channel router, not a maze: a flat maze
over the macro would be millions of lattice nodes per layer, and here it is not needed, because every terminal
is first brought to an **escape pin** on the edge of its own cell.

* ``route_slice_escape`` brings the nine ``bit_slice`` ports the macro connects (``SLICE_PORTS``) down to Metal2
  pins at reserved offsets on the slice's bottom edge, ``SLICE_ESCAPE_H`` below the column path, with the same
  ``MazeRouter``. The slice is one cell placed 32 times, so slice *i*'s pins are at a known x and the escape is
  drawn once; every shape of the neighbouring slices is an obstacle, which is what keeps a wire M2.b from its
  own mirror image. The wires leave the cells on the strip between the cells' right edge and the neighbouring
  slice -- at ``SLICE_MARGIN`` = 0.4 that strip is 1.1 um, two Metal2 wires wide.
* ``route_hier`` brings the ports of ``BLOCK_ESCAPES`` out to a pin on one edge of their block -- Metal3 off a
  left edge, Metal2 off a bottom one, the layer the macro level carries on in, so the two wires merge into one
  shape and no via sits on a cell boundary. The maze picks the node (``connect_edge``, A* toward the edge), so a
  port with a single terminal inside the block is routed here too. Metal3 runs almost unobstructed across these
  blocks, which is the room the escapes use.
* The macro level then joins the pins on reserved tracks: one horizontal Metal3 **trunk** per net in the
  **channel** between the slice pins and the data latch (``channel_h``, which is the gap the latch blocks are
  placed below), one vertical Metal2 **lane** per net and side, and one Metal3 track per net in the
  **decoder approach** band (``DECODER_APPROACH``, between the control block's top and the row decoder). The
  west lanes sit left of the address latch, where the column from the channel up to the row decoder is clear;
  the gap lanes sit in the wordline fan-out gap below the array, which no wordline shape reaches (they are all
  above y = 0). A lane and a trunk cross on different layers, which is what lets 72 trunk nets share the
  channel; the only vias are where a net turns, each on its own lane or its own trunk.

``DOUTB[i]`` is not wired: the sense amplifier's complementary output has no terminal outside slice *i* in the
whole macro (``flat_nets``), so it is dangling by design, and recorded as such in ``fanout_report``.

What is NOT drawn (disclosed, not hidden)
-----------------------------------------
No signal routing to the pins (#108, child 5 of #95): the nine Metal2 pin squares touch nothing, so the macro
is not LVS-able yet. The ``VDD``/``VSS`` pin squares are not connected to the rails, and the supply D/S
terminals of the devices are not joined to the ties. Two nets between the cells of ``bit_slice`` are undrawn:
``BLM`` and ``BLBM``, between the column mux, the sense amplifier and the write driver -- they are inside the
slice, not between blocks, so they are outside #107 and have no child of #95 of their own. One leaf-cell net is
undrawn: ``column_mux`` ``BLBM``, whose terminals are separated by the bit-line jogs (Metal2) and lanes
(Metal3) with too few Metal3 crossings left (``leaf_report["column_mux"]["failed"]``). The array interface
(wordlines, bit lines) is routed; the macro is placed, tapped, supplied and wired between its blocks, but not
to its pins. LVS (#30) and power delivery checks (#31) are the checks that must be run once the pins are wired.

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
  interleaved); lanes reach the trunk through a Via4. Where the Metal2 around a tie is taken by the leaf-cell
  nets, the stub leaves on Metal3 from a Via2 on the tie's pad, or is maze-routed (``tie_maze``) to a Via3 on
  the lane; ``tie_wiring`` records which. Nothing below Metal4 enters the wordline gap.
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
DECODER_CLEAR = 1.0  # um between the address latch / control and the wordline gap: room for their body-tie stubs (issue #104)
LEAF_PACK_GAP = 1.2  # um between the devices of a signal-routed leaf cell: room for its Metal2/Metal3 nets (issue #104)
BLOCK_GAP = 3.0  # um between floorplan blocks
SLICE_MARGIN = 0.4  # um kept clear on each side of a slice's column path: the cell-building margin (the
# ``max_w`` the column-path cells pack to) and their placement offset -- the escape channel of issue #107 is
# the 1.1 um strip between the cells' right edge and the neighbouring slice, two Metal2 wires wide
PIN = 0.5  # um, macro pin square on Metal2
PIN_PITCH = 1.0  # um between left-edge pins

# ---- inter-block routing (rule values from `klt deck rules --deck sg13g2`) ----
V1 = 0.19  # V1.a: Via1 is a fixed 0.19 square
# V1.b spacing (0.22) is not enforced by the generator (unlike V2_SPACE, which is); klt drc checks it
M1_ENC_V1 = 0.01  # V1.c: Metal1 enclosure of Via1
M1_V1_PAD = V1 + 2 * M1_ENC_V1  # 0.21: Metal1 landing pad for a Via1 on a 0.20 wire
M2_W = 0.20  # M2.a
M2_SPACE = 0.21  # M2.b
V2 = 0.19  # V2.a
V2_SPACE = 0.22  # V2.b
M3_W = 0.20  # M3.a
M3_SPACE = 0.21  # M3.b
# Metal2/3 wires are 0.20 wide, so a Via (0.19) is enclosed by 0.005 per side (V2.c 0.005)
TRACK_PITCH = M3_W + M3_SPACE  # 0.41: private Metal3 track pitch (M2: same widths)
LANE_PITCH = 0.42  # Metal2 lane pitch in the wordline gap (>= M2_W + M2_SPACE)
TRACK_OFFSET = 0.5  # first private track above its decoder terminal row
LANE_MARGIN = 1.0  # um clear of the decoder edge / the array edge
WL_PAD_X = -0.25  # x of the wordline contact column, left of the array edge
BL_VIA_Y = -0.15  # y of the Via1 stack under each bit-line stripe
WL_FANOUT_GAP = round(2 * LANE_MARGIN + (ROWS - 1) * LANE_PITCH, 3)  # decoder-to-array gap
STUB_W = M2_W  # Metal2 stub from a tie to its lane

# ---- signal router (issue #104) ----
STEP = 50  # dbu: routing lattice pitch (0.05 um); wires are M2_W wide, centred on lattice nodes
WRONG_WAY = 4  # cost of a lattice step against a layer's preferred direction (Metal2 vertical, Metal3 horizontal)
MAX_ROUTE_TRIES = 12  # orderings tried per cell before a net is reported undrawn
VIA_COST = 16  # lattice steps a Via2 is worth (0.8 um): hopping layers for a short run is never worth it, so vias stay V2.b apart
LEAF_ROUTED = ("inv", "inv_x4", "dlatch", "nand2", "nand3", "nand4", "nor2",
               "precharge", "column_mux", "sense_amp", "write_driver", "wl_driver")
HIER_ROUTED = ("addr_latch", "data_latch", "out_latch", "control",
               "predec3", "predec4", "wl_drivers", "row_decoder")  # cells whose nets between child cells are routed (issues #106, #105)
HIER_PACK_GAP = 2.0  # um between the child cells of those: room for their Metal2 / Metal3 nets
LATCH_PACK_GAP = 4.0  # um between the child cells of data_latch / out_latch: 32 of the 33 children also escape a
# port to the macro level (issue #107), so these two need room for their nets, those escapes and the rail stubs
WL_STUB_DX = -0.15  # um: the wordline Metal2 stub leaves its terminal sideways first, clear of the gate landing of the same driver
WL_ROW_TRACKS = 16  # wordline Metal3 tracks stacked above one decoder terminal row (``route_wordlines``)
COLPATH_CELLS = ("precharge", "column_mux", "sense_amp", "write_driver")
SUPPLY_NETS = ("VDD", "VSS")
TIE_MAZE_REACH = ((8.0, 5.0), (20.0, 10.0), (40.0, 16.0), (60.0, 24.0))  # um half-width / half-height of the tie maze window, smallest first

# ---- macro-level fan-out between blocks (issue #107) ----
PIN_LANE = 0.45  # um between escape pins / routing lanes: >= M2.a + M2.b (0.41) and a whole number of STEP
SLICE_ESCAPE_H = 5.0  # um of clear band below a slice's column path: where its nine ports reach their escape pins
DECODER_APPROACH = 5.0  # um between the control block's top and the row decoder: the decoder's escape band
CHANNEL_MARGIN = 1.0  # um kept clear at each end of the fan-out channel (>= M3.b from the pins and the blocks)
LANE_CLEAR = 1.5  # um between a block edge and the first routing lane beside it
# The control block's outputs that fan out to all 32 slices: one Metal3 trunk each in the channel.
GLOBAL_NETS = ("PRE_B", "SEL0", "SEL0B", "SEL1", "SEL1B", "SAE", "WE")
# The nine ``bit_slice`` ports the macro connects, and their escape-pin offset (um) in the slice's own frame. The
# offsets are PIN_LANE apart from PIN_LANE / 2 inside the slice pitch, so a pin keeps M2.b from the mirror pin of
# the neighbouring slice (the span, 8 * PIN_LANE, is under one pitch less twice that margin).
# The pin order follows the ports' terminal x inside the column path, so the escapes cross as little as possible.
SLICE_PORTS = ("PRE_B", "DOUT", "SEL0", "SEL1", "SAE", "DIN", "WE", "SEL0B", "SEL1B")
SLICE_PIN_X0 = 0.15
# Ports the macro-level fan-out brings out of each periphery block, and the edge it brings them out on.
# ``row_decoder``'s ``A[6:0]`` are the latched address bits ``AL[7:1]``; ``control``'s ``A0L`` is ``AL[0]``.
BLOCK_ESCAPES = {
    "control": ("left", ("CLK", "CENL", "GWENL", "WENL", "A0L",
                         "PRE_B", "WLEN", "SAE", "WE", "SEL0", "SEL0B", "SEL1", "SEL1B")),
    "addr_latch": ("left", ("CLK", "AL[7]", "AL[6]", "AL[5]", "AL[4]", "AL[3]", "AL[2]", "AL[1]", "AL[0]",
                            "CENL", "GWENL", "WENL")),
    "row_decoder": ("bottom", ("WLEN",) + tuple(f"A[{i}]" for i in range(6, -1, -1))),
    "data_latch": ("left", ("CLK",) + tuple(f"Q[{i}]" for i in range(SLICES))),
    "out_latch": ("left", ("SAE",) + tuple(f"D[{i}]" for i in range(SLICES))),
}


def dbu(v: float) -> int:
    return int(round(v / DBU))


def snap(v: float) -> float:
    """Round to the 0.005 um manufacturing grid."""
    return round(v / (GRID * DBU)) * (GRID * DBU)


KEEP = dbu(M2_SPACE + M2_W / 2)  # centre-line keep-out around another net's Metal2/Metal3 shape (M2.b / M3.b)


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
# Flat-net resolution
# ---------------------------------------------------------------------------
_BL_NET = re.compile(r"^BLB?\d*$")
_WL_NET = re.compile(r"^WL(\[\d+\])?$")
DEVICE_REFS = ("sg13_lv_nmos", "sg13_lv_pmos")


def excluded_net(name: str) -> str | None:
    """Why a net is not signal-routed here: supply, bit line or wordline (routed by #92, #94)."""
    if name in SUPPLY_NETS:
        return "supply"
    if _BL_NET.match(name):
        return "bit line"
    if _WL_NET.match(name):
        return "wordline"
    return None


def flat_nets(nl: dict[str, Subckt], top: str = TOP) -> dict[str, dict]:
    """Resolve the hierarchical nets of ``top`` to flat nets, one per instance path.

    Returns ``{name: {"aliases": [...], "terminals": [(path, device, term)], "excluded": reason|None}}``
    where ``name`` is the alias nearest the top (``XS[3]/N1`` for a net internal to an instance) and a terminal is
    ``(instance path, device name, "D"/"G"/"S"/"B")``. A net is excluded when any alias is a supply,
    bit-line or wordline name. ``bitcell`` is a drawn leaf of the array and is not descended into."""
    parent: dict[tuple, tuple] = {}

    def find(a: tuple) -> tuple:
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a: tuple, b: tuple) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    terms: list[tuple[tuple, tuple[str, str, str]]] = []

    def walk(sub: str, path: tuple) -> None:
        for inst in nl[sub].insts:
            ipath = path + (inst.name,)
            if inst.ref in DEVICE_REFS:
                for t, n in zip("DGSB", inst.nets[:4]):
                    terms.append(((path, n), ("/".join(ipath[:-1]), inst.name, t)))
                    find((path, n))
            elif inst.ref in nl and inst.ref != "bitcell":
                for port, n in zip(nl[inst.ref].ports, inst.nets):
                    union((ipath, port), (path, n))
                walk(inst.ref, ipath)

    walk(top, ())
    groups: dict[tuple, list[tuple]] = {}
    for node in list(parent):
        groups.setdefault(find(node), []).append(node)
    members: dict[tuple, list] = {}
    for node, term in terms:
        members.setdefault(find(node), []).append(term)
    out: dict[str, dict] = {}
    for root, nodes in groups.items():
        nodes.sort(key=lambda pn: (len(pn[0]), pn[0], pn[1]))
        aliases = ["/".join(p + (n,)) for p, n in nodes]
        why = next((r for r in (excluded_net(n) for _, n in nodes) if r), None)
        out[aliases[0]] = {"aliases": aliases, "terminals": sorted(members.get(root, [])), "excluded": why}
    return out


# ---------------------------------------------------------------------------
# Net-aware router: Metal2 / Metal3 maze on a 0.05 um lattice
# ---------------------------------------------------------------------------
class MazeRouter:
    """Two-layer (layer 0 = Metal2, 1 = Metal3, joined by Via2) maze router.

    Wires are ``M2_W`` wide and centred on lattice nodes ``STEP`` apart. Every committed shape marks the nodes
    within ``KEEP`` of it as that net's (``owner`` = net id); a node claimed by two nets is blocked for both
    (-1), so a wire of another net never comes within the M2.b / M3.b spacing, and two nets cross only by using
    different layers. Vias keep a Chebyshev distance of ``KEEP`` from one another. Terminals are Metal2 pads."""

    def __init__(self, left: int, bottom: int, right: int, top: int) -> None:
        h = dbu(M2_W / 2)
        self.i0, self.i1 = -(-(left + h) // STEP), (right - h) // STEP
        self.j0, self.j1 = -(-(bottom + h) // STEP), (top - h) // STEP
        self.nx, self.ny = self.i1 - self.i0 + 1, self.j1 - self.j0 + 1
        self.owner = [[[0] * self.ny for _ in range(self.nx)] for _ in range(2)]
        self.via_near: set[tuple[int, int]] = set()
        self.shapes: dict[int, list[tuple]] = {}  # net id -> [("wire", layer, a, b) | ("via", node)]
        self.exits: dict[int, tuple[int, int, int]] = {}  # net id -> the (layer, i, j) it left the window at (#107)

    def node(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(dbu(x) / STEP + 0.5), math.floor(dbu(y) / STEP + 0.5)  # ties round up in every frame

    def inside(self, i: int, j: int) -> bool:
        return self.i0 <= i <= self.i1 and self.j0 <= j <= self.j1

    def _mark(self, layer: int, x0: int, y0: int, x1: int, y1: int, net: int) -> None:
        """Claim every node whose centre-line would sit within KEEP of the dbu rectangle."""
        lo_i, hi_i = (x0 - KEEP) // STEP + 1, -(-(x1 + KEEP) // STEP) - 1
        lo_j, hi_j = (y0 - KEEP) // STEP + 1, -(-(y1 + KEEP) // STEP) - 1
        own = self.owner[layer]
        for i in range(max(lo_i, self.i0), min(hi_i, self.i1) + 1):
            col = own[i - self.i0]
            for j in range(max(lo_j, self.j0), min(hi_j, self.j1) + 1):
                o = col[j - self.j0]
                col[j - self.j0] = net if (o == 0 or o == net) and net > 0 else -1

    def block(self, layer: int, x0: float, y0: float, x1: float, y1: float) -> None:
        """A hard obstacle (um box) on one layer, for every net."""
        self._mark(layer, dbu(x0), dbu(y0), dbu(x1), dbu(y1), -1)

    def own(self, layer: int, x0: float, y0: float, x1: float, y1: float, net: int) -> None:
        """Give ``net`` the nodes a wire could occupy inside its own shape (um box) on one layer: a wire there adds no
        geometry, so another net's keep-out around the shape does not apply to it."""
        h = M2_W / 2
        for i in range(max(-(-dbu(x0 + h) // STEP), self.i0), min(dbu(x1 - h) // STEP, self.i1) + 1):
            for j in range(max(-(-dbu(y0 + h) // STEP), self.j0), min(dbu(y1 - h) // STEP, self.j1) + 1):
                if self.owner[layer][i - self.i0][j - self.j0] in (0, -1, net):
                    self.owner[layer][i - self.i0][j - self.j0] = net

    def pad(self, layer: int, node: tuple[int, int], net: int) -> None:
        h = dbu(M2_W / 2)
        i, j = node
        self._mark(layer, i * STEP - h, j * STEP - h, i * STEP + h, j * STEP + h, net)

    def connect(self, net: int, tree: set[tuple[int, int, int]], goals: set[tuple[int, int, int]],
                toward: tuple[int, int] | None = None):
        """Cheapest path from any (layer, i, j) of ``tree`` to a goal (layer, i, j); None if there is none.

        ``toward`` (an (i, j) node) turns the search into an A* aimed at it rather than one spreading in every
        direction, for a net of many terminals: the Manhattan distance to a node never overestimates a path to it (a
        lattice step costs at least 1), so the path found is still a cheapest one. Left at ``None`` the heuristic is
        0 and this *is* Dijkstra over the goal set. ``toward`` aims at *the one* goal: that heuristic is admissible
        only for the node it aims at, so an aimed call must pass ``goals == {(0, *toward)}`` — with other goals in
        the set a first-popped goal can cost more than the cheapest path, and the call is rejected."""
        import heapq

        assert toward is None or goals == {(0, *toward)}, (toward, goals)

        aimed = toward is not None
        gi, gj = toward if aimed else (0, 0)
        dist: dict[tuple, int] = {n: 0 for n in tree}
        prev: dict[tuple, tuple] = {}
        # Heap entries are (d + heuristic, d, layer, i, j). Unaimed the heuristic is 0, so the second element ties
        # wherever the first does and the pop order is the (d, layer, i, j) one a plain Dijkstra heap would give.
        heap = [((abs(i - gi) + abs(j - gj)) if aimed else 0, 0, l, i, j) for l, i, j in sorted(tree)]
        heapq.heapify(heap)
        owner, i0, i1, j0, j1 = self.owner, self.i0, self.i1, self.j0, self.j1
        via_near = self.via_near
        big = 1 << 30
        while heap:
            _, d, l, i, j = heapq.heappop(heap)
            if d > dist.get((l, i, j), big):
                continue
            if (l, i, j) in goals:
                path = [(l, i, j)]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            ch, cv = (WRONG_WAY, 1) if l == 0 else (1, WRONG_WAY)  # Metal2 prefers vertical, Metal3 horizontal
            own = owner[l]
            nxt = []
            for c, i2, j2 in ((ch, i + 1, j), (ch, i - 1, j), (cv, i, j + 1), (cv, i, j - 1)):
                if i0 <= i2 <= i1 and j0 <= j2 <= j1:
                    o = own[i2 - i0][j2 - j0]
                    if o == 0 or o == net:
                        nxt.append((c, l, i2, j2))
            if (i, j) not in via_near:
                o = owner[1 - l][i - i0][j - j0]
                if o == 0 or o == net:
                    nxt.append((VIA_COST, 1 - l, i, j))
            for c, l2, i2, j2 in nxt:
                n2 = (l2, i2, j2)
                if d + c < dist.get(n2, big):
                    dist[n2] = d + c
                    prev[n2] = (l, i, j)
                    h = (abs(i2 - gi) + abs(j2 - gj)) if aimed else 0
                    heapq.heappush(heap, (d + c + h, d + c, l2, i2, j2))
        return None

    def connect_edge(self, net: int, tree: set[tuple[int, int, int]], goals: set[tuple[int, int, int]],
                     horizontal: bool, at: int):
        """``connect`` to the cheapest of ``goals``, all of which lie on one edge of the window, with A*.

        An escape pin of issue #107 is any node of a whole window edge, which plain ``connect`` would search as an
        undirected Dijkstra -- over the row decoder's 175 x 178 um window, millions of nodes. The lattice distance
        to that edge (``at``: the row index if ``horizontal``, else the column index) never overestimates a path to
        it, since a step costs at least 1, so the same search runs directed and still admissible."""
        import heapq

        dist: dict[tuple, int] = {n: 0 for n in tree}
        prev: dict[tuple, tuple] = {}
        hf = (lambda i, j: abs(j - at)) if horizontal else (lambda i, j: abs(i - at))
        heap = [(hf(i, j), 0, l, i, j) for l, i, j in sorted(tree)]
        heapq.heapify(heap)
        owner, i0, i1, j0, j1 = self.owner, self.i0, self.i1, self.j0, self.j1
        via_near = self.via_near
        big = 1 << 30
        while heap:
            _, d, l, i, j = heapq.heappop(heap)
            if d > dist.get((l, i, j), big):
                continue
            if (l, i, j) in goals:
                path = [(l, i, j)]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return path[::-1]
            ch, cv = (WRONG_WAY, 1) if l == 0 else (1, WRONG_WAY)
            own = owner[l]
            nxt = []
            for c, i2, j2 in ((ch, i + 1, j), (ch, i - 1, j), (cv, i, j + 1), (cv, i, j - 1)):
                if i0 <= i2 <= i1 and j0 <= j2 <= j1:
                    o = own[i2 - i0][j2 - j0]
                    if o == 0 or o == net:
                        nxt.append((c, l, i2, j2))
            if (i, j) not in via_near:
                o = owner[1 - l][i - i0][j - j0]
                if o == 0 or o == net:
                    nxt.append((VIA_COST, 1 - l, i, j))
            for c, l2, i2, j2 in nxt:
                n2 = (l2, i2, j2)
                if d + c < dist.get(n2, big):
                    dist[n2] = d + c
                    prev[n2] = (l, i, j)
                    heapq.heappush(heap, (d + c + hf(i2, j2), d + c, l2, i2, j2))
        return None

    def commit(self, net: int, path: list[tuple[int, int, int]]) -> None:
        h = dbu(M2_W / 2)
        out = self.shapes.setdefault(net, [])
        for (l, i, j), (l2, i2, j2) in zip(path, path[1:]):
            if l != l2:
                out.append(("via", (i, j)))
                near = dbu(V2 + V2_SPACE) // STEP  # Chebyshev reach of a Via2 on the lattice
                for di in range(-near, near + 1):
                    for dj in range(-near, near + 1):
                        self.via_near.add((i + di, j + dj))
                self.pad(1 - l, (i, j), net)
            else:
                last = out[-1] if out else None
                if (last and last[0] == "wire" and last[1] == l and last[3] == (i, j)
                        and (last[2][0] == i) == (i == i2) and (last[2][1] == j) == (j == j2)):
                    out[-1] = ("wire", l, last[2], (i2, j2))  # extend a straight run
                else:
                    out.append(("wire", l, (i, j), (i2, j2)))
                self._mark(l, min(i, i2) * STEP - h, min(j, j2) * STEP - h, max(i, i2) * STEP + h, max(j, j2) * STEP + h, net)

    def route_net(self, net: int, terminals: list[tuple[int, int]], directed: bool = False,
                  exits: set[tuple[int, int, int]] | None = None,
                  exit_edge: tuple[bool, int] = (True, 0),
                  m3_arrive: set[tuple[int, int]] | None = None) -> bool:
        """Join the terminals (Metal2 pads, already claimed with ``pad``) into one tree. ``directed``: join the terminal
        nearest the tree next, searching toward it only (nets of many terminals). ``exits``: the net must also reach
        one of these (layer, i, j) on the window's edge, the escape pin the cell above wires from (issue #107); the
        one it reached is recorded in ``self.exits``. ``exit_edge`` names that edge for the A* heuristic --
        ``(True, j)`` for the lattice row ``j``, ``(False, i)`` for the column ``i``. ``m3_arrive``: terminals the
        route may reach on Metal3 -- only where the caller draws a Metal3 pad over the terminal (the escape's lane
        tops carry a Via2 stack, so the stub may arrive on Metal3; issue #107)."""
        if len(terminals) < 2 and not exits:
            return True
        tree = {(0, *terminals[0])}
        todo = set(terminals[1:])
        todo -= {t for t in todo if (0, *t) in tree}
        while todo:
            arrive = m3_arrive or set()
            goals = {(0, *t) for t in todo} | {(1, *t) for t in todo if t in arrive}
            if directed:
                near = min(sorted(todo), key=lambda t: min(abs(t[0] - n[1]) + abs(t[1] - n[2]) for n in tree))
                path = self.connect(net, tree, {(0, *near)}, toward=near)
            else:
                path = self.connect(net, tree, goals)
            if path is None:
                return False
            self.commit(net, path)
            tree |= set(path)
            todo.discard(path[-1][1:])
        if exits:
            hit = sorted(tree & exits)
            if not hit:
                horizontal, at = exit_edge
                path = self.connect_edge(net, tree, exits, horizontal, at)
                if path is None:
                    return False
                self.commit(net, path)
                hit = [path[-1]]
            self.exits[net] = hit[0]
        return True


def route_orders(names: list[str], size: dict[str, int]) -> list[list[str]]:
    """Net orderings to try: short nets first, long first, then reversed alphabetical, then every rotation of
    each (issue #107: two nets that each route alone can block each other, and a rotation changes who goes
    first). The base orders come first, so a router that succeeds on one of them never sees a rotation."""
    by = sorted(names, key=lambda n: (size[n], n))
    bases = [by, by[::-1], sorted(names, reverse=True)]
    orders = list(bases)
    for base in bases:
        for k in range(1, len(base)):
            orders.append(base[k:] + base[:k])
    return orders


OBST_HASH_PITCH = 5.0  # um cell size of the supply-rail obstacle spatial hash


class Obstacles:
    """Metal2/Metal3 obstacle hashes of one macro, indexed by an ``OBST_HASH_PITCH``-um grid, with the
    DRC-spacing model the supply-rail stubs are checked against: ``clear`` is the Metal2 rule (M2.b plus a
    0.01 margin to every other net's shape, or to a same-net shape not merging with the candidate; a corner
    overlap of two same-net shapes narrower than the stub is a sliver under M2.a), ``clear3`` the Metal3 rule
    (M3.b plus the same margin). Signal shapes are stored under net ``None`` and block every net."""

    def __init__(self) -> None:
        self.m2: dict[tuple[int, int], list[tuple[str | None, kdb.DBox]]] = {}
        self.m3: dict[tuple[int, int], list[kdb.DBox]] = {}

    @staticmethod
    def cells_of(b: kdb.DBox):
        for gx in range(int(b.left // OBST_HASH_PITCH), int(b.right // OBST_HASH_PITCH) + 1):
            for gy in range(int(b.bottom // OBST_HASH_PITCH), int(b.top // OBST_HASH_PITCH) + 1):
                yield gx, gy

    def add(self, net: str | None, b: kdb.DBox) -> None:
        item = (net, b)
        for c in self.cells_of(b):
            self.m2.setdefault(c, []).append(item)

    def add_m3(self, b: kdb.DBox) -> None:
        for c in self.cells_of(b):
            self.m3.setdefault(c, []).append(b)

    def clear(self, net: str, b: kdb.DBox) -> bool:
        e = b.enlarged(M2_SPACE + 0.01, M2_SPACE + 0.01)
        for c in self.cells_of(e):
            for n, ob in self.m2.get(c, ()):
                if e.overlaps(ob) and (n != net or not b.touches(ob)):
                    return False  # other net, or same net but neither merged nor 0.21 apart
                if n == net and e.overlaps(ob) and b.touches(ob):
                    ov = b & ob
                    if not ov.empty() and min(ov.width(), ov.height()) < STUB_W - 0.001:
                        return False  # a corner overlap of two same-net shapes is a sliver narrower than M2.a
        return True

    def clear3(self, b: kdb.DBox) -> bool:
        e = b.enlarged(M3_SPACE + 0.01, M3_SPACE + 0.01)
        return not any(e.overlaps(ob) for c in self.cells_of(e) for ob in self.m3.get(c, ()))


@dataclass
class RailState:
    """Draw target and bookkeeping the supply-rail tie searches share: the rails cell shapes are added to,
    the Via2s already committed per (region, net, lane) x position, and the lanes already serving a tie."""

    rc: kdb.Cell
    via2_at: dict[tuple[int, str, float], list[float]] = field(default_factory=dict)
    used: dict[tuple[int, str], set[float]] = field(default_factory=dict)


def in_wl_gap(x0: float, x1: float) -> bool:
    """An x-span intersecting the open wordline fan-out gap (0 to -WL_FANOUT_GAP): nothing below Metal4 may
    enter it, though a wire edge may reach its boundary."""
    return x1 > -WL_FANOUT_GAP and x0 < 0


def lane_positions(regions: list[kdb.Box], trunk_x: dict[str, float],
                   seam_pads: dict[str, list[float]]) -> tuple[dict[tuple[int, str], list[float]],
                                                               dict[tuple[int, str], list[float]]]:
    """Metal4 lane y positions per (region, net), and the strap pads per (region, net) a free lane must avoid:
    per region, VDD at y0 + 0.6 + j * pitch, VSS half a pitch above. A lane keeps clear of every strap pad
    (Metal4 pad at a trunk) inside its x-range and of the other net's lanes; it moves (nearest free spot) rather
    than the pitch."""
    hp = VIA_PAD / 2
    lanes: dict[tuple[int, str], list[float]] = {}
    pads_of: dict[tuple[int, str], list[float]] = {}
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
        for net in trunk_x:
            pads_of[(ri, net)] = pads[net]
    return lanes, pads_of


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
        # leaf-cell signal routing (issue #104): what was drawn and what was not, per cell
        self.leaf_report: dict[str, dict] = {}
        self.leaf_terms: dict[str, dict[str, list[tuple[float, float]]]] = {}  # cell -> net -> M1 landing points
        self.leaf_vias: dict[str, list[dict]] = {}
        self.leaf_shapes: dict[str, dict[str, dict[int, kdb.Region]]] = {}  # cell -> net -> {0: Metal2, 1: Metal3} drawn
        self.leaf_ties: dict[str, list[tuple[float, float]]] = {}  # cell -> body-tie points (their Metal2 / Metal3 pads)
        # routing of the nets between leaf cells (issue #106): report and terminal points per cell
        self.hier_report: dict[str, dict] = {}
        self.hier_landed: dict[str, set[str]] = {}  # hierarchical cell -> ports whose terminal already carries a landing
        self.hier_terms: dict[str, dict[str, list[tuple[float, float]]]] = {}
        # macro-level fan-out (issue #107): the escape pin each block port was brought out to, in the cell's own
        # frame, and the per-cell escape report
        self.escape_pins: dict[str, dict[str, tuple[float, float]]] = {}
        self.escape_report: dict[str, dict] = {}
        self.fanout_report: dict = {}

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
    def pack(self, items: list[kdb.Cell], max_w: float, pack_gap: float = PACK_GAP,
             lattice: bool = False, row_gap: float | None = None) -> tuple[list[tuple[kdb.Cell, int, int]], int, int]:
        """Shelf-pack cells by bbox. Returns [(cell, dx, dy)] placing each
        bbox's lower-left at the shelf position, plus the packed width/height.
        ``lattice``: offsets are multiples of ``STEP``, so a child's routing lattice is the parent's. ``row_gap``:
        the space between shelves, where it differs from the one between cells (the wordline driver rows)."""
        gap, mw = dbu(pack_gap), dbu(max_w)
        rgap = gap if row_gap is None else dbu(row_gap)
        out: list[tuple[kdb.Cell, int, int]] = []
        x = y = row_h = used = 0
        for c in items:
            bb = c.bbox()
            if x > 0 and x + bb.width() > mw:
                y += row_h + rgap
                x = row_h = 0
            dx, dy = x - bb.left, y - bb.bottom
            if lattice:
                dx, dy = -(-dx // STEP) * STEP, -(-dy // STEP) * STEP
                x, y = dx + bb.left, dy + bb.bottom
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
        placed, _, _ = self.pack(items, mw,
                                 LATCH_PACK_GAP if name in ("data_latch", "out_latch") else
                                 HIER_PACK_GAP if name in HIER_ROUTED else
                                 LEAF_PACK_GAP if name in LEAF_ROUTED and name not in COLPATH_CELLS else PACK_GAP,
                                 lattice=name in HIER_ROUTED,
                                 row_gap=max(HIER_PACK_GAP, self.wl_band_overshoot()) if name == "wl_drivers" else None)
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
        if name in COLPATH_CELLS:
            self.route_leaf(name, cell, phase="pads")  # their nets are routed after the bit-line jogs (``bit_slice``)
        elif name == "wl_driver":  # placed once per wordline: keeps room for ``route_wordlines`` over its terminal
            band = self.wl_reserve(name, "WL", worst=True)
            self.route_leaf(name, cell, [(l, kdb.Box(dbu(a), dbu(b), dbu(c), dbu(d))) for l, a, b, c, d in band])
        elif name in LEAF_ROUTED:
            self.route_leaf(name, cell)
        elif name in HIER_ROUTED:
            self.route_hier(name, cell)
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

    # ---- leaf-cell signal routing (issue #104) ------------------------------
    def draw_shapes(self, cell: kdb.Cell, shapes: list[tuple]) -> tuple[dict[int, kdb.Region], list[dict]]:
        """Draw a ``MazeRouter`` net's wires (Metal2 / Metal3) and Via2s into ``cell``; returns the net's regions per
        layer and its vias."""
        drawn = {0: kdb.Region(), 1: kdb.Region()}
        vias: list[dict] = []
        for sh in shapes:
            if sh[0] == "wire":
                _, l, a, b = sh
                self.seg(cell, L_METAL2 if l == 0 else L_METAL3, M2_W,
                         a[0] * STEP * DBU, a[1] * STEP * DBU, b[0] * STEP * DBU, b[1] * STEP * DBU)
                drawn[l].insert(kdb.Box(dbu(min(a[0], b[0]) * STEP * DBU - M2_W / 2), dbu(min(a[1], b[1]) * STEP * DBU - M2_W / 2),
                                        dbu(max(a[0], b[0]) * STEP * DBU + M2_W / 2), dbu(max(a[1], b[1]) * STEP * DBU + M2_W / 2)))
            else:
                x, y = sh[1][0] * STEP * DBU, sh[1][1] * STEP * DBU
                self.via_pad(cell, L_VIA2, x, y)
                self.rect(cell, L_METAL2, x, y, M2_W, M2_W)
                self.rect(cell, L_METAL3, x, y, M3_W, M3_W)
                vias.append({"x": round(x, 3), "y": round(y, 3)})
        return drawn, vias

    def route_leaf(self, name: str, cell: kdb.Cell, extra: list[tuple[int, kdb.Box]] = (), phase: str = "all") -> None:
        """Draw the intra-cell signal nets of a leaf cell on Metal2/Metal3 (Via1 landings on the Metal1 terminals).

        A net is drawn when it has two or more D/G/S terminals in the cell; supply nets and the bit-line nets
        (routed at slice level) are not signal-routed here, and a net with one terminal has nothing to join.
        Whatever is not drawn is listed in ``leaf_report``. The routes stay inside the cell's bounding box, so
        placement and every other cell are unchanged. ``phase`` "pads" only draws the terminal landings (so the
        slice's bit-line jogs, which are drawn next, keep clear of them), "wires" the nets between them."""
        pts = self.dev_pts[name]
        by_net: dict[str, list[tuple[str, str, tuple[float, float]]]] = {}
        for inst in self.nl[name].insts:
            if inst.name in pts:
                for t, n in zip("DGS", inst.nets[:3]):
                    by_net.setdefault(n, []).append((inst.name, t, pts[inst.name][t]))
        bb = cell.bbox()
        mz = MazeRouter(bb.left, bb.bottom, bb.right, bb.top)
        report = {"routed": {}, "single_terminal": [], "excluded": {}, "failed": []}
        names = sorted(n for n, v in by_net.items() if not excluded_net(n) and len(v) >= 2)
        for n, v in sorted(by_net.items()):
            why = excluded_net(n)
            if why:
                report["excluded"][n] = {"reason": why, "terminals": len(v)}
            elif len(v) < 2:
                report["single_terminal"].append(n)
        ids = {n: k + 1 for k, n in enumerate(names)}
        node = {n: [mz.node(x, y) for _, _, (x, y) in by_net[n]] for n in names}
        # fixed obstacles: body-tie Metal2 pads, bit-line terminals (their Metal2 comes at slice level) and,
        # in the column path, the slice's bit-line Metal3 lanes
        hp = VIA_PAD / 2
        for inst in self.nl[name].insts:
            if inst.name in pts:
                tx, ty = pts[inst.name]["B"]
                self.leaf_ties.setdefault(name, []).append((tx, ty))
                mz.block(0, tx - hp, ty - hp, tx + hp, ty + hp)
                mz.block(1, tx - hp, ty - hp, tx + hp, ty + hp)  # room for a Via2 + Metal3 pad on the tie (rails)
        for n, v in by_net.items():
            if excluded_net(n) == "bit line":
                for _, _, (x, y) in v:
                    mz.block(0, x - M2_W / 2, y - M2_W / 2, x + M2_W / 2, y + M2_W / 2)
        for layer, eb in extra:  # Metal2 jogs and Metal3 lanes the parent already drew over the cell (bit lines)
            mz.block(layer, eb.left * DBU, eb.bottom * DBU, eb.right * DBU, eb.top * DBU)
        if phase == "pads":
            for n in names:
                for t in sorted(set(node[n])):
                    self.m1_via1(cell, t[0] * STEP * DBU, t[1] * STEP * DBU)
            return
        mz, failed = self.search_routes(bb, mz, names, ids, node)
        for n in names:
            if phase == "all":
                for t in sorted(set(node[n])):
                    self.m1_via1(cell, t[0] * STEP * DBU, t[1] * STEP * DBU)
            if n in failed:
                report["failed"].append(n)
                continue
            report["routed"][n] = len(by_net[n])
            drawn, vias = self.draw_net(cell, mz, ids[n], node[n])
            self.leaf_shapes.setdefault(name, {})[n] = drawn
            self.leaf_vias.setdefault(name, []).extend({"net": n, **v} for v in vias)
        self.leaf_terms[name] = {n: [(t[0] * STEP * DBU, t[1] * STEP * DBU) for t in sorted(set(node[n]))]
                                 for n in names if n not in failed}
        self.leaf_report[name] = report

    def search_routes(self, bb: kdb.Box, base: MazeRouter, names: list[str], ids: dict[str, int],
                      node: dict[str, list[tuple[int, int]]], directed: bool = False,
                      tries: int = MAX_ROUTE_TRIES,
                      exits: dict[str, set[tuple[int, int, int]]] | None = None,
                      exit_edge: tuple[bool, int] = (True, 0)) -> tuple[MazeRouter, list[str]]:
        """Route ``names`` over ``base`` (its obstacles and claims), trying up to ``tries`` orderings; returns
        the router of the ordering that left the fewest nets undrawn, and those nets."""
        size = {n: max(1, sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in node[n] for b in node[n])) for n in names}
        best = None
        tried: list[list[str]] = []
        orders = route_orders(names, size) if names else [[]]
        while orders and len(tried) < tries:
            order = orders.pop(0)
            if order in tried:
                continue
            tried.append(order)
            mz = MazeRouter(bb.left, bb.bottom, bb.right, bb.top)
            mz.owner = [[col[:] for col in lay] for lay in base.owner]
            mz.via_near = set(base.via_near)
            for n in names:
                for t in node[n]:
                    mz.pad(0, t, ids[n])
            failed = [n for n in order
                      if not mz.route_net(ids[n], sorted(set(node[n])), directed, (exits or {}).get(n),
                                          exit_edge)]
            if best is None or len(failed) < len(best[1]):
                best = (mz, failed)
            if not failed:
                break
            # rip up and reroute: the nets that did not fit go first next time
            orders.append(failed + [n for n in order if n not in failed])
            orders.append([n for n in order if n not in failed] + failed[::-1])
        return best if best else (base, [])

    def draw_net(self, cell: kdb.Cell, mz: MazeRouter, nid: int, pts: list[tuple[int, int]],
                 own: dict[int, kdb.Region] | None = None) -> tuple[dict[int, kdb.Region], list[dict]]:
        """Draw one routed net into ``cell``; returns its regions per layer and its Via2s. ``own``: shapes of the same
        net already in the cell (a leaf cell's, in this cell's frame); every gap under the layer's spacing between
        them and the new wires is filled (a morphological closing), as the net is one shape."""
        drawn, vias = self.draw_shapes(cell, mz.shapes.get(nid, []))
        for t in sorted(set(pts)):
            drawn[0].insert(kdb.Box(dbu(t[0] * STEP * DBU - M2_W / 2), dbu(t[1] * STEP * DBU - M2_W / 2),
                                    dbu(t[0] * STEP * DBU + M2_W / 2), dbu(t[1] * STEP * DBU + M2_W / 2)))
        for l in (0, 1):
            if own:
                drawn[l] += own[l]
        # two parts of one net that run closer than the layer's spacing (a wire folding back beside itself) are
        # joined: the gap is filled, so the pair is one shape instead of a spacing violation
        for l, lp in ((0, L_METAL2), (1, L_METAL3)):
            rg = drawn[l].merged()
            if own:
                h = dbu(M2_SPACE) // 2
                fill = rg.sized(h).sized(-h) - rg
                cell.shapes(self.li(lp)).insert(fill)
                drawn[l] += fill
                continue
            gaps = rg.space_check(dbu(M2_SPACE)) + rg.notch_check(dbu(M2_SPACE))
            for ep in gaps.each():
                cell.shapes(self.li(lp)).insert(ep.bbox())
                drawn[l].insert(ep.bbox())
        return drawn, vias

    # ---- wordline room (issue #105) -------------------------------------------
    def wl_band_overshoot(self) -> float:
        """How far (um) the wordline Metal2 stubs and Metal3 tracks of one terminal row reach above the top of a
        ``wl_driver`` cell, with the spacing the next row's cell keeps to them."""
        c = self.cells["wl_driver"]
        top = TRACK_OFFSET + (WL_ROW_TRACKS - 1) * TRACK_PITCH
        return max(0.0, self.terminal("wl_driver", "WL")[1] + top + M3_W / 2 + M3_SPACE - c.bbox().top * DBU)

    def wl_reserve(self, name: str, port: str, worst: bool = False) -> list[tuple[int, float, float, float, float]]:
        """Metal2 / Metal3 boxes (layer, um, in ``name``'s frame) that ``route_wordlines`` will draw over the wordline
        terminals of ``name`` (ports ``port`` or ``port[r]``): the Metal2 stub up from each terminal and, ``TRACK_OFFSET``
        + k * ``TRACK_PITCH`` above its row, the Metal3 track that runs right to the decoder edge. In a frame that holds
        the whole row, k follows from the terminal's place in it (the rightmost gets the lowest track). A cell
        that is placed once per terminal (``worst``) cannot know k, so it keeps the whole band of ``WL_ROW_TRACKS``
        tracks across its width."""
        bb = self.cells[name].bbox()
        terms = [self.terminal(name, p) for p in self.nl[name].ports if p == port or re.fullmatch(re.escape(port) + r"\[\d+\]", p)]
        terms = [t for t in terms if t is not None]
        out: list[tuple[int, float, float, float, float]] = []
        hw3 = M3_W / 2
        if worst:
            top = TRACK_OFFSET + (WL_ROW_TRACKS - 1) * TRACK_PITCH
            for tx, ty in terms:
                sx = snap(tx + WL_STUB_DX)
                out.append((0, sx - M2_W / 2, ty - M2_W / 2, tx + M2_W / 2, ty + M2_W / 2))
                out.append((0, sx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, ty + top + M2_W / 2))
                out.append((1, bb.left * DBU, ty + TRACK_OFFSET - hw3, bb.right * DBU, ty + top + hw3))
            return out
        rows: dict[float, list[tuple[float, float]]] = {}
        for t in terms:
            rows.setdefault(round(t[1], 2), []).append(t)
        for row in rows.values():
            assert len(row) <= WL_ROW_TRACKS, (name, len(row))
            for k, (tx, ty) in enumerate(sorted(row, key=lambda t: -t[0])):
                yt = ty + TRACK_OFFSET + k * TRACK_PITCH
                sx = snap(tx + WL_STUB_DX)
                out.append((0, sx - M2_W / 2, ty - M2_W / 2, tx + M2_W / 2, ty + M2_W / 2))
                out.append((0, sx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, yt + M2_W / 2))
                out.append((1, sx - M2_W / 2, yt - hw3, bb.right * DBU, yt + hw3))
        return out

    def route_hier(self, name: str, cell: kdb.Cell) -> None:
        """Draw the nets between the leaf cells of ``name`` (Metal2 / Metal3, Via1 landings on terminals with no landing yet).

        A net is the name an instance port is wired to; it is joined at one terminal per instance (the leaf cell
        already joined its own terminals of the port), supply nets are not drawn. The leaf cells' own Metal2 / Metal3
        shapes are obstacles, except the shapes of the nets being drawn, which the new wires may overlap. Nets that do
        not fit are listed in ``hier_report``.

        A cell in ``BLOCK_ESCAPES`` also brings the ports named there out to an **escape pin** on one edge: the net
        must reach a lattice node on that edge, on the layer the macro level continues in (Metal3 off a left edge,
        Metal2 off a bottom one), so the two wires merge into one shape and no via sits on the boundary. The maze
        picks the node, which is why a port with a single terminal in the cell is routed here too, and the pin is
        recorded in ``escape_pins[name]`` for the macro-level fan-out (issue #107)."""
        insts = [i for i in self.nl[name].insts if i.ref in self.nl and i.ref not in DEVICE_REFS]
        by_net: dict[str, list[tuple[str, str, tuple[float, float], bool]]] = {}
        for inst in insts:
            dx, dy = (v * DBU for v in self.place_of[name][inst.name])
            for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                t = self.terminal(inst.ref, port)
                if t is not None:
                    landed = self.port_landed(inst.ref, port)
                    by_net.setdefault(n, []).append((inst.name, port, (t[0] + dx, t[1] + dy), landed))
        side, esc_ports = BLOCK_ESCAPES.get(name, (None, ()))
        esc = tuple(p for p in esc_ports if p in by_net)
        assert len(esc) == len(esc_ports), (name, "escape port with no terminal", set(esc_ports) - set(esc))
        report = {"routed": {}, "single_terminal": [], "excluded": {}, "failed": [], "escaped": list(esc)}
        routed_here: dict[str, tuple[dict[int, kdb.Region], list[dict]]] = {}
        names = sorted(n for n, v in by_net.items() if not excluded_net(n) and (len(v) >= 2 or n in esc))
        for n, v in sorted(by_net.items()):
            why = excluded_net(n)
            if why:
                report["excluded"][n] = {"reason": why, "terminals": len(v)}
            elif len(v) < 2 and n not in esc:
                report["single_terminal"].append(n)
        ids = {n: k + 1 for k, n in enumerate(names)}
        bb = cell.bbox()
        mz = MazeRouter(bb.left, bb.bottom, bb.right, bb.top)
        if side == "left":  # the macro level carries on westward on Metal3 from the leftmost column
            edge = {(1, mz.i0, j) for j in range(mz.j0, mz.j1 + 1)}
            exit_edge = (False, mz.i0)
        elif side == "bottom":  # ... or downward on Metal2 from the bottom row
            edge = {(0, i, mz.j0) for i in range(mz.i0, mz.i1 + 1)}
            exit_edge = (True, mz.j0)
        else:
            assert side is None, (name, side)
            edge, exit_edge = set(), (True, mz.j0)
        exits = {n: edge for n in esc}
        node = {n: [mz.node(x, y) for _, _, (x, y), _ in by_net[n]] for n in names}
        hp = VIA_PAD / 2
        own_boxes: list[tuple[int, int, kdb.Box]] = []  # (layer, net id, box in dbu) of leaf-cell shapes of the nets drawn here
        for inst in insts:
            dx, dy = self.place_of[name][inst.name]
            port_net = dict(zip(self.nl[inst.ref].ports, inst.nets))
            for lx, ly in self.leaf_ties.get(inst.ref, []):
                x, y = lx + dx * DBU, ly + dy * DBU
                for l in (0, 1):
                    mz.block(l, x - hp, y - hp, x + hp, y + hp)
            for n, regs in self.leaf_shapes.get(inst.ref, {}).items():
                nid = ids.get(port_net.get(n, ""), -1)
                for l in (0, 1):
                    for b in (r for poly in regs[l].merged().each() for r in poly.decompose_trapezoids(kdb.Polygon.TD_simple)):
                        bx = b.bbox().moved(dx, dy)
                        mz._mark(l, bx.left, bx.bottom, bx.right, bx.top, nid)
                        if nid > 0:
                            own_boxes.append((l, nid, bx))
        near = dbu(V2 + V2_SPACE) // STEP
        for inst in insts:  # a new Via2 keeps V2.b from the leaf cells' own
            dx, dy = self.place_of[name][inst.name]
            for v in self.leaf_vias.get(inst.ref, []):
                vi, vj = mz.node(v["x"] + dx * DBU, v["y"] + dy * DBU)
                mz.via_near.update((vi + a, vj + b) for a in range(-near, near + 1) for b in range(-near, near + 1))
        for l, nid, bx in own_boxes:
            mz.own(l, bx.left * DBU, bx.bottom * DBU, bx.right * DBU, bx.top * DBU, nid)
        for n in names:
            for t in node[n]:
                mz.own(0, t[0] * STEP * DBU - M2_W / 2, t[1] * STEP * DBU - M2_W / 2,
                       t[0] * STEP * DBU + M2_W / 2, t[1] * STEP * DBU + M2_W / 2, ids[n])
        for l, x0, y0, x1, y1 in self.wl_reserve(name, "WL"):  # what ``route_wordlines`` draws over the wordline terminals
            mz.block(l, x0, y0, x1, y1)
        mz, failed = self.search_routes(bb, mz, names, ids, node, directed=True, exits=exits,
                                        exit_edge=exit_edge)
        pins: dict[str, tuple[float, float, int]] = {}
        for n in esc:
            if n in failed:
                continue
            l, i, j = mz.exits[ids[n]]
            pins[n] = (round(i * STEP * DBU, 3), round(j * STEP * DBU, 3), l)
        self.escape_pins[name] = pins
        for n in names:
            for (_, _, (x, y), landed), t in zip(by_net[n], node[n]):
                if not landed:
                    self.m1_via1(cell, t[0] * STEP * DBU, t[1] * STEP * DBU)
            if n in failed:
                report["failed"].append(n)
                continue
            report["routed"][n] = len(by_net[n])
            own = {l: kdb.Region() for l in (0, 1)}
            for l, nid, bx in own_boxes:
                if nid == ids[n]:
                    own[l].insert(bx)
            drawn, vias = self.draw_net(cell, mz, ids[n], node[n], own)
            routed_here[n] = (drawn, vias)
        # Metal1 landings (um) made here, per drawn net, for the connectivity check (the others are the leaf cells' own)
        self.hier_terms[name] = {n: [(t[0] * STEP * DBU, t[1] * STEP * DBU)
                                     for (_, _, _, landed), t in zip(by_net[n], node[n]) if not landed]
                                 for n in names if n not in failed}
        self.hier_report[name] = report
        self.export_hier(name, insts, routed_here, report)

    def port_landed(self, ref: str, port: str) -> bool:
        """Whether ``terminal(ref, port)`` already carries a Via1 landing joined to the rest of the port's net in ``ref``."""
        if ref in self.leaf_report:
            return port in self.leaf_report[ref]["routed"]
        return port in self.hier_landed.get(ref, ())

    def export_hier(self, name: str, insts: list[Inst], routed_here: dict[str, tuple[dict[int, kdb.Region], list[dict]]],
                    report: dict) -> None:
        """Make ``name`` look like a leaf cell to the cell above (issue #105): its drawn Metal2 / Metal3 per net, body ties,
        Via2s and Metal1 landings, in its own frame and keyed by its net names (``instance/net`` for a net internal to a
        child), the child cells' own plus the nets joined here; and the ports whose terminal is already landed."""
        shapes: dict[str, dict[int, kdb.Region]] = {}
        vias: list[dict] = []
        terms: dict[str, list[tuple[float, float]]] = {}
        ties: list[tuple[float, float]] = []
        for inst in insts:
            dx, dy = self.place_of[name][inst.name]
            port_net = dict(zip(self.nl[inst.ref].ports, inst.nets))

            def key(n: str) -> str:
                return port_net.get(n, f"{inst.name}/{n}")

            for n, regs in self.leaf_shapes.get(inst.ref, {}).items():
                tgt = shapes.setdefault(key(n), {0: kdb.Region(), 1: kdb.Region()})
                for l in (0, 1):
                    tgt[l] += regs[l].moved(dx, dy)
            ties += [(x + dx * DBU, y + dy * DBU) for x, y in self.leaf_ties.get(inst.ref, [])]
            vias += [{**v, "net": key(v["net"]), "x": round(v["x"] + dx * DBU, 3), "y": round(v["y"] + dy * DBU, 3)}
                     for v in self.leaf_vias.get(inst.ref, [])]
            for n, ps in self.leaf_terms.get(inst.ref, {}).items():
                terms.setdefault(key(n), []).extend((x + dx * DBU, y + dy * DBU) for x, y in ps)
        for n, (drawn, vs) in routed_here.items():
            shapes[n] = drawn
            vias += [{"net": n, **v} for v in vs]
        for n, ps in self.hier_terms[name].items():
            terms.setdefault(n, []).extend(ps)
        for n in report["failed"]:
            terms.pop(n, None)
        self.leaf_shapes[name], self.leaf_vias[name], self.leaf_terms[name], self.leaf_ties[name] = shapes, vias, terms, ties
        landed: set[str] = set()
        for p in self.nl[name].ports:
            if p in report["routed"]:
                landed.add(p)
                continue
            for inst in insts:
                hit = [(cp, self.terminal(inst.ref, cp)) for cp, n in zip(self.nl[inst.ref].ports, inst.nets) if n == p]
                hit = [cp for cp, t in hit if t is not None]
                if hit:
                    if self.port_landed(inst.ref, hit[0]):
                        landed.add(p)
                    break
        self.hier_landed[name] = landed

    # ---- macro-level fan-out: escape a port to a reserved pin (issue #107) ------
    @staticmethod
    def _col_blocks(x: float, boxes: list[kdb.Box], keep: int) -> list[kdb.Box]:
        """The boxes a column of half-width ``keep`` (dbu) at ``x`` (um) touches."""
        c0, c1 = dbu(x) - keep, dbu(x) + keep
        return [b for b in boxes if not (b.right < c0 or b.left > c1)]

    def m3_lane_columns(self, box: kdb.Box, m3_boxes: list[kdb.Box], m2_boxes: list[kdb.Box],
                        vias: list[tuple[float, float]],
                        goals_y: float) -> list[tuple[float, float]]:
        """The candidate reserved Metal3 **lane** columns for the slice escape (issue #107): one ``(x, top)`` per
        column of the slice whose Metal3 is free from a top Via2 at ``top`` down to the pin's Via2 at ``goals_y``.
        The bit-line jog structures hang from the top of the window, so a lane's free run starts below them -- as
        low as the lowest Metal3 shape on its column.

        Reserved tracks instead of a maze: nine nets must leave the column path side by side, and a maze routes
        them one ordering at a time -- each takes the lane that is cheapest *then*, and no ordering lets them all
        through. The escape routes each net onto the cheapest still-free of these columns, and a lane whose stub
        failed goes back on the shelf (nothing was committed)."""
        keep3 = dbu(M3_SPACE + M3_W / 2)
        keep2 = dbu(M2_SPACE + M2_W / 2)
        vmin = V2 + V2_SPACE
        y_lo = dbu(goals_y)

        def via2_ok(x: float, y: float) -> bool:
            m2z = kdb.Box(dbu(x) - keep2, dbu(y) - keep2, dbu(x) + keep2, dbu(y) + keep2)
            if any(not (b.right < m2z.left or b.left > m2z.right or b.top < m2z.bottom or b.bottom > m2z.top)
                   for b in m2_boxes):
                return False
            return all(abs(x - vx) >= vmin - 1e-9 or abs(y - vy) >= vmin - 1e-9 for vx, vy in vias)

        cols: list[tuple[float, float]] = []  # (x um, lane top y um): the free Metal3 run is [top, goals_y]
        for i in range((box.width() - 2 * keep3) // STEP + 1):
            x = (box.left + keep3 + i * STEP) * DBU
            blocks = [b for b in self._col_blocks(x, m3_boxes, keep3) if b.top > y_lo]
            top = (min(b.bottom for b in blocks) - keep3 - dbu(M3_W / 2)) if blocks else box.top - dbu(M3_W)
            top = top // STEP * STEP  # the Via2 and its pads sit on the routing lattice
            while top > y_lo + STEP and not via2_ok(x, top * DBU):
                top -= STEP
            if top > y_lo + STEP:
                cols.append((x, round(top * DBU, 3)))
        return cols


    def cell_shapes(self, cell: kdb.Cell, lp, recursive: bool = True) -> kdb.Region:
        rg = kdb.Region(cell.begin_shapes_rec(self.li(lp))) if recursive else kdb.Region(cell.shapes(self.li(lp)))
        return rg.merged()

    @staticmethod
    def boxes_of(rg: kdb.Region, clip: kdb.Box | None = None) -> list[kdb.Box]:
        """Bounding boxes of a region's trapezoid decomposition, optionally clipped (every router obstacle is a box)."""
        if clip is not None:
            rg = rg & kdb.Region(clip)
        return [t.bbox() for poly in rg.merged().each() for t in poly.decompose_trapezoids(kdb.Polygon.TD_simple)]

    def via_centres(self, cell: kdb.Cell, recursive: bool = True) -> list[tuple[float, float]]:
        out = []
        for b in self.boxes_of(self.cell_shapes(cell, L_VIA2, recursive)):
            c = b.center()
            out.append((c.x * DBU, c.y * DBU))
        return out

    def route_slice_escape(self, cell: kdb.Cell) -> None:
        """Bring the nine ``bit_slice`` ports the macro fans out (``SLICE_PORTS``) down to a reserved Metal2 escape
        pin on the slice's own bottom edge, ``SLICE_ESCAPE_H`` below the column path (issue #107).

        The slice is one cell placed 32 times, so the escape is drawn once and the pin of slice *i* sits at
        ``i * 2 * W_CELL + SLICE_PIN_X0 + k * PIN_LANE``: the macro level knows every pin without searching. The
        column-path cells' own nets, the bit-line jogs and lanes and the tie pads are obstacles, and so is every
        shape of the neighbouring slices (the same shapes a slice pitch away), which is what keeps a wire M2.b
        clear of its own mirror image. ``PRE_B`` is the one port with two terminals in the slice (both
        precharges). ``DOUTB`` has one terminal here and none outside the slice, so it is left dangling by design
        (recorded in ``escape_report["bit_slice"]["dangling"]``) rather than routed."""
        pitch = 2 * bc.W_CELL
        x_lo = SLICE_PIN_X0
        x_hi = round(x_lo + ((dbu(pitch - M2_W - M2_SPACE)) // STEP) * STEP * DBU, 3)  # widest span one pitch allows
        assert x_lo + (len(SLICE_PORTS) - 1) * PIN_LANE <= x_hi, "the escape pins do not fit in one slice pitch"
        y_pin = ((self.colpath_bottom - dbu(SLICE_ESCAPE_H)) // STEP) * STEP
        box = kdb.Box(dbu(x_lo - M2_W / 2), y_pin - dbu(M2_W / 2), dbu(x_hi + M2_W / 2), self.colpath_top)
        win = kdb.Box(box.left - KEEP, box.bottom - KEEP, box.right + KEEP, box.top + KEEP)
        goals = {p: (x_lo + k * PIN_LANE, y_pin * DBU) for k, p in enumerate(SLICE_PORTS)}

        by_net: dict[str, list[tuple[float, float, bool]]] = {}
        own_boxes: list[tuple[int, str, kdb.Box]] = []
        blocked: list[tuple[int, kdb.Box]] = []
        vias: list[tuple[float, float]] = []
        own_vias: dict[str, list[tuple[float, float]]] = {}
        for inst in self.nl["bit_slice"].insts:
            off = self.place_of["bit_slice"].get(inst.name)
            if off is None or inst.ref not in COLPATH_CELLS:
                continue
            dx, dy = off
            port_net = dict(zip(self.nl[inst.ref].ports, inst.nets))
            for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                if n in goals:
                    t = self.terminal(inst.ref, port)
                    assert t is not None, (inst.name, port)
                    by_net.setdefault(n, []).append((t[0] + dx * DBU, t[1] + dy * DBU,
                                                     self.port_landed(inst.ref, port)))
            for n, regs in self.leaf_shapes.get(inst.ref, {}).items():
                key = port_net.get(n, f"{inst.name}/{n}")
                for l in (0, 1):
                    own_boxes += [(l, key, b) for b in self.boxes_of(regs[l].moved(dx, dy), win)]
            # body ties (``leaf_ties``) are Metal1 pads: Metal2 and Metal3 pass over them, so they are no
            # obstacle to the escape (a Via1 would be, but the maze never places one -- landings happen on
            # terminals only)
            for v in self.leaf_vias.get(inst.ref, ()):
                key = port_net.get(v["net"], f"{inst.name}/{v['net']}")
                pt = (v["x"] + dx * DBU, v["y"] + dy * DBU)
                vias.append(pt)
                own_vias.setdefault(key, []).append(pt)
        for l, lp in ((0, L_METAL2), (1, L_METAL3)):  # the bit-line jogs, lanes and pads, drawn in the slice itself
            blocked += [(l, b) for b in self.boxes_of(self.cell_shapes(cell, lp, recursive=False), win)]
            flat = self.cell_shapes(cell, lp)
            for d in (-dbu(pitch), dbu(pitch)):  # ... and everything in the neighbouring slices
                blocked += [(l, b) for b in self.boxes_of(flat.moved(d, 0), win)]
        vias += self.via_centres(cell, recursive=False)
        vias += [(x + s * pitch, y) for x, y in list(vias) for s in (-1, 1)]

        cols = self.m3_lane_columns(box,
                                    [b for l, _, b in own_boxes if l == 1] + [b for l, b in blocked if l == 1],
                                    [b for l, _, b in own_boxes if l == 0] + [b for l, b in blocked if l == 0],
                                    vias, y_pin * DBU)
        ids = {n: k + 1 for k, n in enumerate(SLICE_PORTS)}
        mz = MazeRouter(box.left, box.bottom, box.right, box.top)
        for l, b in blocked:
            mz.block(l, b.left * DBU, b.bottom * DBU, b.right * DBU, b.top * DBU)
        for l, n, b in own_boxes:  # another net's shape is an obstacle; two nets over one node block it for both
            mz._mark(l, b.left, b.bottom, b.right, b.top, ids.get(n, -1))
        for l, n, b in own_boxes:  # ... and a net's own shape costs it no geometry, so it may route through it
            if n in ids:
                mz.own(l, b.left * DBU, b.bottom * DBU, b.right * DBU, b.top * DBU, ids[n])
        near = dbu(V2 + V2_SPACE) // STEP
        for vx, vy in vias:
            vi, vj = mz.node(vx, vy)
            mz.via_near.update((vi + a, vj + b) for a in range(-near, near + 1) for b in range(-near, near + 1))
        pins: dict[str, tuple[float, float, int]] = {}
        report = {"routed": {}, "failed": [], "pins": pins}
        # Candidate lanes are *assigned* highest-terminal first -- the top cells' nets are the ones only a tall
        # lane can serve, so they claim the tall columns before a low net's short hop takes one -- and then
        # *routed* lowest-terminal first, so the bottom cells' short hops commit before longer descents can wall
        # them off (a committed wire keeps KEEP around itself). A net tries its candidates shortest-stub first
        # and commits the first one that routes; a failed attempt commits nothing, so its lane goes back on the
        # shelf and the net falls through to its next candidate, then to whatever is still unclaimed.
        claimed: list[float] = []
        assigned: dict[str, list[tuple[float, float]]] = {}
        for n in sorted(SLICE_PORTS, key=lambda k: (by_net[k][0][1], by_net[k][0][0], k), reverse=True):
            tx, ty = by_net[n][0][:2]
            cands = sorted((c for c in cols if all(abs(c[0] - u) >= PIN_LANE - 1e-9 for u in claimed)),
                           key=lambda c: (abs(c[0] - tx) + abs(c[1] - ty), c[0], c[1]))
            assert cands, f"no Metal3 lane for the {n} escape"
            assigned[n] = cands
            claimed.append(cands[0][0])
        first = {n: cands[0][0] for n, cands in assigned.items()}
        used: list[float] = []  # lane x of every routed stub: lanes are PIN_LANE apart
        for n in sorted(SLICE_PORTS, key=lambda k: (by_net[k][0][1], by_net[k][0][0], k), reverse=True):
            # same order as the assignment: the top cells' nets route into a clean field (their tall lanes are
            # the scarce ones), and a net that gets walled off backtracks through its candidate lanes
            tx, ty = by_net[n][0][:2]
            terms = by_net.get(n, ())
            for x, y, landed in terms:
                if not landed:
                    ti, tj = mz.node(x, y)
                    self.m1_via1(cell, ti * STEP * DBU, tj * STEP * DBU)
            nodes = [mz.node(x, y) for x, y, _ in terms]
            # a Via2 may land on the net's own leaf Via2 (the vias merge into one shape), so its own Via2
            # nodes do not keep the escape's Via2s out
            own_via_nodes = {mz.node(x, y) for x, y in own_vias.get(n, ())}
            saved = own_via_nodes & mz.via_near
            mz.via_near -= own_via_nodes
            # backtracking may use any column that no routed stub and no *other* net's reserved lane occupies
            reserved = {first[n2] for n2 in SLICE_PORTS if n2 != n}
            leftover = [c for c in cols if all(abs(c[0] - u) >= PIN_LANE - 1e-9 for u in used) and c[0] not in reserved]
            cands = sorted(set(assigned[n]) | set(leftover),
                           key=lambda c: (abs(c[0] - tx) + abs(c[1] - ty), c[0], c[1]))
            cands = [c for c in cands if all(abs(c[0] - u) >= PIN_LANE - 1e-9 for u in used)]
            for lx, ltop in cands:
                top = mz.node(lx, ltop)
                nodes_top = nodes + [top]
                for t in nodes_top:  # the terminal pads and the lane's top Via2 pad are this net's own
                    mz.own(0, t[0] * STEP * DBU - M2_W / 2, t[1] * STEP * DBU - M2_W / 2,
                           t[0] * STEP * DBU + M2_W / 2, t[1] * STEP * DBU + M2_W / 2, ids[n])
                if not mz.route_net(ids[n], sorted(set(nodes_top)), m3_arrive={top}):
                    continue
                own = {l: kdb.Region() for l in (0, 1)}
                for l, nid, b in own_boxes:
                    if nid == n:
                        own[l].insert(b)
                self.draw_net(cell, mz, ids[n], nodes_top, own)
                # the lane: Via2 on the stub, straight Metal3 down, Via2 on the pin the macro level meets
                self.stack2(cell, top[0] * STEP * DBU, top[1] * STEP * DBU)
                pin = (lx, y_pin * DBU)
                self.seg(cell, L_METAL3, M3_W, lx, top[1] * STEP * DBU, *pin)
                self.stack2(cell, *pin)
                for vx, vy in (mz.node(*pin), top):
                    vi, vj = vx, vj
                    mz.via_near.update((vi + a, vj + b) for a in range(-near, near + 1)
                                       for b in range(-near, near + 1))
                used.append(lx)
                report["routed"][n] = len(terms) + 1
                pins[n] = (round(lx, 3), round(y_pin * DBU, 3), 0)  # Metal2: the macro runs on down
                break
            mz.via_near |= saved
            if n not in report["routed"]:
                report["failed"].append(n)
                print(f"STUB FAIL {n}: terms={[(x, y) for x, y, _ in terms]} cands={cands[:6]} (of {len(cands)})")
                print(f"  own vias: {sorted(own_vias.get(n, []))}")
                i0, j0 = mz.node(tx, ty)
                for l, tag in ((0, "M2"), (1, "M3")):
                    print(f"  {tag}: rows y=-53.8..-56.2, cols x={((i0-4)*0.05):.2f}..{((i0+42)*0.05):.2f}")
                    for jj in range(mz.node(tx, -53.8)[1], mz.node(tx, -56.2)[1] - 1, -1):
                        row = ""
                        for ii in range(i0 - 4, i0 + 43):
                            o = mz.owner[l][ii - mz.i0][jj - mz.j0]
                            row += "." if o == 0 else ("#" if o == -1 else chr(ord('A') + o - 1))
                        vn = any((ii, jj) in mz.via_near for ii in range(i0 - 4, i0 + 43))
                        print(f"  {jj * 0.05:8.2f} {row}{'V' if vn else ''}")
        report["dangling"] = sorted(n for n, v in self.slice_port_terms().items()
                                    if len(v) == 1 and n not in goals)
        assert not report["failed"], f"bit_slice escape failed for {report['failed']}"
        self.escape_pins["bit_slice"] = pins
        self.escape_report["bit_slice"] = report

    def slice_port_terms(self) -> dict[str, list[tuple[str, str]]]:
        """``{net: [(instance, port)]}`` for every non-supply net of ``bit_slice`` that is a port of the slice."""
        ports = set(self.nl["bit_slice"].ports)
        out: dict[str, list[tuple[str, str]]] = {}
        for inst in self.nl["bit_slice"].insts:
            if inst.ref not in COLPATH_CELLS:
                continue
            for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                if n in ports and not excluded_net(n):
                    out.setdefault(n, []).append((inst.name, port))
        return out

    # ---- macro-level fan-out: the channel between the blocks (issue #107) --------
    def top_port_map(self) -> dict[str, dict[str, str]]:
        """``{block: {macro net: the block's port wired to it}}``, read from ``.subckt macro``."""
        out: dict[str, dict[str, str]] = {}
        for inst in self.nl[TOP].insts:
            if inst.ref in self.nl and inst.ref != "bit_slice":
                out[inst.ref] = {n: p for p, n in zip(self.nl[inst.ref].ports, inst.nets)}
        return out

    def inter_block_nets(self) -> dict[str, list[tuple[str, str]]]:
        """``{macro net: [(top-level instance, its port)]}`` for every net that joins two or more placed blocks or
        slices, supply / bit-line / wordline nets excluded: exactly the set the macro-level fan-out must wire.

        A net with a single terminal here is either a macro port (one block drives or reads it, so the pin
        connection of issue #108 is all it needs) or dangling by design (``DOUTB[i]``)."""
        out: dict[str, list[tuple[str, str]]] = {}
        for inst in self.nl[TOP].insts:
            if inst.ref not in self.nl:
                continue
            for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                if not excluded_net(n):
                    out.setdefault(n, []).append((inst.name, port))
        return {n: v for n, v in sorted(out.items()) if len(v) >= 2}

    def slice_internal_nets(self) -> dict[str, int]:
        """``{net: terminal count}`` for the nets between ``bit_slice``'s own child cells that are *not* ports of
        the slice: ``BLM`` and ``BLBM``, between the column mux, the sense amplifier and the write driver.

        They are inside the slice, so the macro-level fan-out does not reach them, and no child of #95 claims
        them either -- disclosed here and in the record rather than left unmentioned."""
        ports = set(self.nl["bit_slice"].ports)
        out: dict[str, int] = {}
        for inst in self.nl["bit_slice"].insts:
            if inst.ref not in COLPATH_CELLS:
                continue
            for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                if n not in ports and not excluded_net(n):
                    out[n] = out.get(n, 0) + 1
        return {n: c for n, c in sorted(out.items()) if c >= 2}

    def trunk_nets(self) -> list[str]:
        """The macro nets that need a horizontal Metal3 trunk in the fan-out channel, in track order: the global
        control nets first (32 branches each, so their drops are the shortest), then the per-slice data nets."""
        return (list(GLOBAL_NETS) + ["CLK"]
                + [f"DL[{i}]" for i in range(SLICES)] + [f"DOUT[{i}]" for i in range(SLICES)])

    def channel_h(self) -> float:
        """Height (um) of the fan-out channel: one Metal3 track per trunk net, clear of the slice pins and the
        latch blocks by ``CHANNEL_MARGIN``."""
        return round(2 * CHANNEL_MARGIN + len(self.trunk_nets()) * TRACK_PITCH, 3)

    def escape_pin(self, block: str, net: str, port_map: dict[str, dict[str, str]]) -> tuple[float, float, int]:
        """A block's escape pin for a macro net, in the macro's frame."""
        port = port_map[block][net]
        x, y, l = self.escape_pins[block][port]
        dx, dy = self.place_of[TOP][block]
        return round(x + dx * DBU, 3), round(y + dy * DBU, 3), l

    def fanout_probes(self) -> dict[str, list[tuple[float, float]]]:
        """``{macro net: [(x, y) Metal1 device terminal in the macro's frame]}``, for every inter-block net.

        These are the points the fan-out has to join: a transistor terminal in each block and, for a net that
        reaches the array, in every one of the 32 slices. The connectivity test probes *these*, not the escape
        pins, so a route that stops short inside a block cannot pass it."""
        sl_w = dbu(2 * bc.W_CELL)
        out: dict[str, list[tuple[float, float]]] = {}

        def add(net: str, t: tuple[float, float], dx: int, dy: int) -> None:
            out.setdefault(net, []).append((round(t[0] + dx * DBU, 3), round(t[1] + dy * DBU, 3)))

        for inst in self.nl[TOP].insts:
            if inst.ref not in self.nl:
                continue
            m = re.fullmatch(r"XS\[(\d+)\]", inst.name)
            if m:
                sx = int(m.group(1)) * sl_w
                port_net = dict(zip(self.nl[inst.ref].ports, inst.nets))
                for ci in self.nl["bit_slice"].insts:
                    off = self.place_of["bit_slice"].get(ci.name)
                    if off is None or ci.ref not in COLPATH_CELLS:
                        continue
                    for port, n in zip(self.nl[ci.ref].ports, ci.nets):
                        t = self.terminal(ci.ref, port) if n in port_net else None
                        if t is not None and not excluded_net(port_net[n]):
                            add(port_net[n], t, off[0] + sx, off[1])
            else:
                dx, dy = self.place_of[TOP][inst.ref]
                for port, n in zip(self.nl[inst.ref].ports, inst.nets):
                    t = self.terminal(inst.ref, port) if not excluded_net(n) else None
                    if t is not None:
                        add(n, t, dx, dy)
        wired = set(self.fanout_report["nets"])
        return {n: sorted(set(v)) for n, v in sorted(out.items()) if n in wired}

    def m3_run(self, cell: kdb.Cell, x0: float, x1: float, y: float) -> None:
        if abs(x1 - x0) > 1e-9:
            self.seg(cell, L_METAL3, M3_W, x0, y, x1, y)

    def m2_run(self, cell: kdb.Cell, x: float, y0: float, y1: float) -> None:
        if abs(y1 - y0) > 1e-9:
            self.seg(cell, L_METAL2, M2_W, x, y0, x, y1)

    def stack2(self, cell: kdb.Cell, x: float, y: float) -> None:
        """Via2 with its Metal2 and Metal3 landing pads (as ``draw_shapes`` draws the router's own)."""
        self.via_pad(cell, L_VIA2, x, y)
        self.rect(cell, L_METAL2, x, y, M2_W, M2_W)
        self.rect(cell, L_METAL3, x, y, M3_W, M3_W)

    def route_fanout(self, top: kdb.Cell) -> None:
        """Wire the macro's inter-block nets: the global control fan-out to all 32 slices, the latched address and
        control bits across the left block, and the per-slice ``DL`` / ``DOUT`` (issue #107).

        Every terminal is already on an escape pin (``escape_pins``: one per block port, and nine per slice at a
        reserved offset in the slice pitch), so this is a channel router with reserved tracks, not a maze --
        deterministic, and checkable by construction:

        * **channel**: one horizontal Metal3 **trunk** per net of ``trunk_nets`` in the band between the slices'
          escape pins and the data latch, ``TRACK_PITCH`` apart (so M3.b between trunks, and M3.b between a trunk
          and another trunk's Via2 pad).
        * **lanes**: one vertical Metal2 lane per net and side, ``PIN_LANE`` apart (M2.b between lanes and between
          a lane and another lane's Via2 pad). The *west* lanes sit left of the address latch, where the column
          from the channel up to the row decoder is clear; the *gap* lanes sit in the wordline fan-out gap below
          the array, which no wordline shape reaches (they are all above y = 0).
        * **decoder approach**: one horizontal Metal3 track per net in the ``DECODER_APPROACH`` band between the
          control block's top and the row decoder, which spans the whole decoder width.

        A lane and a trunk cross on different layers, which is what lets 72 nets share the channel; the only vias
        are where a net turns, and each is on its own lane or its own trunk.

        ``DOUTB[i]`` is not wired: its only terminal in the whole macro is the sense amplifier's ``OUTB`` inside
        slice *i* (``flat_nets``), so it is dangling by design, and recorded as such."""
        port_map = self.top_port_map()
        sl_w = 2 * bc.W_CELL
        sp = self.escape_pins["bit_slice"]
        slice_pin_y = sp[SLICE_PORTS[0]][1]
        assert all(v[1] == slice_pin_y and v[2] == 0 for v in sp.values()), "the slice pins must share one Metal2 row"

        # ---- tracks and lanes, all from the placement ----
        order = self.trunk_nets()
        y0 = snap(slice_pin_y - CHANNEL_MARGIN)
        trunk = {n: snap(y0 - k * TRACK_PITCH) for k, n in enumerate(order)}
        ad = self.cells["addr_latch"].bbox().moved(*self.place_of[TOP]["addr_latch"])
        rd = self.cells["row_decoder"].bbox().moved(*self.place_of[TOP]["row_decoder"])
        west_nets = (list(GLOBAL_NETS) + ["CLK", "WLEN", "CENL", "GWENL", "WENL"]
                     + [f"AL[{k}]" for k in range(8)])
        x_west0 = snap(ad.left * DBU - LANE_CLEAR)
        west = {n: snap(x_west0 - k * PIN_LANE) for k, n in enumerate(west_nets)}
        gap_pins = ([("data_latch", "CLK")] + [("data_latch", f"DL[{i}]") for i in range(SLICES)]
                    + [("out_latch", "SAE")] + [("out_latch", f"DOUT[{i}]") for i in range(SLICES)])
        x_gap0 = snap(-LANE_CLEAR)
        gap = {k: snap(x_gap0 - i * PIN_LANE) for i, k in enumerate(gap_pins)}
        dec_nets = ["WLEN"] + [f"AL[{k}]" for k in range(1, 8)]
        ya0 = snap(rd.bottom * DBU - CHANNEL_MARGIN)
        approach = {n: snap(ya0 - k * TRACK_PITCH) for k, n in enumerate(dec_nets)}
        assert min(approach.values()) - M3_W / 2 - M3_SPACE >= self.cells["control"].bbox().moved(
            *self.place_of[TOP]["control"]).top * DBU, "the decoder approach band is too thin for its tracks"
        assert min(west.values()) > rd.left * DBU, "the west lanes run off the macro's left edge"
        assert min(gap.values()) - PIN_LANE > -WL_FANOUT_GAP, "the gap lanes run into the row decoder's column"

        # ---- the global control nets: the control block to all 32 slices ----
        for n in GLOBAL_NETS:
            yt, lx = trunk[n], west[n]
            px, py, pl = self.escape_pin("control", n, port_map)
            assert pl == 1, (n, "control's escape pin is not on Metal3")
            self.m3_run(top, lx, px, py)
            self.stack2(top, lx, py)
            self.m2_run(top, lx, py, yt)
            self.stack2(top, lx, yt)
            xs = [snap(i * sl_w + sp[n][0]) for i in range(SLICES)]
            x_end = max(xs)
            if n == "SAE":  # the output latch's enable is the same net
                ox, oy, _ = self.escape_pin("out_latch", n, port_map)
                gx = gap[("out_latch", n)]
                self.m3_run(top, gx, ox, oy)
                self.stack2(top, gx, oy)
                self.m2_run(top, gx, oy, yt)
                self.stack2(top, gx, yt)
            self.m3_run(top, lx, x_end, yt)
            for x in xs:
                self.stack2(top, x, yt)
                self.m2_run(top, x, yt, slice_pin_y)

        # ---- CLK: the address latch, the control block and the data latch ----
        yt, lx = trunk["CLK"], west["CLK"]
        ys = []
        for blk in ("addr_latch", "control"):
            px, py, _ = self.escape_pin(blk, "CLK", port_map)
            self.m3_run(top, lx, px, py)
            self.stack2(top, lx, py)
            ys.append(py)
        self.m2_run(top, lx, min(ys + [yt]), max(ys + [yt]))
        self.stack2(top, lx, yt)
        gx = gap[("data_latch", "CLK")]
        px, py, _ = self.escape_pin("data_latch", "CLK", port_map)
        self.m3_run(top, gx, px, py)
        self.stack2(top, gx, py)
        self.m2_run(top, gx, py, yt)
        self.stack2(top, gx, yt)
        self.m3_run(top, lx, gx, yt)

        # ---- the address latch to the control block: CENL, GWENL, WENL, AL[0] ----
        for n in ("CENL", "GWENL", "WENL", "AL[0]"):
            lx = west[n]
            ax, ay, _ = self.escape_pin("addr_latch", n, port_map)
            cx, cy, _ = self.escape_pin("control", n, port_map)
            self.m3_run(top, lx, ax, ay)
            self.m3_run(top, lx, cx, cy)
            self.stack2(top, lx, ay)
            self.stack2(top, lx, cy)
            self.m2_run(top, lx, min(ay, cy), max(ay, cy))

        # ---- to the row decoder: AL[7:1] from the address latch, WLEN from the control block ----
        for n in dec_nets:
            lx, ya = west[n], approach[n]
            src = "control" if n == "WLEN" else "addr_latch"
            sx, sy, _ = self.escape_pin(src, n, port_map)
            dx_, dy_, dl = self.escape_pin("row_decoder", n, port_map)
            assert dl == 0, (n, "the row decoder's escape pin is not on Metal2")
            self.m3_run(top, lx, sx, sy)
            self.stack2(top, lx, sy)
            self.m2_run(top, lx, sy, ya)
            self.stack2(top, lx, ya)
            self.m3_run(top, lx, dx_, ya)
            self.stack2(top, dx_, ya)
            self.m2_run(top, dx_, ya, dy_)

        # ---- per-slice write data and read data ----
        for i in range(SLICES):
            for n, blk, sport in ((f"DL[{i}]", "data_latch", "DIN"), (f"DOUT[{i}]", "out_latch", "DOUT")):
                yt, gx = trunk[n], gap[(blk, n)]
                px, py, _ = self.escape_pin(blk, n, port_map)
                sx = snap(i * sl_w + sp[sport][0])
                self.m3_run(top, gx, px, py)
                self.stack2(top, gx, py)
                self.m2_run(top, gx, py, yt)
                self.stack2(top, gx, yt)
                self.m3_run(top, gx, sx, yt)
                self.stack2(top, sx, yt)
                self.m2_run(top, sx, yt, slice_pin_y)

        wired = set(order) | set(west_nets)
        assert wired == set(self.inter_block_nets()), \
            f"fan-out misses or invents a net: {wired ^ set(self.inter_block_nets())}"
        self.fanout_report = {
            "nets": sorted(wired),
            "trunks": {n: trunk[n] for n in order},
            "west_lanes": {n: west[n] for n in west_nets},
            "gap_lanes": {f"{b}.{n}": v for (b, n), v in gap.items()},
            "decoder_approach": {n: approach[n] for n in dec_nets},
            "slice_pins": {n: sp[n][0] for n in SLICE_PORTS},
            "slice_pin_y": slice_pin_y,
            "channel_h": self.channel_h(),
            "dangling_by_design": [f"DOUTB[{i}]" for i in range(SLICES)],
            "slice_internal_not_drawn": self.slice_internal_nets(),
        }

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
        # the column-path cells' terminal landings (issue #104) are obstacles for every bit-line jog
        for inst in self.nl["bit_slice"].insts:
            off = self.place_of["bit_slice"].get(inst.name)
            if off is not None and inst.ref in COLPATH_CELLS:
                sub = kdb.Region(self.cells[inst.ref].begin_shapes_rec(self.li(L_METAL2)))
                supply += sub.transformed(kdb.Trans(off[0], off[1]))
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
            for jog in [WL_STUB_DX, 0.0] + [round(0.2 * i, 3) for i in range(2, 16)]:
                sx = snap(tx + jog)
                parts = [kdb.DBox(sx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, yt + M2_W / 2)]
                if jog:
                    parts.append(kdb.DBox(tx - M2_W / 2, ty - M2_W / 2, sx + M2_W / 2, ty + M2_W / 2))
                grown = [pt.enlarged(M2_SPACE, M2_SPACE) for pt in parts]
                if not any(gr.overlaps(tp) for gr in grown for tp in tie_pads):
                    break
            else:
                raise AssertionError(f"no tie-clear Metal2 stub for wordline {r}")
            assert jog == WL_STUB_DX, (r, jog)  # ``wl_reserve`` kept this stub's room clear in the decoder cells
            if jog:
                self.seg(top, L_METAL2, M2_W, tx, ty, sx, ty)
            self.seg(top, L_METAL2, M2_W, sx, ty, sx, yt)
            self.via_pad(top, L_VIA2, sx, yt)
            self.seg(top, L_METAL3, M3_W, sx, yt, xl, yt)
            if abs(yt - ya) < V2 + V2_SPACE - 1e-6:
                # the track is less than a Via2 pitch from the wordline's y: the lane's two Via2 would be V2.b apart,
                # so the two Metal3 runs are joined by Metal3 at the lane's x instead
                self.seg(top, L_METAL3, M3_W, xl, yt, xl, ya)
            else:
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
            # the offsets are whole STEPs, so a column-path cell's routing lattice is the slice's: the Via1
            # landing the cell drew on a terminal and the one the slice's escape would draw are then the same
            # square, not two 0.03 um apart (issue #107; ``pack(lattice=True)`` does this for the latch blocks)
            dx = -(-(dbu(SLICE_MARGIN) - bb.left) // STEP) * STEP
            dy = (y - bb.top) // STEP * STEP
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(cell, ch, dx, dy)
            self.place_of["bit_slice"][inst.name] = (dx, dy)
            y = y - bb.height() - dbu(PACK_GAP)
        self.colpath_bottom = y + dbu(PACK_GAP)
        assert arr_h > 0
        self.route_bitlines(cell)
        # the column-path cells route around the jogs (a cell is shared by the slice's instances of it)
        jogs = [kdb.Region(cell.shapes(self.li(lp))) for lp in (L_METAL2, L_METAL3)]  # Metal2 jogs, Metal3 lanes
        for ref in COLPATH_CELLS:
            extra = []
            for inst in self.nl["bit_slice"].insts:
                off = self.place_of["bit_slice"].get(inst.name)
                if inst.ref == ref and off is not None:
                    cb = self.cells[ref].bbox().moved(off[0], off[1]).enlarged(dbu(1.0), dbu(1.0))
                    for layer, rg in enumerate(jogs):
                        for poly in (rg & kdb.Region(cb)).each():
                            extra.append((layer, poly.bbox().moved(-off[0], -off[1])))
            self.route_leaf(ref, self.cells[ref], extra, phase="wires")
        self.route_slice_escape(cell)  # the nine ports the macro fans out, to pins on the slice's bottom edge (#107)
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
            dx = right - (dbu(DECODER_CLEAR) if ref != "row_decoder" else 0) - bb.right
            dy = by - bb.bottom
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(top, ch, dx, dy)
            regions.append(bb.moved(dx, dy))
            self.place_of.setdefault(TOP, {})[ref] = (dx, dy)
            # the row decoder sits DECODER_APPROACH above the control block: the band its escaped address and
            # WLEN nets reach their lanes across (issue #107)
            by += bb.height() + dbu(DECODER_APPROACH if ref == "control" else BLOCK_GAP)

        # bottom block: data latch and output latch under the column path, the fan-out channel between
        y = col_bottom - dbu(self.channel_h())
        for ref in ("data_latch", "out_latch"):
            ch = self.build(ref)
            bb = ch.bbox()
            dx = 0 - bb.left
            dy = y - bb.top
            assert dx % GRID == 0 and dy % GRID == 0
            self.place(top, ch, dx, dy)
            regions.append(bb.moved(dx, dy))
            self.place_of.setdefault(TOP, {})[ref] = (dx, dy)
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
        self.route_fanout(top)  # the inter-block signal nets (issue #107)

        # pins on the content bounding box
        bb = top.bbox()
        pins = self.pins(top, bb, ports, arr_w)
        self.pin_list = pins
        before = top.bbox()
        self.pre_rail_bb = before
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

    def notch_free(self, obs: Obstacles, net: str, x: float, y: float, parts: list[kdb.DBox]) -> bool:
        """Whether ``parts`` add no sub-M2.b gap or notch to the Metal2 of their own net around (x, y).

        ``Obstacles.clear`` tests one part against one shape at a time and lets two shapes of a net merge, which is
        right -- but a run that leaves a tie's pad and comes back under it merges *and* leaves a re-entrant corner
        narrower than M2.b, and that is a violation just as a gap is. Compared against the same check without
        ``parts``, so a flaw that is already there is not blamed on them."""
        win = kdb.DBox(x - 3.0, y - 3.0, x + 3.0, y + 3.0)
        mine = kdb.Region()
        for c in obs.cells_of(win):
            for n, b in obs.m2.get(c, ()):
                if n == net and win.overlaps(b):
                    mine.insert(kdb.Box(dbu(b.left), dbu(b.bottom), dbu(b.right), dbu(b.top)))
        added = kdb.Region([kdb.Box(dbu(pt.left), dbu(pt.bottom), dbu(pt.right), dbu(pt.top)) for pt in parts])

        def flaws(rg: kdb.Region) -> int:
            rg = rg.merged()
            return rg.notch_check(dbu(M2_SPACE)).count() + rg.space_check(dbu(M2_SPACE)).count()

        return flaws(mine + added) <= flaws(mine)

    def rails(self, top: kdb.Cell, regions: list[kdb.Box], arr_w: int) -> None:
        """Supply rails. Metal4 lanes run in free tracks, Metal5 trunks sit right of the array; nothing but
        Metal4 crosses the wordline fan-out gap, whose Metal2/Metal3 lanes and tracks belong to the signals."""
        rc = self.layout.create_cell("rails")
        top.insert(kdb.CellInstArray(rc.cell_index(), kdb.Trans()))
        self.rails_top = top
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
        # Metal2 / Metal3 obstacles in a spatial hash: [(net-or-None, DBox)]. Signals are net None.
        obs = Obstacles()

        for ob in self.signal_boxes(top, L_METAL2, tie_pads):
            obs.add(None, ob)
        for ob in self.signal_boxes(top, L_METAL3, []):
            obs.add_m3(ob)
        for t, tp in zip(ties, tie_pads):
            obs.add(t["net"], tp)

        # Metal4 lanes and strap pads: per region, per net (see lane_positions)
        lanes, pads_of = lane_positions(regions, trunk_x, seam_pads)
        self.tie_wiring: list[dict] = []
        state = RailState(rc)

        def tie_candidates(net: str, ri: int, x: float, y: float):
            """(ly, xs, dx) candidates for a tie's stub: its net's lanes nearest-first (eight), the sideways offset
            nearest-first on a 0.2 um grid within +-6 um; the guards shared by the Metal2 and Metal3 paths (the lane
            pad stays inside the macro; the Via2 keeps V2.b / M3.b to the other Via2s on the same lane) applied once."""
            for ly in sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]:
                for dx in sorted([round(0.2 * i, 3) for i in range(-30, 31)], key=abs):
                    xs = round(x + dx, 3)
                    if xs - hp < self.pre_rail_bb.left * DBU:
                        continue  # the lane pad stays inside the macro (rails extend it to the right only)
                    # Via2 (and its Metal3 pad) keep V2.b / M3.b to the other Via2 on the same lane
                    if any(0 < abs(xs - ox) < VIA_PAD + M3_SPACE for ox in state.via2_at.get((ri, net, ly), ())):
                        continue
                    yield ly, xs, dx

        for t in ties:
            net, x, y = t["net"], t["x"], t["y"]
            ri = next((i for i, rb in enumerate(regions) if rb.contains(kdb.Point(dbu(x), dbu(y)))), None)
            assert ri is not None, (net, x, y, [str(r) for r in regions])
            # candidates: nearest lanes first, vertical stub straight up/down from the pad, else jogged
            # sideways at the tie's own height (Metal2 horizontal, then vertical)
            chosen = None
            hw = STUB_W / 2
            def m2_parts(ly: float, xs: float) -> list[kdb.DBox] | None:
                """The Metal2 shapes of a stub from the tie pad (x, y) to a Via3 at (xs, ly), or None if neither
                variant stays clear of the wordline gap and this net's own Metal2: vertical first (up/down from
                the pad, then along the lane's height), else sideways first."""
                lo, hi = min(y, ly), max(y, ly)
                for variant in (0, 1):
                    if variant == 0:  # horizontal at the tie's height, vertical at xs
                        parts = [kdb.DBox(xs - hw, lo - hp, xs + hw, hi + hp)]
                        if xs != x:
                            parts.append(kdb.DBox(min(x, xs) - hp, y - hw, max(x, xs) + hp, y + hw))
                    else:  # vertical at the tie's x, horizontal at the lane height
                        if xs == x or abs(ly - y) < hp + M2_SPACE + STUB_W / 2 + 0.01:
                            continue
                        parts = [kdb.DBox(x - hw, lo - hp, x + hw, hi + hp),
                                 kdb.DBox(min(x, xs) - hp, ly - hw, max(x, xs) + hp, ly + hw)]
                    if any(in_wl_gap(pt.left, pt.right) for pt in parts + [kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)]):
                        continue  # nothing below Metal4 in the wordline gap
                    if all(obs.clear(net, pt) for pt in parts):
                        return parts
                return None

            def m2_search(ly: float) -> tuple[float, float, list[kdb.DBox]] | None:
                """The nearest-clear Metal2 stub from this tie's pad to the lane at ``ly``, or None: sideways
                offsets nearest-first on a 0.2 um grid; a stub beside its own pad must clear it by M2.b
                (otherwise the joint is a notch or a sliver), and the Via2 (and its Metal3 pad) keep V2.b /
                M3.b to the other Via2s on the same lane."""
                for dx in sorted([round(0.2 * i, 3) for i in range(-30, 31)], key=abs):
                    if dx and abs(dx) < hp + M2_SPACE + STUB_W / 2 + 0.01:
                        continue
                    xs = round(x + dx, 3)
                    if xs - hp < self.pre_rail_bb.left * DBU:
                        continue  # the lane pad stays inside the macro (rails extend it to the right only)
                    if any(0 < abs(xs - ox) < VIA_PAD + M3_SPACE for ox in state.via2_at.get((ri, net, ly), ())):
                        continue
                    if not obs.clear3(kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)):
                        continue
                    parts = m2_parts(ly, xs)
                    if parts:
                        return ly, xs, parts
                return None

            def free_lane(ly: float) -> bool:
                """Whether a new Metal4 lane may sit at ``ly`` in this region: inside it with the same 0.3 um
                margin, clear of the strap pads of its net, and LANE_W + M3.b from every lane already there."""
                rb = regions[ri]
                if not (rb.bottom * DBU + 0.3 <= ly <= rb.top * DBU - 0.3):
                    return False
                if any(abs(ly - o) < LANE_W / 2 + hp + M3_SPACE for o in pads_of.get((ri, net), ())):
                    return False
                return all(abs(ly - o) >= LANE_W + M3_SPACE
                           for n2 in trunk_x for o in lanes[(ri, n2)])

            for ly in sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]:
                chosen = m2_search(ly)
                if chosen:
                    break
            if chosen is None:
                chosen3 = None
                for ly, xs, dx in tie_candidates(net, ri, x, y):
                    lo, hi = min(y, ly), max(y, ly)
                    if dx and (abs(dx) < hp + M3_SPACE + STUB_W / 2 + 0.01 or abs(ly - y) < hp + M3_SPACE + STUB_W / 2 + 0.01):
                        continue  # a sideways run keeps M3.b to its own pads (otherwise a sliver between them)
                    parts = [kdb.DBox(x - hp, y - hp, x + hp, y + hp), kdb.DBox(xs - hw, lo - hw, xs + hw, hi + hw),
                             kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)]
                    if dx:
                        parts.append(kdb.DBox(min(x, xs) - hw, y - hw, max(x, xs) + hw, y + hw))
                    if any(in_wl_gap(pt.left, pt.right) for pt in parts):
                        continue  # nothing below Metal4 in the wordline gap
                    if all(obs.clear3(pt) for pt in parts):
                        chosen3 = (ly, xs, parts)
                        break
                if chosen3:
                    ly, xs, parts = chosen3
                    for pt in parts:
                        self.box(rc, L_METAL3, pt.left, pt.bottom, pt.right, pt.top)
                        obs.add_m3(pt)
                    via(None, L_VIA2, L_METAL3, x, y)
                    via(None, L_VIA3, L_METAL4, xs, ly)
                    state.via2_at.setdefault((ri, net, ly), []).append(xs)
                    state.used.setdefault((ri, net), set()).add(ly)
                    self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": xs, "region": ri,
                                            "stub": "Metal3"})
                    continue
                if self.tie_maze(net, x, y, ri, rb_x=(regions[ri].left * DBU, regions[ri].right * DBU), lanes=lanes[(ri, net)],
                                 obs=obs, state=state):
                    continue
                # Still nothing: give the tie a Metal4 lane of its own, at the nearest clear height. A lane is
                # Metal4 and is only drawn where it serves a tie, so an extra one costs its own clearance and
                # nothing else. This runs after every path above, so it only ever changes a tie that would
                # otherwise fail outright -- which issue #107's escapes made happen in the latch blocks, where
                # the Metal2 and Metal3 around a few ties no longer reach the 4 um lane grid.
                for d in [round(0.1 * k, 3) for k in range(1, int(10 * RAIL_LANE_PITCH))]:
                    for ly in (round(y + d, 3), round(y - d, 3)):
                        if free_lane(ly):
                            chosen = m2_search(ly)
                            if chosen and not self.notch_free(obs, net, x, y, chosen[2]):
                                chosen = None
                            if chosen:
                                lanes[(ri, net)].append(ly)
                                break
                    if chosen:
                        break
            if chosen is None:
                raise AssertionError(f"no clear Metal2 stub for {net} tie at ({x}, {y}); lanes {sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]}, region {ri}")
            ly, xs, parts = chosen
            for pt in parts:
                self.box(rc, L_METAL2, pt.left, pt.bottom, pt.right, pt.top)
                obs.add(net, pt)
            via(None, L_VIA2, L_METAL3, xs, ly)
            via(None, L_VIA3, L_METAL4, xs, ly)
            pad3 = kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)
            obs.add_m3(pad3)
            state.via2_at.setdefault((ri, net, ly), []).append(xs)
            state.used.setdefault((ri, net), set()).add(ly)
            self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": xs, "region": ri,
                                    "stub": "Metal2"})
        # lanes that serve at least one tie run on Metal4 out to the trunk of their net
        for (ri, net), ys in sorted(state.used.items()):
            rb = regions[ri]
            tx = trunk_x[net]
            x0 = rb.left * DBU
            for ly in sorted(ys):
                self.box(rc, L_METAL4, x0, ly - LANE_W / 2, tx + hp, ly + LANE_W / 2)
                via(None, L_VIA4, L_METAL4, tx, ly)
        # Metal5 trunks span every lane and strap of their net
        for net in ("VDD", "VSS"):
            ys = list(seam_pads[net]) + [ly for (_, n), v in state.used.items() if n == net for ly in v]
            tx = trunk_x[net]
            self.box(rc, L_METAL5, tx - TRUNK_W / 2, min(ys) - hp, tx + TRUNK_W / 2, max(ys) + hp)
            self.text(rc, (67, 25), net, tx, min(ys))

    def tie_maze(self, net: str, x: float, y: float, ri: int, rb_x: tuple[float, float], lanes: list[float],
                 obs: Obstacles, state: RailState, reach: int = 0) -> bool:
        """Last resort for a tie whose straight stubs are blocked (issue #104): maze-route it on Metal2/Metal3 from its
        Metal2 pad to a Via3 on one of its net's Metal4 lanes, around everything already drawn. The search window grows
        (``TIE_MAZE_REACH``) where the decoder's cell nets leave no way out of the first one (issue #105)."""
        rx, ry = TIE_MAZE_REACH[reach]

        def retry() -> bool:
            if reach + 1 == len(TIE_MAZE_REACH):
                return False
            return self.tie_maze(net, x, y, ri, rb_x, lanes, obs, state, reach + 1)

        pb = self.pre_rail_bb  # the rails may extend the macro to the right only
        win = kdb.DBox(max(x - rx, pb.left * DBU + 0.5), max(y - ry, pb.bottom * DBU + 0.5), x + rx, min(y + ry, pb.top * DBU - 0.5))
        mz = MazeRouter(dbu(win.left), dbu(win.bottom), dbu(win.right), dbu(win.top))
        seen: set[int] = set()
        for c in obs.cells_of(win):
            for it in obs.m2.get(c, ()):
                n, b = it
                if id(it) in seen or (n == net and abs(b.center().x - x) < 1e-3 and abs(b.center().y - y) < 1e-3):
                    continue
                seen.add(id(it))
                mz.block(0, b.left, b.bottom, b.right, b.top)
            for b in obs.m3.get(c, ()):
                if id(b) not in seen:
                    seen.add(id(b))
                    mz.block(1, b.left, b.bottom, b.right, b.top)
        for layer in (0, 1):  # nothing below Metal4 in the wordline gap: a wire edge may reach its boundary, not enter
            mz.block(layer, -WL_FANOUT_GAP + KEEP * DBU - M2_W / 2, win.bottom, 0.0, win.top)
        near = dbu(V2 + V2_SPACE) // STEP  # a Via2 of the path keeps V2.b from every Via2 already drawn in the window
        halo = dbu(V2 + V2_SPACE)
        it = kdb.RecursiveShapeIterator(self.layout, self.rails_top, self.li(L_VIA2),
                                        kdb.Box(dbu(win.left) - halo, dbu(win.bottom) - halo, dbu(win.right) + halo, dbu(win.top) + halo))
        while not it.at_end():
            c = it.shape().bbox().transformed(it.trans()).center()
            vi, vj = c.x // STEP, c.y // STEP
            mz.via_near.update((vi + a, vj + b) for a in range(-near, near + 2) for b in range(-near, near + 2))
            it.next()
        start = mz.node(x, y)
        mz.pad(0, start, 1)
        hp = VIA_PAD / 2
        goals = set()
        for ly in lanes:
            for i in range(mz.i0, mz.i1 + 1):
                gx, gy = i * STEP * DBU, round(ly / (STEP * DBU)) * STEP * DBU
                if abs(gy - ly) > 0.055 or gx < rb_x[0] + 0.3 or in_wl_gap(gx - hp, gx + hp):
                    continue
                if any(abs(gx - ox) < VIA_PAD + M3_SPACE for ox in state.via2_at.get((ri, net, ly), ())):
                    continue
                if mz.inside(i, round(ly / (STEP * DBU))) and obs.clear3(kdb.DBox(gx - M3_W / 2, gy - M3_W / 2, gx + M3_W / 2, gy + M3_W / 2)):
                    goals.add((1, i, round(ly / (STEP * DBU))))
        if not goals:
            return retry()
        path = mz.connect(1, {(0, *start)}, goals)
        if path is None:
            return retry()
        mz.commit(1, path)
        # the tie's own pad is not an obstacle to its own path (the path starts on it), so a path that leaves it
        # and runs back underneath merges with it and leaves a notch: reject that and let the window grow, or
        # the tie fall through to a lane of its own (issue #107)
        m2 = [kdb.DBox(min(a[0], b[0]) * STEP * DBU - M2_W / 2, min(a[1], b[1]) * STEP * DBU - M2_W / 2,
                       max(a[0], b[0]) * STEP * DBU + M2_W / 2, max(a[1], b[1]) * STEP * DBU + M2_W / 2)
              for kind, l, a, b in (sh for sh in mz.shapes.get(1, []) if sh[0] == "wire") if l == 0]
        m2 += [kdb.DBox(sh[1][0] * STEP * DBU - M2_W / 2, sh[1][1] * STEP * DBU - M2_W / 2,
                        sh[1][0] * STEP * DBU + M2_W / 2, sh[1][1] * STEP * DBU + M2_W / 2)
               for sh in mz.shapes.get(1, []) if sh[0] == "via"]
        if not self.notch_free(obs, net, x, y, m2):
            return retry()
        ly = min(lanes, key=lambda v: abs(v - path[-1][2] * STEP * DBU))
        # the Metal2 pad of the tie to the path start (lattice nodes are 0.05 apart, the pad is on the 0.005 grid)
        self.seg(state.rc, L_METAL2, M2_W, x, y, start[0] * STEP * DBU, start[1] * STEP * DBU)
        for sh in mz.shapes.get(1, []):
            if sh[0] == "wire":
                _, l, a, b = sh
                lp = L_METAL2 if l == 0 else L_METAL3
                self.seg(state.rc, lp, M2_W, a[0] * STEP * DBU, a[1] * STEP * DBU, b[0] * STEP * DBU, b[1] * STEP * DBU)
                bx = kdb.DBox(min(a[0], b[0]) * STEP * DBU - M2_W / 2, min(a[1], b[1]) * STEP * DBU - M2_W / 2,
                              max(a[0], b[0]) * STEP * DBU + M2_W / 2, max(a[1], b[1]) * STEP * DBU + M2_W / 2)
                if l == 0:
                    obs.add(net, bx)
                else:
                    obs.add_m3(bx)
            else:
                vx, vy = sh[1][0] * STEP * DBU, sh[1][1] * STEP * DBU
                self.via_pad(state.rc, L_VIA2, vx, vy)
                for lp in (L_METAL2, L_METAL3):
                    self.rect(state.rc, lp, vx, vy, M2_W, M2_W)
        gx, gy = path[-1][1] * STEP * DBU, path[-1][2] * STEP * DBU
        self.via_pad(state.rc, L_VIA3, gx, gy)
        self.rect(state.rc, L_METAL3, gx, gy, M3_W, M3_W)
        pad3 = kdb.DBox(gx - hp, gy - hp, gx + hp, gy + hp)
        obs.add_m3(pad3)
        state.via2_at.setdefault((ri, net, ly), []).append(round(gx, 3))
        state.used.setdefault((ri, net), set()).add(ly)
        self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": round(gx, 3), "region": ri, "stub": "maze"})
        return True

    def pins(self, top: kdb.Cell, bb: kdb.Box, ports: list[str], arr_w: int) -> list[dict]:
        out: list[dict] = []
        sl_w = 2 * bc.W_CELL

        def add(name: str, x0: float, y0: float, direction: str, use: str) -> None:
            self.box(top, L_METAL2, x0, y0, x0 + PIN, y0 + PIN)
            self.text(top, L_METAL2_LBL, name, x0 + PIN / 2, y0 + PIN / 2)
            out.append({"name": name, "x": round(x0 + PIN / 2, 3), "y": round(y0 + PIN / 2, 3),
                        "direction": direction, "use": use})

        left, bottom = bb.left * DBU, bb.bottom * DBU
        # bottom edge: D[i], Q[i] either side of slice i's centre, M2.b outside the content so the
        # periphery's Metal2 (issues #92, #104) keeps its spacing to them
        for i in range(SLICES):
            xc = (i + 0.5) * sl_w
            add(f"D[{i}]", round(xc - 1.5, 3), round(bottom - PIN - M2_SPACE, 3), "INPUT", "SIGNAL")
            add(f"Q[{i}]", round(xc + 1.0, 3), round(bottom - PIN - M2_SPACE, 3), "OUTPUT", "SIGNAL")
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
