#!/usr/bin/env python3
"""Generate the SG13G2 6T SRAM bitcell layout and its 2x2 abutment tile.

Draws ``design/bitcell/bitcell.spice`` (sizes below) on the IHP SG13G2 drawing
layers. Every rule value is taken from the PDK deck (``klt deck rules --deck
sg13g2`` and ``sg13g2_tech_default.json`` of the PDK's native KLayout deck),
not from the gf180mcu origin and not from the foundry ``BITKIT_*`` cells.

Run from the repo root::

    uv run --with klayout python3 layout/bitcell/generate.py

Outputs (byte-stable; GDS timestamps are disabled):

* ``layout/bitcell/sg13g2_sram_bitcell_6t.gds``   -- cell ``sg13g2_sram_bitcell_6t``
* ``layout/bitcell/sg13g2_sram_bitcell_tile2x2.gds`` -- 2x2 mirror-abutment tile

## Topology

One Activ strip carries the four NMOS devices in schematic order::

    BL | MN2 | Q | MN0 | VSS | MN1 | QB | MN3 | BLB

A second Activ row inside NWell carries the pull-ups ``Q | MP0 | VDD | MP1 | QB``.
Both W values equal or undercut the contact-pad height, so the NMOS strip is a
plain rectangle (W = 0.30) and the PMOS row narrows to W = 0.15 at each gate.
The cross-coupling uses the origin's two-jog scheme: each inverter gate poly
jogs into the centre column at its own height and is strapped in Metal1 to the
opposite storage node's diffusions.

## Boundary contract (mirror tiling in X and Y)

* ``BL`` / ``BLB`` -- vertical Metal1 stripes over the full cell height.
* ``WL``           -- horizontal GatPoly over the full cell width.
* Ties are in-cell (decision recorded in ``layout/README.md``): a full-width
  p-substrate tie strip (VSS) near the bottom edge and an n-well tie strip
  (VDD) near the top edge, each inset half an Activ spacing from the edge.
  The VSS/VDD Metal1 risers run to the edge, so mirror copies merge them and
  the supplies are continuous along a column; the full-width tie strips merge
  along a row.
* NWell and pSD extend past the pitch box where the tie strips need
  enclosure; mirrored neighbours overlap them. The pitch box is the
  ``prBoundary`` rectangle (189/4); area is quoted from it.

The cell does not use ``SRAM.drawing`` (25/0): no relaxed SRAM rule is claimed.
"""

from __future__ import annotations

import os
import sys

import klayout.db as kdb

# ---------------------------------------------------------------------------
# SG13G2 layers (GDS layer, datatype), from libs.tech/klayout/tech/sg13g2.lyp.
# ---------------------------------------------------------------------------
L_ACTIV = (1, 0)
L_GATPOLY = (5, 0)
L_GATPOLY_LBL = (5, 1)
L_CONT = (6, 0)
L_METAL1 = (8, 0)
L_METAL1_LBL = (8, 25)
L_PSD = (14, 0)
L_NWELL = (31, 0)
L_PRBOUNDARY = (189, 4)

_LAYER_NAMES = {
    L_ACTIV: "Activ",
    L_GATPOLY: "GatPoly",
    L_GATPOLY_LBL: "GatPoly_label",
    L_CONT: "Cont",
    L_METAL1: "Metal1",
    L_METAL1_LBL: "Metal1_text",
    L_PSD: "pSD",
    L_NWELL: "NWell",
    L_PRBOUNDARY: "prBoundary",
}

# ---------------------------------------------------------------------------
# Rule constants (um). Deck rule ids in comments (klt sg13g2 deck / PDK
# sg13g2_maximal.drc). Margins over the minimum are explicit.
# ---------------------------------------------------------------------------
CO = 0.16  # Cnt.a: Cont is a fixed 0.16 square
CO_ENC_ACT = 0.07  # Cnt.c
CO_ENC_POLY = 0.07  # Cnt.d
CO_ENC_M1 = 0.05  # M1.c1 end-of-line enclosure of Cont
CO_POLY_TO_ACT = 0.14  # Cnt.e: Cont on GatPoly to Activ
PAD = CO + 2 * CO_ENC_ACT  # 0.30: Activ pad holding one contact
GAP = 0.08  # pad edge to gate edge: > Gat.d 0.07 (field poly to Activ); Cnt.f 0.11 met via CO_ENC_ACT
GATE_ENDCAP = 0.18  # Gat.c: GatPoly extension past Activ
POLY_SPACE = 0.18  # Gat.b
POLY_TO_ACT = 0.07  # Gat.d
ACT_SPACE = 0.21  # Act.b
M1_W = 0.20  # >= M1.a 0.16
M1_STRAP_W = 0.16  # M1.a
M1_SPACE = 0.18  # M1.b
PSD_ENC_ACT = 0.18  # pSD.c / pSD.d
PSD_TO_NACT = 0.30  # pSD.e class: pSD to n+ Activ, kept at 0.30
NW_ENC_PACT = 0.31  # NW.c
NW_ENC_NACT = 0.24  # NW.e
NW_TO_NACT = 0.31  # NW.d

