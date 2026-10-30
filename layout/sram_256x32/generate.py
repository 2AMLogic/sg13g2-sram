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

What is NOT drawn (disclosed, not hidden)
-----------------------------------------
No signal routing between cells and none to the pins (#95): the decoder, latch and control cells' own nets
(children 2, 3), the fan-out between blocks (4) and the pins (5). The ``VDD``/``VSS`` pin squares are not
connected to the rails, and the supply D/S terminals of the devices are not joined to the ties. One leaf-cell
net is undrawn: ``column_mux`` ``BLBM``, whose terminals are separated by the bit-line jogs (Metal2) and
lanes (Metal3) with too few Metal3 crossings left (``leaf_report["column_mux"]["failed"]``). The array
interface (wordlines, bit lines) is routed; the macro is placed, tapped and supplied, not fully
signal-connected. LVS (#30) and power delivery checks (#31) are the checks that must be run once routing exists.

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

# ---- signal router (issue #104) ----
STEP = 50  # dbu: routing lattice pitch (0.05 um); wires are M2_W wide, centred on lattice nodes
WRONG_WAY = 4  # cost of a lattice step against a layer's preferred direction (Metal2 vertical, Metal3 horizontal)
MAX_ROUTE_TRIES = 12  # orderings tried per cell before a net is reported undrawn
VIA_COST = 16  # lattice steps a Via2 is worth (0.8 um): hopping layers for a short run is never worth it, so vias stay V2.b apart
LEAF_ROUTED = ("inv", "inv_x4", "dlatch", "nand2", "nand3", "nand4", "nor2",
               "precharge", "column_mux", "sense_amp", "write_driver")
COLPATH_CELLS = ("precharge", "column_mux", "sense_amp", "write_driver")
SUPPLY_NETS = ("VDD", "VSS")


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
_WL_NET = re.compile(r"^WL\[\d+\]$")
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

    def node(self, x: float, y: float) -> tuple[int, int]:
        return round(dbu(x) / STEP), round(dbu(y) / STEP)

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

    def pad(self, layer: int, node: tuple[int, int], net: int) -> None:
        h = dbu(M2_W / 2)
        i, j = node
        self._mark(layer, i * STEP - h, j * STEP - h, i * STEP + h, j * STEP + h, net)

    def _free(self, layer: int, i: int, j: int, net: int) -> bool:
        return self.inside(i, j) and self.owner[layer][i - self.i0][j - self.j0] in (0, net)

    def connect(self, net: int, tree: set[tuple[int, int, int]], goals: set[tuple[int, int, int]]):
        """Cheapest path from any (layer, i, j) of ``tree`` to a goal (layer, i, j); None if there is none."""
        import heapq

        dist: dict[tuple, int] = {}
        prev: dict[tuple, tuple] = {}
        heap = [(0, *n) for n in sorted(tree)]
        for n in tree:
            dist[n] = 0
        heapq.heapify(heap)
        owner, i0, i1, j0, j1 = self.owner, self.i0, self.i1, self.j0, self.j1
        via_near = self.via_near
        big = 1 << 30
        while heap:
            d, l, i, j = heapq.heappop(heap)
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
                    heapq.heappush(heap, (d + c, l2, i2, j2))
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

    def route_net(self, net: int, terminals: list[tuple[int, int]]) -> bool:
        """Join the terminals (Metal2 pads, already claimed with ``pad``) into one tree."""
        if len(terminals) < 2:
            return True
        tree = {(0, *terminals[0])}
        todo = set(terminals[1:])
        todo -= {t for t in todo if (0, *t) in tree}
        while todo:
            path = self.connect(net, tree, {(0, *t) for t in todo})
            if path is None:
                return False
            self.commit(net, path)
            tree |= set(path)
            todo.discard(path[-1][1:])
        return True


def route_orders(names: list[str], size: dict[str, int]) -> list[list[str]]:
    """Net orderings to try: short nets first, long first, then reversed alphabetical."""
    by = sorted(names, key=lambda n: (size[n], n))
    return [by, by[::-1], sorted(names, reverse=True)]


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
    def pack(self, items: list[kdb.Cell], max_w: float, pack_gap: float = PACK_GAP) -> tuple[list[tuple[kdb.Cell, int, int]], int, int]:
        """Shelf-pack cells by bbox. Returns [(cell, dx, dy)] placing each
        bbox's lower-left at the shelf position, plus the packed width/height."""
        gap, mw = dbu(pack_gap), dbu(max_w)
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
        placed, _, _ = self.pack(items, mw, LEAF_PACK_GAP if name in LEAF_ROUTED and name not in COLPATH_CELLS else PACK_GAP)
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
        elif name in LEAF_ROUTED:
            self.route_leaf(name, cell)
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
        size = {n: max(1, sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a in node[n] for b in node[n])) for n in names}
        base = mz
        best = None
        tried: list[list[str]] = []
        orders = route_orders(names, size) if names else [[]]
        while orders and len(tried) < MAX_ROUTE_TRIES:
            order = orders.pop(0)
            if order in tried:
                continue
            tried.append(order)
            mz = MazeRouter(bb.left, bb.bottom, bb.right, bb.top)
            mz.owner = [[col[:] for col in lay] for lay in base.owner]
            for n in names:
                for t in node[n]:
                    mz.pad(0, t, ids[n])
            failed = [n for n in order if not mz.route_net(ids[n], sorted(set(node[n])))]
            if best is None or len(failed) < len(best[1]):
                best = (mz, failed)
            if not failed:
                break
            # rip up and reroute: the nets that did not fit go first next time
            orders.append(failed + [n for n in order if n not in failed])
            orders.append([n for n in order if n not in failed] + failed[::-1])
        mz, failed = best if best else (mz, [])
        for n in names:
            if phase == "all":
                for t in sorted(set(node[n])):
                    self.m1_via1(cell, t[0] * STEP * DBU, t[1] * STEP * DBU)
            if n in failed:
                report["failed"].append(n)
                continue
            report["routed"][n] = len(by_net[n])
            drawn, vias = self.draw_shapes(cell, mz.shapes.get(ids[n], []))
            for t in sorted(set(node[n])):
                drawn[0].insert(kdb.Box(dbu(t[0] * STEP * DBU - M2_W / 2), dbu(t[1] * STEP * DBU - M2_W / 2),
                                        dbu(t[0] * STEP * DBU + M2_W / 2), dbu(t[1] * STEP * DBU + M2_W / 2)))
            self.leaf_vias.setdefault(name, []).extend({"net": n, **v} for v in vias)
            # two parts of one net that run closer than the layer's spacing (a wire folding back beside itself) are
            # joined: the gap is filled, so the pair is one shape instead of a spacing violation
            for l, lp in ((0, L_METAL2), (1, L_METAL3)):
                rg = drawn[l].merged()
                gaps = rg.space_check(dbu(M2_SPACE)) + rg.notch_check(dbu(M2_SPACE))
                for ep in gaps.each():
                    cell.shapes(self.li(lp)).insert(ep.bbox())
        self.leaf_terms[name] = {n: [(t[0] * STEP * DBU, t[1] * STEP * DBU) for t in sorted(set(node[n]))]
                                 for n in names if n not in failed}
        self.leaf_report[name] = report

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
                        if any(pt.right > -WL_FANOUT_GAP and pt.left < 0 for pt in parts + [kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)]):
                            continue  # nothing below Metal4 in the wordline gap
                        if all(clear(net, pt) for pt in parts):
                            chosen = (ly, xs, parts)
                            break
                    if chosen:
                        break
                if chosen:
                    break
            if chosen is None:
                # the Metal2 around the tie is taken by cell routing (issue #104): leave on Metal3 instead, from a
                # Via2 on the tie's own Metal2 pad to a Via3 on the lane
                chosen3 = None
                for ly in sorted(lanes[(ri, net)], key=lambda ly: abs(ly - y))[:8]:
                    lo, hi = min(y, ly), max(y, ly)
                    for dx in sorted([round(0.2 * i, 3) for i in range(-30, 31)], key=abs):
                        if dx and (abs(dx) < hp + M3_SPACE + STUB_W / 2 + 0.01 or abs(ly - y) < hp + M3_SPACE + STUB_W / 2 + 0.01):
                            continue  # a sideways run keeps M3.b to its own pads (otherwise a sliver between them)
                        xs = round(x + dx, 3)
                        if any(0 < abs(xs - ox) < VIA_PAD + M3_SPACE for ox in via2_at.get((ri, net, ly), ())):
                            continue
                        parts = [kdb.DBox(x - hp, y - hp, x + hp, y + hp), kdb.DBox(xs - hw, lo - hw, xs + hw, hi + hw),
                                 kdb.DBox(xs - hp, ly - hp, xs + hp, ly + hp)]
                        if dx:
                            parts.append(kdb.DBox(min(x, xs) - hw, y - hw, max(x, xs) + hw, y + hw))
                        if any(pt.right > -WL_FANOUT_GAP and pt.left < 0 for pt in parts):
                            continue  # nothing below Metal4 in the wordline gap
                        if all(clear3(pt) for pt in parts):
                            chosen3 = (ly, xs, parts)
                            break
                    if chosen3:
                        break
                if chosen3:
                    ly, xs, parts = chosen3
                    for pt in parts:
                        self.box(rc, L_METAL3, pt.left, pt.bottom, pt.right, pt.top)
                        put(obst3, pt, pt)
                    via(None, L_VIA2, L_METAL3, x, y)
                    via(None, L_VIA3, L_METAL4, xs, ly)
                    via2_at.setdefault((ri, net, ly), []).append(xs)
                    used.setdefault((ri, net), set()).add(ly)
                    self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": xs, "region": ri,
                                            "stub": "Metal3"})
                    continue
                if self.tie_maze(net, x, y, ri, rb_x=(regions[ri].left * DBU, regions[ri].right * DBU), lanes=lanes[(ri, net)],
                                 obst=obst, obst3=obst3, cells_of=cells_of, via2_at=via2_at, clear3=clear3, rc=rc,
                                 add_obst=add_obst, put=put, used=used):
                    continue
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
            self.tie_wiring.append({"net": net, "x": x, "y": y, "lane_y": ly, "lane_x": xs, "region": ri,
                                    "stub": "Metal2"})
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

    def tie_maze(self, net: str, x: float, y: float, ri: int, rb_x: tuple[float, float], lanes: list[float], obst: dict,
                 obst3: dict, cells_of, via2_at: dict, clear3, rc: kdb.Cell, add_obst, put, used: dict) -> bool:
        """Last resort for a tie whose straight stubs are blocked (issue #104): maze-route it on Metal2/Metal3 from its
        Metal2 pad to a Via3 on one of its net's Metal4 lanes, around everything already drawn."""
        win = kdb.DBox(x - 8.0, y - 5.0, x + 8.0, y + 5.0)
        mz = MazeRouter(dbu(win.left), dbu(win.bottom), dbu(win.right), dbu(win.top))
        seen: set[int] = set()
        for c in cells_of(win):
            for it in obst.get(c, ()):
                n, b = it
                if id(it) in seen or (n == net and abs(b.center().x - x) < 1e-3 and abs(b.center().y - y) < 1e-3):
                    continue
                seen.add(id(it))
                mz.block(0, b.left, b.bottom, b.right, b.top)
            for b in obst3.get(c, ()):
                if id(b) not in seen:
                    seen.add(id(b))
                    mz.block(1, b.left, b.bottom, b.right, b.top)
        for layer in (0, 1):  # nothing below Metal4 in the wordline gap: a wire edge may reach its boundary, not enter
            mz.block(layer, -WL_FANOUT_GAP + KEEP * DBU - M2_W / 2, win.bottom, 0.0, win.top)
        start = mz.node(x, y)
        mz.pad(0, start, 1)
        hp = VIA_PAD / 2
        goals = set()
        for ly in lanes:
            for i in range(mz.i0, mz.i1 + 1):
                gx, gy = i * STEP * DBU, round(ly / (STEP * DBU)) * STEP * DBU
                if abs(gy - ly) > 0.055 or gx < rb_x[0] + 0.3 or (gx + hp > -WL_FANOUT_GAP and gx - hp < 0):
                    continue
                if any(abs(gx - ox) < VIA_PAD + M3_SPACE for ox in via2_at.get((ri, net, ly), ())):
                    continue
                if mz.inside(i, round(ly / (STEP * DBU))) and clear3(kdb.DBox(gx - M3_W / 2, gy - M3_W / 2, gx + M3_W / 2, gy + M3_W / 2)):
                    goals.add((1, i, round(ly / (STEP * DBU))))
        if not goals:
            return False
        path = mz.connect(1, {(0, *start)}, goals)
        if path is None:
            return False
        mz.commit(1, path)
        ly = min(lanes, key=lambda v: abs(v - path[-1][2] * STEP * DBU))
        # the Metal2 pad of the tie to the path start (lattice nodes are 0.05 apart, the pad is on the 0.005 grid)
        self.seg(rc, L_METAL2, M2_W, x, y, start[0] * STEP * DBU, start[1] * STEP * DBU)
        for sh in mz.shapes.get(1, []):
            if sh[0] == "wire":
                _, l, a, b = sh
                lp = L_METAL2 if l == 0 else L_METAL3
                self.seg(rc, lp, M2_W, a[0] * STEP * DBU, a[1] * STEP * DBU, b[0] * STEP * DBU, b[1] * STEP * DBU)
                bx = kdb.DBox(min(a[0], b[0]) * STEP * DBU - M2_W / 2, min(a[1], b[1]) * STEP * DBU - M2_W / 2,
                              max(a[0], b[0]) * STEP * DBU + M2_W / 2, max(a[1], b[1]) * STEP * DBU + M2_W / 2)
                if l == 0:
                    add_obst(net, bx)
                else:
                    put(obst3, bx, bx)
            else:
                vx, vy = sh[1][0] * STEP * DBU, sh[1][1] * STEP * DBU
                self.via_pad(rc, L_VIA2, vx, vy)
                for lp in (L_METAL2, L_METAL3):
                    self.rect(rc, lp, vx, vy, M2_W, M2_W)
        gx, gy = path[-1][1] * STEP * DBU, path[-1][2] * STEP * DBU
        self.via_pad(rc, L_VIA3, gx, gy)
        self.rect(rc, L_METAL3, gx, gy, M3_W, M3_W)
        pad3 = kdb.DBox(gx - hp, gy - hp, gx + hp, gy + hp)
        put(obst3, pad3, pad3)
        via2_at.setdefault((ri, net, ly), []).append(round(gx, 3))
        used.setdefault((ri, net), set()).add(ly)
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
