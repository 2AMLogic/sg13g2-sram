# Decision record: internal-consistency edits to `spec/sram.md`

**Status**: Proposed. Clarifying edits only; `spec/sram.md` stays Proposed.
**Issue**: #72 (EE-key findings F5 a-c and F6, from the review in #37)
**Edited from**: `spec/sram.md` @ `2597199`

## Edits

1. **F5a, corner-set prose.** "The three process-corner names above" now reads
   "five", matching the five `mos_*` corners in the Corner-set table.
2. **F5b, Signoff definition.** States that read SNM, hold SNM and write
   margin also carry Monte Carlo evidence per "Statistical treatment",
   matching the Margins row. No numbers restated; no `target_yield`.
3. **F5c, Open items.** Two rows added: confirmation of the 1 ns write pulse
   (flip time and sensitivity sweep, unrun), and the choice of Monte Carlo
   mismatch parameters.
4. **F6, typical point.** The Temperature row marks 25 °C as the typical
   point, matching the shipped typ Liberty and the 45-corner grid.

## Not changed

No row status, threshold, corner set or the 1 ns pulse. No `sim/` edit.

## Known discrepancy

`sim/bitcell/README.md:54` and `sim/bitcell/bitcell_post.py:104` label the
bitcell "typical" point 27 °C. `sim/` is append-only evidence, so it is left
as is; the 27 °C label is a recorded discrepancy against the spec's 25 °C.

## Effect on #37

The text under review in #37 has changed since `2597199`. The EE key's
"unchanged since 2597199" check (`spec/ratification-review-decision.md`, open
question 3) must be re-run against the commit that contains these edits.