# ---------------------------------------------------------------------------
# Device sizing -- design/bitcell/bitcell.spice (sg13_lv_nmos / sg13_lv_pmos).
# ---------------------------------------------------------------------------
L_GATE = 0.13
W_N = 0.30  # XMN0..XMN3 (pull-down and access)
W_P = 0.15  # XMP0, XMP1
assert abs(W_N - PAD) < 1e-9, "NMOS strip is drawn as a plain PAD-tall rectangle"

TOP_CELL = "sg13g2_sram_bitcell_6t"
TILE_CELL = "sg13g2_sram_bitcell_tile2x2"


def r(v: float) -> float:
    return round(v, 3)


# ---------------------------------------------------------------------------
# X plan (one accumulation pass across the NMOS strip).
# ---------------------------------------------------------------------------
MARGIN_X = r(ACT_SPACE / 2 + 0.0)  # 0.105: half the Activ spacing across a mirror seam


def _x_plan() -> dict[str, tuple[float, float]]:
    cur = MARGIN_X
    plan: dict[str, tuple[float, float]] = {}

    def place(name: str, width: float) -> None:
        nonlocal cur
        plan[name] = (r(cur), r(cur + width))
        cur += width

    place("pad_bl", PAD)
    cur += GAP
    place("g_wl_l", L_GATE)
    cur += GAP
    place("pad_q", PAD)
    cur += GAP
    place("g_l", L_GATE)  # gate of MN0/MP0, net QB
    cur += GAP
    place("pad_c", PAD)  # VSS (NMOS) / VDD (PMOS)
    cur += GAP
    place("g_r", L_GATE)  # gate of MN1/MP1, net Q
    cur += GAP
    place("pad_qb", PAD)
    cur += GAP
    place("g_wl_r", L_GATE)
    cur += GAP
    place("pad_blb", PAD)
    plan["_end"] = (r(cur), r(cur + MARGIN_X))
    return plan


X = _x_plan()
W_CELL = X["_end"][1]


def xc(name: str) -> float:
    return r(0.5 * (X[name][0] + X[name][1]))


# ---------------------------------------------------------------------------
# Y plan (bottom-up).
# ---------------------------------------------------------------------------
SEAM_INSET = 0.105  # half of Act.b: tie Activ stays 0.21 from its mirror copy
Y_PTIE = (SEAM_INSET, r(SEAM_INSET + PAD))  # p-substrate tie
Y_WL = (0.50, 0.66)  # wordline GatPoly (0.16 tall)
Y_N = (1.02, r(1.02 + W_N))  # NMOS strip
# cross-couple landing pads (GatPoly, PAD square); contact centred on each
POLY_PAD = CO + 2 * CO_ENC_POLY  # 0.30
Y_JOG1 = (r(Y_N[1] + 0.14), r(Y_N[1] + 0.14 + POLY_PAD))  # gate_L / net QB
Y_JOG2 = (r(Y_JOG1[1] + POLY_SPACE), r(Y_JOG1[1] + POLY_SPACE + POLY_PAD))  # gate_R / net Q
Y_P0 = r(Y_JOG2[1] + 0.18)  # PMOS row bottom: clears Cnt.e 0.14 and the VDD riser's M1 spacing
Y_P = (Y_P0, r(Y_P0 + PAD))
Y_NTIE_BOT = r(Y_P[1] + PSD_ENC_ACT + PSD_TO_NACT)
Y_NTIE = (Y_NTIE_BOT, r(Y_NTIE_BOT + PAD))  # n-well tie, flush with the top edge
H_CELL = r(Y_NTIE[1] + SEAM_INSET)


