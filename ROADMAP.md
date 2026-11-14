# Roadmap

A 1 kB (256 x 32) single-port SRAM macro on IHP SG13G2, ported from `gf180-sram`
with the PDK as the variable; the array, macro LVS and view generation are the
tool surface under test.

Status as of 2026-11-13, `main` @ `4e5fd29`. Issue and PR states are as read from
the tracker on that date. `WORK_PLAN.md` is the generated label view; this file
says what the work is and what holds it.

## Where it stands

`manifests/sg13g2-sram.signoff.json` (klayout-tools 0.8.0) is the verdict of
record: **5 of 11 T1 items met, `tier: null`.**

| T1 item | Grade | Evidence or gap |
|---|---|---|
| 1 Design sources | met | `design/` schematics and netlists up to `design/macro/macro.spice`; `attest/item1.envelope.json` (#24) |
| 2 Layout | met | generated `layout/sram_256x32/macro.gds`, LEF, socket; `attest/item2.envelope.json` (#27, #28) |
| 3 DRC clean | met | `layout/reports/drc-macro.json`: clean, 42 rules checked, 20 skipped for lack of geometry, coverage gaps listed in `layout/README.md` (#29) |
| 4 LVS clean | unmet | macro is partly routed, so not LVS-able (#30) |
| 5 Corners vs a ratified spec | unmet | 45-corner records exist (`sim/bitcell/records/`, `sim/array/records/`) but `spec/sram.md` is Proposed, not ratified |
| 6 Monte Carlo | unmet | no campaign recorded (#68) |
| 7 Post-layout verification | unmet | needs item 4 |
| 8 Characterization report | unmet | needs items 5 to 7 |
| 9 Testbenches shipped | met | `attest/item9.envelope.json`, cold start `sim/run_all.sh` (#26) |
| 10 Repo hygiene | met | `attest/item10.envelope.json` (#25) |
| 11 Power delivery | unmet | needs item 4 and a `klt erc` supply spec (#31) |

Schematic-level results (no parasitics, `sim/array/README.md`): all 45 corners
pass; worst in-situ read SNM 145 mV, worst write margin 250 mV, slowest
read-of-1 access 3.2241 ns.

Layout, per `layout/reports/macro-record-decoder.json`: wordlines and bit lines
wired to the periphery (#94), per-device body ties and Metal4/Metal5 supply rails
(#92, #102), leaf-cell nets (#104), latch and control nets (#106) and decoder
nets (PR #121): 114 hierarchical nets routed, none undrawn. `not_drawn`: signal
nets between blocks, inter-block fan-out, signal pin routing, VDD/VSS pin
connection to the rails, and `column_mux` `BLBM`. Size 417.88 x 616.395 um
(257,579 um2, about 5.2x the shipped macro's 49,488.5 um2; recorded, no
threshold).

On the README's maturity ladder the repo is past "array assembled" in layout
terms but formally still at "spec proposed": the two-key review on #37 returned
EE `request-changes` and market `uncompetitive`, and the findings are the spec
issues below.

## Now

Can start today. None of these touches a file in `attest/item9.json` (see
Blocked and waiting for why that matters).

1. **Route global control fan-out and per-slice DL/DOUT** (#107). Done when the
   nets named in #107 are each one connected net with no short under
   `klt extract`, a slice-0-to-slice-31 net has a test with teeth, and
   `./layout/verify.sh` passes. Its cited blockers are cleared in the tree
   (#104 and #106 closed; #105's decoder routing landed as PR #121), but the
   issue still carries `loom:blocked` because #105 is open.
2. **Join `column_mux` `BLBM`**, the one undrawn leaf net
   (`test_macro.py` asserts it as the known gap). Done when the undrawn set is
   empty in a new append-only macro record and macro DRC is still clean. No
   issue yet (seed 1). Same file as #107: land one, rebase the other.
3. **Run `klt array-check` on the macro.** `layout/README.md` lists it as unrun.
   Done when a report is committed under `layout/reports/` and the README
   sentence is corrected, or the tool gap is filed on klayout-tools. No issue
   yet (seed 2).
4. **Bring `README.md` status up to date.** It still says "No layout, array or
   periphery exists yet". Done when the Status paragraph and ladder position
   match the signoff record and `attest/item10.envelope.json` is regenerated
   (README is a hashed hygiene file; the item 10 checks are PDK-free). No issue
   yet (seed 3).

## Next

- **Connect macro pins, signals record, verify, README** (#108): after #107.
  Done when every pin square is on its labelled net, VDD/VSS reach the rails,
  and a signals record lists expected vs connected nets. Closes #95 and #88.
- **Layout pins for per-bit `WEN[31:0]`**: after PR #130 (netlist) merges; the
  generator and LEF draw one `WEN` pin today. Needs an issue, or #108 rescoped.
- **Macro LVS, T1 item 4** (#30): after #108. Done when `klt lvs` of the
  extracted macro against `design/macro/macro.spice` reports `status: match`
  with `power_connectivity` not `mismatch`, and item 4 grades `met`.
- **Power delivery, T1 item 11** (#31): after #30. Done when the `klt erc`
  supply spec runs with zero blocking findings and item 11 grades `met`.
- **Monte Carlo for the margin rows, T1 item 6** (#68): harness is on branch
  `feature/issue-68`; needs the batch backend (below) and `klt yield`. Done when
  a seeded campaign with a negative control and a yield report is recorded.
- **Bitcell and macro post-layout re-run, T1 item 7**: after #30 and the batch
  backend. Done when the spec benches are re-run on the extracted netlist and
  recorded beside the schematic results.
- **Wordline and bit-line wire-RC check** (`spec/wordline-rc-decision.md`, open
  item in `spec/sram.md`): after extraction with parasitics is available on the
  routed macro.

## Later

- **Spec ratification (an operator step), then T1 items 5 and 8.** Question
  first: do the open spec PRs resolve the EE and market findings on #37?
- **Liberty at all 45 corners, CDL and Verilog views.** Question first: can the
  klt Liberty flow emit more than one corner per run, and can it characterize a
  sequential macro (`spec/views-and-liberty-corners-decision.md`, #126)?
- **PDK-native DRC against the curated deck.** Question first: where can
  KLayout >= 0.29.11 run for this repo (`layout/README.md`, coverage gaps)?
- **Area.** The macro is about 5.2x the shipped one and the bitcell 2.96x the
  reference cell. Question first: is an area target adopted (#74, PR #80)?

## Blocked and waiting

- **Item 9 re-attestation is not possible under the current pin.** CI pins
  klayout-tools 0.8.0; the batch backend's runners now carry 0.9.0 and the
  0.8.0 client refuses the version skew (operator note on PR #130, 2026-11-06,
  which lists three ways out). Until one is chosen, any change to a file in
  `attest/item9.json` leaves `signoff` red. Held on this: PR #64 (#56),
  PR #84 (#69), PR #130 (#126).
- **Spec PRs parked since 2026-10-29**: #77 (#37), #78 (#72), #80 (#74),
  #81 (#71, now conflicting with `main`). They were parked because CI could not
  start; CI on `main` is green as of 2026-11-13, so they need a re-run and a
  review, not new work.
- **Tracker state to clear by hand**: PR #116 is superseded by merged PR #121
  and awaits closing; #105 stays open and `loom:building` behind it, which is
  what keeps #107 labelled blocked. Tracker #3's checklist body predates the
  signoff record and still reads all items unmet.

## Not planned

- Wrapping or copying the shipped `sg13g2_sram` macro or its `BITKIT_*` cells;
  it is the comparison point only.
- BIST and the foundry macro's pin interface.
- Reimplementing a free SRAM generator; a parameterized generator and a 1RW1R
  port are stretch rows, after the fixed instance is DRC/LVS clean.
