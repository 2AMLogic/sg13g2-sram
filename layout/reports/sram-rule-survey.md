# `SRAM.drawing` (25/0) rule survey, bitcell

**Statement: the bitcell does not draw the `SRAM.drawing` marker.** Nothing in
`layout/bitcell/generate.py` writes layer 25/0, and all geometry is checked
(or constructed) against the ordinary, non-SRAM rule values. No relaxation is
claimed, and `spec/` is not changed.

What the PDK deck says the marker relaxes, read from
`libs.tech/klayout/tech/drc/rule_decks/` of the PDK checkout used for this
work (`~/share/pdk/ihp-sg13g2`):

- `sg13g2_maximal.drc` derives `Act_Nsram`, `pSD_Nsram`, `GP_Nsram`,
  `Cont_Nsram`, `V1_Nsram`, `M1_Nsram`, `M2_Nsram`, `V2_Nsram` (shapes outside
  the marker) for the general rules.
- `feol/5_14_cont.drc`: `Cnt.c.SRAM`, Activ enclosure of Cont inside the
  marker, 0.006 µm (versus `Cnt.c` 0.07 µm outside it). This is the one
  relaxation seen with a number; it is the main source of the foundry cell's
  density.

Not surveyed: the full list of rules the marker scopes, and whether
`klt drc --deck sg13g2` honours it (the curated deck's `activ.enclosing.cont.1`
description says Activ is joined with Activ.mask; it does not mention the
marker). Drawing the cell with and without the marker is therefore not
possible: with no marker drawn, only the ordinary rules apply, and that is the
single DRC result recorded. A marker-using cell is future work for a density
pass and needs its own decision record.