def _co_y(y: tuple[float, float]) -> tuple[float, float]:
    mid = 0.5 * (y[0] + y[1])
    return (r(mid - 0.5 * CO), r(mid + 0.5 * CO))


def _b(x0: float, y0: float, x1: float, y1: float) -> kdb.DBox:
    return kdb.DBox(x0, y0, x1, y1)


def _co(cx: float, y: tuple[float, float]) -> kdb.DBox:
    cy = _co_y(y)
    return _b(cx - 0.5 * CO, cy[0], cx + 0.5 * CO, cy[1])


def shapes() -> dict[tuple[int, int], list[kdb.DBox]]:
    out: dict[tuple[int, int], list[kdb.DBox]] = {k: [] for k in _LAYER_NAMES}

    # ---- Activ ----
    out[L_ACTIV].append(_b(X["pad_bl"][0], Y_N[0], X["pad_blb"][1], Y_N[1]))  # NMOS strip
    for pad in ("pad_q", "pad_c", "pad_qb"):  # PMOS pads
        out[L_ACTIV].append(_b(X[pad][0], Y_P[0], X[pad][1], Y_P[1]))
    for g in ("g_l", "g_r"):  # PMOS channel necks (W = 0.15)
        out[L_ACTIV].append(_b(X[g][0] - GAP, Y_P[0], X[g][1] + GAP, r(Y_P[0] + W_P)))
    out[L_ACTIV].append(_b(0.0, Y_PTIE[0], W_CELL, Y_PTIE[1]))
    out[L_ACTIV].append(_b(0.0, Y_NTIE[0], W_CELL, Y_NTIE[1]))

    # ---- GatPoly ----
    out[L_GATPOLY].append(_b(0.0, Y_WL[0], W_CELL, Y_WL[1]))
    y_acc_top = r(Y_N[1] + GATE_ENDCAP)
    for g in ("g_wl_l", "g_wl_r"):
        out[L_GATPOLY].append(_b(X[g][0], Y_WL[0], X[g][1], y_acc_top))
    y_inv_bot = r(Y_N[0] - GATE_ENDCAP)
    y_inv_top = r(Y_P[0] + W_P + GATE_ENDCAP)
    for g in ("g_l", "g_r"):
        out[L_GATPOLY].append(_b(X[g][0], y_inv_bot, X[g][1], y_inv_top))
    # g_l (net QB) jogs right into the centre column; g_r (net Q) jogs left,
    # one POLY_SPACE higher
    x_jog1 = (X["g_l"][0], r(X["g_l"][0] + POLY_PAD))
    x_jog2 = (r(X["g_r"][1] - POLY_PAD), X["g_r"][1])
    out[L_GATPOLY].append(_b(x_jog1[0], Y_JOG1[0], x_jog1[1], Y_JOG1[1]))
    out[L_GATPOLY].append(_b(x_jog2[0], Y_JOG2[0], x_jog2[1], Y_JOG2[1]))

    # ---- implants / well ----
    px0 = X["pad_q"][0] - PSD_ENC_ACT
    px1 = X["pad_qb"][1] + PSD_ENC_ACT
    out[L_PSD].append(_b(r(px0), r(Y_P[0] - PSD_ENC_ACT), r(px1), r(Y_P[1] + PSD_ENC_ACT)))
    out[L_PSD].append(
        _b(-PSD_ENC_ACT, r(Y_PTIE[0] - PSD_ENC_ACT), r(W_CELL + PSD_ENC_ACT), r(Y_PTIE[1] + PSD_ENC_ACT))
    )
    out[L_NWELL].append(
        _b(
            -NW_ENC_NACT,
            r(Y_P[0] - NW_ENC_PACT),
            r(W_CELL + NW_ENC_NACT),
            r(Y_NTIE[1] + NW_ENC_NACT),
        )
    )

    # ---- contacts ----
    for pad in ("pad_bl", "pad_q", "pad_c", "pad_qb", "pad_blb"):
        out[L_CONT].append(_co(xc(pad), Y_N))
    for pad in ("pad_q", "pad_c", "pad_qb"):
        out[L_CONT].append(_co(xc(pad), Y_P))
    out[L_CONT].append(_co(xc("pad_c"), Y_PTIE))
    out[L_CONT].append(_co(xc("pad_c"), Y_NTIE))
    x_cj1 = r(0.5 * (x_jog1[0] + x_jog1[1]))
    x_cj2 = r(0.5 * (x_jog2[0] + x_jog2[1]))
    out[L_CONT].append(_co(x_cj1, Y_JOG1))
    out[L_CONT].append(_co(x_cj2, Y_JOG2))

    # ---- Metal1 ----
    # bitline stripes, full height
    for pad in ("pad_bl", "pad_blb"):
        out[L_METAL1].append(_b(r(xc(pad) - 0.5 * M1_W), 0.0, r(xc(pad) + 0.5 * M1_W), H_CELL))
    # VSS riser: ptie contact up to the NMOS centre pad
    cy_pt = _co_y(Y_PTIE)
    cy_n = _co_y(Y_N)
    cy_p = _co_y(Y_P)
    cy_nt = _co_y(Y_NTIE)
    xl, xr = r(xc("pad_c") - 0.5 * M1_W), r(xc("pad_c") + 0.5 * M1_W)
    out[L_METAL1].append(_b(xl, 0.0, xr, r(cy_n[1] + CO_ENC_M1)))
    # VDD riser: PMOS centre pad up to the n-well tie
    out[L_METAL1].append(_b(xl, r(cy_p[0] - CO_ENC_M1), xr, H_CELL))
    # Q net: NMOS + PMOS drain bar, strap to the g_r landing pad
    for pad in ("pad_q", "pad_qb"):
        out[L_METAL1].append(
            _b(
                r(xc(pad) - 0.5 * M1_W),
                r(cy_n[0] - CO_ENC_M1),
                r(xc(pad) + 0.5 * M1_W),
                r(cy_p[1] + CO_ENC_M1),
            )
        )
    cj1 = _co_y(Y_JOG1)
    cj2 = _co_y(Y_JOG2)
    # landing pads on the two jog contacts
    out[L_METAL1].append(
        _b(r(x_cj1 - 0.5 * CO), r(cj1[0] - CO_ENC_M1), r(x_cj1 + 0.5 * CO), r(cj1[1] + CO_ENC_M1))
    )
    out[L_METAL1].append(
        _b(r(x_cj2 - 0.5 * CO), r(cj2[0] - CO_ENC_M1), r(x_cj2 + 0.5 * CO), r(cj2[1] + CO_ENC_M1))
    )
    # QB strap (from g_l's jog to the pad_qb bar), Q strap (g_r's jog to pad_q bar)
    out[L_METAL1].append(
        _b(r(x_cj1 - 0.5 * CO), r(0.5 * (cj1[0] + cj1[1]) - 0.5 * M1_STRAP_W), r(xc("pad_qb") + 0.5 * M1_W), r(0.5 * (cj1[0] + cj1[1]) + 0.5 * M1_STRAP_W))
    )
    out[L_METAL1].append(
        _b(r(xc("pad_q") - 0.5 * M1_W), r(0.5 * (cj2[0] + cj2[1]) - 0.5 * M1_STRAP_W), r(x_cj2 + 0.5 * CO), r(0.5 * (cj2[0] + cj2[1]) + 0.5 * M1_STRAP_W))
    )

    # ---- pitch box ----
    out[L_PRBOUNDARY].append(_b(0.0, 0.0, W_CELL, H_CELL))
    return out


