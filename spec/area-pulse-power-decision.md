# Decision record: area, minimum clock pulse, power and retention rows

**Status**: Proposed, 2026-10-29 (not self-ratified)
**Resolves**: #74, "spec: no area target, min-clock-pulse, power or retention rows"
(market-key findings F2, F3 from the #37 ratification review)
**Origin**: `gf180-sram` `spec/sram.md` @ `d0bacc0` has no area, minimum
clock pulse or power row either (checked 2026-10-29); its hold SNM bullet is
the only retention statement. Finding filed on the origin: 2AMLogic/gf180-sram#293.

## Question

`spec/sram.md` records the comparison macro's area and minimum clock pulse in
its Reference table but sets no row for either, and has no power or retention
row. For each of area, minimum clock pulse, power and retention: is there a
target / stretch, or is the quantity recorded with no pass threshold?

## Answer

Same form as access time ("Recorded, no pass threshold"): all four are
**recorded, no pass threshold** at the canary tier. No numeric target is set
for any of them. The comp figures are the reference scale, not a target.

| Quantity | Form | Measured where | Pass threshold |
|---|---|---|---|
| Area | recorded | drawn array layout (GDS/LEF) | none; reference scale only |
| Minimum clock pulse | recorded, Liberty output only | Liberty characterization | none |
| Power | open item, not measured | characterization issue (not yet filed) | none |
| Retention | covered by hold SNM; data-retention voltage is an open item | hold SNM bench | hold SNM > 0 (existing row) |

## Rationale

### Area

1. The unit is stated first: **macro area (µm²) is the recorded figure**, with
   **area per bit** (macro area / 8,192) and **bitcell area** recorded
   alongside, so a buyer can compare at any of the three levels.
2. Comp figures, per the `spec/sram.md` Reference table (read 2026-10-17, and
   marked unverified against primary Liberty/LEF by #76): macro
   49,488.5 µm², 6.04 µm²/bit, bitcell 3.50 µm², array efficiency about 58%.
3. A numeric target would have to come from drawn geometry. The bitcell here
   is a custom 6T on `sg13_lv_*` devices whose area is unmeasured
   (`spec/bitcell-decision.md` already expects it to be larger than 3.50 µm²
   and says the ratio is "recorded, not required"). Setting "at most comp
   6.04 µm²/bit" now would pre-judge a layout that does not exist, and would
   fail or pass on an assumed array efficiency. Rejected.
4. Once the array layout exists, a numeric area target may be proposed by a
   new decision record, derived from the drawn bitcell and the measured
   array efficiency. Until then the repo neither claims nor fails area, and
   the recorded ratio to the comp is the statement a buyer gets.

### Minimum clock pulse

1. Comp Liberty `A_CLK` minimum pulse width: 0.12 / 0.21 / 0.40 ns (fast /
   typ / slow), per the Reference table.
2. It is a **Liberty-characterized output, recorded**, not a spec row with a
   threshold. It is a property of the periphery's clock path, which does not
   exist yet, and the spec's timing stance is that no independent macro timing
   target is ratified (`spec/write-pulse-width-decision.md`).
3. Relation to the fixed 1 ns write pulse: the write pulse is the
   **testbench wordline window** used to measure write margin; the minimum
   clock pulse is the **narrowest clock high time the finished macro is
   characterized to accept**. They are different quantities. The comp's
   slowest minimum pulse (0.40 ns) is below 1 ns, so the comp does not
   contradict the 1 ns window. When the macro's own minimum clock pulse is
   characterized, it is recorded next to the write pulse; if the write needs
   more than the characterized minimum pulse allows, that is reported as a
   finding, not absorbed by editing either number.

### Power

Not measured, and no value is invented. Power is **recorded, with no pass
threshold**, and is an open item. A measurable definition, to be applied by
the characterization issue that owns Liberty power tables:

- Dynamic: energy per read and per write access, from the same column or
  array testbench that produces access time.
- Leakage: standby supply current with `CEN` deasserted, array holding data.
- Corners: the 45-corner set in `spec/sram.md`; leakage is worst at
  `mos_ff`, 125 °C, 1.32 V, which must be among those recorded.

The comp's Liberty power tables have not been read into the Reference table,
so no comparison figure is quoted here. Marked: **comp power not read; this
repo's power not measured.**

### Retention

"Retention" is split into two meanings so neither is dropped:

1. **Hold stability** is already a spec row: hold SNM, strictly positive at
   every corner, plus Monte Carlo (`spec/sram.md`, "What must be measured").
   That is the retention row for the supply range the spec covers.
2. **Data-retention voltage** (the lowest supply at which the cell holds)
   and any retention-mode/low-power rail are **non-goals for the canary
   tier**: the spec has one supply range, 1.08-1.32 V, and no sleep mode.
   Recorded as an open item, not a target.

## Open items

| Item | Status | Owner |
|---|---|---|
| Numeric area target | open; proposed only after the array layout gives drawn area and array efficiency | array layout issue |
| Macro minimum clock pulse | open, Liberty characterization output | Liberty generation issue |
| Dynamic and leakage power | open, not measured | characterization issue |
| Data-retention voltage | non-goal at the canary tier | none |

## What this record changes

`spec/sram.md` gains one "Recorded" bullet in "What must be measured" for
area, minimum clock pulse and power, a retention note pointing at hold SNM,
and open-item rows. `spec/sram.md` stays Proposed; no ratified row is
relaxed and the Reference table is not edited.

Wording note: "recorded, no pass threshold" is the same form as the access
time row. #73 asks whether that form is acceptable for access time; if #73
lands first, this record follows its wording.

## References

- `spec/sram.md` Reference table; `spec/bitcell-decision.md`;
  `spec/write-pulse-width-decision.md`
- `gf180-sram` `spec/sram.md` @ `d0bacc0`; origin finding filed as 2AMLogic/gf180-sram#293
- #73 (access time), #75 (view and corner scope), #76 (comp verification)
