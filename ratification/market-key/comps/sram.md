# SRAM macro comp data (public sources only)

Seeded 2026-10-27 from the one comparison part this repo has read first-hand: the PDK's shipped macro. Rows for other vendors' SRAM IP are **not** included: embedded SRAM compilers are licensed IP with no public datasheet or price, and no row is invented to fill the table. A market key reviewing a row this table does not cover researches public sources from scratch (`SKILL.md` Step 0) and notes the gap.

## Comparable parts

| Vendor | Part | Class | Organization | Area | Clock to output (typ) | Min clock pulse (typ) | Source |
|---|---|---|---|---|---|---|---|
| IHP | `RM_IHPSG13_1P_256x32_c2_bm_bist` | Foundry SRAM macro, 1 port, column mux 2, BIST and bit mask | 256 × 32 (1 kB) | 49,488.5 µm² (6.04 µm²/bit) | 3.050 ns (`A_DOUT[31:0]` bus arc, `cell_rise`, `related_pin A_CLK`, first table entry; 1.20 V, 25 °C) | 0.21 ns | IHP-Open-PDK `v0.3.0` (`sim/pdk.json` pin), `libs.ref/sg13g2_sram/`: `doc/RM_IHPSG13_1P_256x32_c2_bm_bist.txt`, `lef/RM_IHPSG13_1P_256x32_c2_bm_bist.lef`, `lib/RM_IHPSG13_1P_256x32_c2_bm_bist_{fast_1p32V_m55C,typ_1p20V_25C,slow_1p08V_125C}.lib`. Verified against primary files 2026-10-29. |

Only three Liberty corners ship for it (1.32 V −55 °C, 1.20 V 25 °C, 1.08 V 125 °C); it is not a like-for-like of a dense PVT matrix. Typ `cell_rise` first entries across the three corners: fast 1.876 ns, typ 3.050 ns, slow 5.126 ns; `min_pulse_width` on `A_CLK`: 0.12 / 0.21 / 0.4 ns. Area is the LEF `SIZE 416.64 BY 118.78` and Liberty `area : 49488.4992`, identical in all three libs. Not re-read in this pass and **inherited from `spec/sram.md`, not re-read**: bitcell area (3.50 µm²), array efficiency (58 %), the `A_BM`/BIST port list. Free SRAM generators are references to cite, not comps to score against.

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://github.com/IHP-GmbH/IHP-Open-PDK (`ihp-sg13g2/libs.ref/sg13g2_sram/`) | Shipped macro organization, area, Liberty timing, corner list | values re-read from the primary datasheet, LEF and Liberty files on 2026-10-29 (PDK `v0.3.0`; datasheet "Generated on Thu Aug 21 20:49:09 2025"), not copied from `spec/sram.md`; originally read 2026-10-17 |