# Pin labels: (layer, text, x, y)
def labels() -> tuple[tuple[tuple[int, int], str, float, float], ...]:
    cy_n = _co_y(Y_N)
    return (
        (L_METAL1_LBL, "BL", xc("pad_bl"), 0.5 * H_CELL),
        (L_METAL1_LBL, "BLB", xc("pad_blb"), 0.5 * H_CELL),
        (L_METAL1_LBL, "Q", xc("pad_q"), 0.5 * (cy_n[0] + cy_n[1])),
        (L_METAL1_LBL, "QB", xc("pad_qb"), 0.5 * (cy_n[0] + cy_n[1])),
        (L_METAL1_LBL, "VSS", xc("pad_c"), 0.5 * (Y_PTIE[1] + Y_N[0])),
        (L_METAL1_LBL, "VDD", xc("pad_c"), 0.5 * (Y_P[1] + Y_NTIE[0])),
        (L_GATPOLY_LBL, "WL", 0.5 * (X["g_wl_l"][0] + X["g_wl_l"][1]), 0.5 * (Y_WL[0] + Y_WL[1])),
    )


def draw(layout: kdb.Layout, top: kdb.Cell, with_labels: bool = True) -> None:
    for lp, boxes in shapes().items():
        if not boxes:
            continue
        li = layout.layer(*lp)
        layout.set_info(li, kdb.LayerInfo(*lp, _LAYER_NAMES[lp]))
        region = kdb.Region()
        for box in boxes:
            region.insert(kdb.Box.from_dbox(box * (1.0 / layout.dbu)))
        region.merge()
        top.shapes(li).insert(region)
    if with_labels:
        for lp, text, x, y in labels():
            li = layout.layer(*lp)
            layout.set_info(li, kdb.LayerInfo(*lp, _LAYER_NAMES[lp]))
            top.shapes(li).insert(
                kdb.Text(text, kdb.Trans(int(round(x / layout.dbu)), int(round(y / layout.dbu))))
            )


