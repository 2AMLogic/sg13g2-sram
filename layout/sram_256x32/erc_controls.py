#!/usr/bin/env python3
"""Negative controls for the ``klt erc`` supply check of the macro (issue #229).

``macro.supply.json`` must have teeth on the 8,192-cell macro: a rail defect
or a removed body tie has to show up as a finding, or the committed as-built
report (``layout/reports/erc-macro.json``) is evidence of nothing. This module
writes three single-defect variants of the committed ``macro.gds`` and the tests
assert each variant's findings against the as-built ones:

* ``severed`` -- the VSS Metal5 trunk cut once, in the widest gap between its
  Via4 landings, so no landing is swallowed by the cut. The VSS network splits
  in two: the island count rises by one and ``erc.unconnected_net`` names it.
  Cutting one array strap instead is *invisible by design* -- the rail mesh is
  redundant (every riser is strapped at 64 seams), which this control records
  rather than fights; the trunk is the one rail whose severance the net-level
  check can see.
* ``no_tie`` -- the bitcell's n-well tie (its Activ strip *and* its Cont)
  removed from the shared ``bitcell`` cell, so all 8,192 instances lose it.
  The array's merged n-well then has no ``nwell_vdd`` tap at all and
  ``erc.missing_tie`` fires; nothing else moves.

* ``no_activ`` -- only the tie's Activ removed; its Cont and metal stay, so a
  tap definition that does not require active diffusion would still see a tie.

All edits are hierarchy-local (the ``rails`` and ``bitcell`` cells; the
variants never touch the committed files). Run from the repo root::

    uv run --with klayout python3 layout/sram_256x32/erc_controls.py \
        layout/sram_256x32/macro.gds /tmp/variants

Used by ``test_erc_controls.py`` (CI: ``layout-macro-tests.yml``) and
``./layout/verify.sh`` step 12.
"""

from __future__ import annotations

import os
import sys

import klayout.db as kdb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generate as g  # noqa: E402  (layer constants; rails_check.py's import)

VIA4 = g.L_VIA4
METAL5 = g.L_METAL5
ACTIV = g.bc.L_ACTIV
CONT = g.bc.L_CONT
GAP_UM = 1.0  # trunk cut width


def _cut_trunk(layout: kdb.Layout) -> str:
    """Sever the VSS Metal5 trunk once; returns a description of the edit."""
    rails = layout.cell("rails")
    l5 = layout.layer(*METAL5)
    l4 = layout.layer(*VIA4)
    trunks = [s.box for s in rails.shapes(l5).each() if s.is_box()]
    if len(trunks) != 2:
        raise SystemExit(f"expected the two Metal5 trunks in cell 'rails', found {len(trunks)}")
    # VSS is the inner trunk (smaller x); the generator draws VSS at the
    # smaller trunk_x (TRUNK_OFFSET beats TRUNK_PITCH).
    vss = min(trunks, key=lambda b: b.left)
    landings = sorted(
        s.box.center().y
        for s in rails.shapes(l4).each()
        if s.is_box() and vss.left <= s.box.center().x <= vss.right
    )
    if not landings:
        raise SystemExit("no Via4 landings found on the VSS trunk")
    # cut in the middle of the widest gap between consecutive landings, so the
    # cut swallows no landing (a swallowed Via4 would disconnect a lane too)
    gaps = [(b - a, 0.5 * (a + b)) for a, b in zip(landings, landings[1:])]
    _, mid = max(gaps)
    half = round(GAP_UM / (2 * layout.dbu))
    lo, hi = mid - half, mid + half
    rails.shapes(l5).clear()
    for b in trunks:
        if b is vss:
            rails.shapes(l5).insert(kdb.Box(b.left, b.bottom, b.right, lo))
            rails.shapes(l5).insert(kdb.Box(b.left, hi, b.right, b.top))
        else:
            rails.shapes(l5).insert(b)
    return (
        f"VSS Metal5 trunk cut once at y={mid * layout.dbu:.3f} um "
        f"(widest Via4 gap, {len(landings)} landings), gap {GAP_UM} um"
    )


def _remove_bitcell_ntie(layout: kdb.Layout) -> str:
    """Remove the n-well tie (Activ strip + Cont) from the shared bitcell cell."""
    cell = layout.cell("bitcell")
    la, lc = layout.layer(*ACTIV), layout.layer(*CONT)
    # the n-well tie Activ is the topmost Activ box in the cell (the tie strip
    # flush with the top edge); its Cont is the Cont inside that strip.
    tie = max(
        (s for s in cell.shapes(la).each() if s.is_box()),
        key=lambda s: s.box.top,
    )
    tie_box = tie.box
    conts = [
        s
        for s in cell.shapes(lc).each()
        if s.is_box() and tie_box.overlaps(s.box)
    ]
    if len(conts) != 1:
        raise SystemExit(f"expected one Cont on the bitcell n-well tie, found {len(conts)}")
    tie.delete()
    conts[0].delete()
    return (
        f"bitcell n-well tie removed (Activ {tie_box.to_s()} + its Cont) from "
        f"cell 'bitcell' (all 8192 instances)"
    )


def _remove_bitcell_ntie_activ(layout: kdb.Layout) -> str:
    """Remove only the n-well tie Activ; its Cont and metal stay (no diffusion under the contact)."""
    cell = layout.cell("bitcell")
    la = layout.layer(*ACTIV)
    tie = max(
        (s for s in cell.shapes(la).each() if s.is_box()),
        key=lambda s: s.box.top,
    )
    tie_box = tie.box
    tie.delete()
    return (
        f"bitcell n-well tie Activ {tie_box.to_s()} removed from cell 'bitcell'; "
        f"its Cont and Metal1 left in place (all 8192 instances)"
    )


def build_variants(src: str, outdir: str) -> dict[str, str]:
    """Write ``<outdir>/macro-severed.gds``, ``macro-no-tie.gds`` and ``macro-no-activ.gds``.

    Returns ``{variant: description of the injected defect}``.
    """
    os.makedirs(outdir, exist_ok=True)
    out: dict[str, str] = {}
    for name, edit in (
        ("severed", _cut_trunk),
        ("no_tie", _remove_bitcell_ntie),
        ("no_activ", _remove_bitcell_ntie_activ),
    ):
        layout = kdb.Layout()
        layout.read(src)
        out[name] = edit(layout)
        path = os.path.join(outdir, f"macro-{name.replace('_', '-')}.gds")
        layout.write(path, g.save_options())
    return out


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(g.HERE, "macro.gds")
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/erc-variants"
    for name, desc in build_variants(src, outdir).items():
        print(f"{name}: {desc}")
    print(f"variants written under {outdir}")


if __name__ == "__main__":
    main()
