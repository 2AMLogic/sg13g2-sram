# SRAM macro comp data (public sources only)

Seeded 2026-10-27 from the one comparison part this repo has read first-hand: the PDK's shipped macro. Rows for other vendors' SRAM IP are **not** included: embedded SRAM compilers are licensed IP with no public datasheet or price, and no row is invented to fill the table. A market key reviewing a row this table does not cover researches public sources from scratch (`SKILL.md` Step 0) and notes the gap.

## Comparable parts

| Vendor | Part | Class | Organization | Area | Clock to output (typ) | Min clock pulse (typ) | Source |
|---|---|---|---|---|---|---|---|
| IHP | `RM_IHPSG13_1P_256x32_c2_bm_bist` | Foundry SRAM macro, 1 port, column mux 2, BIST and bit mask | 256 × 32 (1 kB) | 49,488.5 µm² (6.04 µm²/bit) | 3.050 ns (`cell_rise`, lowest slew/load entry, bit 0) | 0.21 ns | IHP-Open-PDK `libs.ref/sg13g2_sram/` datasheet, LEF and Liberty, as read in `spec/sram.md` "Reference row" |

Only three Liberty corners ship for it (1.32 V −55 °C, 1.20 V 25 °C, 1.08 V 125 °C); it is not a like-for-like of a dense PVT matrix. Free SRAM generators are references to cite, not comps to score against.

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://github.com/IHP-GmbH/IHP-Open-PDK (`ihp-sg13g2/libs.ref/sg13g2_sram/`) | Shipped macro organization, area, Liberty timing, corner list | read 2026-10-17 (per `spec/sram.md`); not re-fetched for this seed |