def build() -> kdb.Layout:
    layout = kdb.Layout()
    layout.dbu = 0.001
    draw(layout, layout.create_cell(TOP_CELL))
    return layout


def build_tile(cols: int = 2, rows: int = 2) -> kdb.Layout:
    """Mirror-abutted cols x rows tile of the bitcell.

    Column j is mirrored in X for odd j, row i in Y for odd i. Labels: global
    VDD/VSS, per-column BL<j>/BLB<j>, per-row WL<i>; Q/QB are left anonymous.
    """
    layout = kdb.Layout()
    layout.dbu = 0.001
    cell = layout.create_cell("bitcell_leaf")
    draw(layout, cell, with_labels=False)
    top = layout.create_cell(TILE_CELL)
    dbu = layout.dbu
    w = int(round(W_CELL / dbu))
    h = int(round(H_CELL / dbu))
    for i in range(rows):
        for j in range(cols):
            mx, my = j % 2 == 1, i % 2 == 1
            x0 = (j + (1 if mx else 0)) * w
            y0 = (i + (1 if my else 0)) * h
            trans = {
                (False, False): kdb.Trans.R0,
                (True, False): kdb.Trans.M90,
                (False, True): kdb.Trans.M0,
                (True, True): kdb.Trans.R180,
            }[(mx, my)]
            top.insert(kdb.CellInstArray(cell.cell_index(), kdb.Trans(trans.rot, trans.is_mirror(), x0, y0)))
    # labels
    def lab(lp, text, x, y):
        li = layout.layer(*lp)
        layout.set_info(li, kdb.LayerInfo(*lp, _LAYER_NAMES[lp]))
        top.shapes(li).insert(kdb.Text(text, kdb.Trans(int(round(x / dbu)), int(round(y / dbu)))))

    def fx(x, j):
        return (j + 1) * W_CELL - x if j % 2 else j * W_CELL + x

    def fy(y, i):
        return (i + 1) * H_CELL - y if i % 2 else i * H_CELL + y

    lab(L_METAL1_LBL, "VSS", fx(xc("pad_c"), 0), fy(0.5 * (Y_PTIE[1] + Y_N[0]), 0))
    lab(L_METAL1_LBL, "VDD", fx(xc("pad_c"), 0), fy(0.5 * (Y_P[1] + Y_NTIE[0]), 0))
    for j in range(cols):
        lab(L_METAL1_LBL, f"BL{j}", fx(xc("pad_bl"), j), 0.5 * H_CELL)
        lab(L_METAL1_LBL, f"BLB{j}", fx(xc("pad_blb"), j), 0.5 * H_CELL)
    for i in range(rows):
        lab(L_GATPOLY_LBL, f"WL{i}", fx(0.5 * (X["g_wl_l"][0] + X["g_wl_l"][1]), 0), fy(0.5 * (Y_WL[0] + Y_WL[1]), i))
    return layout


def save_options() -> kdb.SaveLayoutOptions:
    opts = kdb.SaveLayoutOptions()
    opts.gds2_write_timestamps = False
    return opts


def main() -> None:
    out_dir = os.path.dirname(os.path.abspath(__file__))
    cell_path = os.path.join(out_dir, f"{TOP_CELL}.gds")
    tile_path = os.path.join(out_dir, "sg13g2_sram_bitcell_tile2x2.gds")
    if len(sys.argv) > 1:
        cell_path = sys.argv[1]
    build().write(cell_path, save_options())
    build_tile().write(tile_path, save_options())
    print(f"wrote {cell_path}")
    print(f"wrote {tile_path}")
    print(f"cell pitch: {W_CELL:.3f} x {H_CELL:.3f} um  ({W_CELL * H_CELL:.3f} um^2)")


if __name__ == "__main__":
    main()
