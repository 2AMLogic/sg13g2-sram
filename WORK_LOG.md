# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide
triage agent. Newest first.

### 2026-11-19

- **PR #220**: docs: record the item 9 roadmap block as discharged at the 0.9.2 pin
- **PR #218**: docs: align three live signoff-pin cross-references with committed provenance
- **PR #216**: docs: align layout/ signoff-pin prose with the 0.9.2 pin; drop mint.sh pin-sync line numbers for a grep
- **PR #215**: docs: pin README.md out of Guide docs maintenance; document item-10 re-sign policy
- **PR #214**: fix: decide mint --skip-local-only from inventory content, not text
- **Issue #219** (closed): Reassess the roadmap’s item 9 blocker against the 0.9.2 refresh and the three held PRs
- **Issue #217** (closed): Three live 0.8.0 signoff-pin cross-references remain outside #212's three-file scope
- **Issue #212** (closed): Pin bump to 0.9.2 left stale 0.8.0 signoff-pin prose in layout/ and stale line numbers in mint.sh's pin_sync_set()
- **Issue #211** (closed): attest/mint.sh gates --skip-local-only on a textual grep of inventory JSON formatting
- **Issue #152** (closed): Pin README.md in Guide docs maintenance and document the item-10 re-sign procedure
- **PR #178**: chore: bump the signoff klayout-tools pin to 0.9.2 and refresh the attestation evidence
- **Issue #172** (closed): Bump CI's KLT_VERSION pin from 0.8.0 to 0.9.2 so attestation envelopes can be regenerated without a fleet submit

### 2026-11-18

- **PR #204**: ci: add merge_group trigger to the required-check workflows
- **Issue #203** (closed): Merge queue: add the merge_group trigger to the required-check workflow(s)

### 2026-11-17

- **PR #200**: chore: remove superseded generate-macro-decoder.sh, repoint README at the blbm script
- **Issue #199** (closed): Remove generate-macro-decoder.sh: superseded by generate-macro-blbm.sh, and README points at it
- **PR #197**: chore(loom): resync installed Loom to v0.19.1306
- **PR #196**: docs: explain klayout_version_mismatch on drc-macro.json in layout README
- **Issue #195** (closed): drc-macro.json is the first record minted with klayout_version_mismatch: true (host klayout 0.30.13 vs klt expecting 0.30.12)
- **PR #194**: layout: join the column_mux BLBM net, the last undrawn leaf-cell net
- **Issue #159** (closed): layout: join the column_mux BLBM net, the one undrawn leaf-cell net

### 2026-11-16

- **PR #189**: chore(loom): resync installed Loom to v0.19.1302

### 2026-11-15

- **PR #185**: test: pin obstacle clear-side probes to the 0.22 margin boundary
- **Issue #184** (closed): Obstacle margin assertions pin clear/clear3 to (0.21, 0.23], not exactly 0.22
- **PR #183**: test: pin obstacle M2/M3 spacing margins with boundary assertions
- **PR #180**: fix: scope new_record's cleanup trap to the caller's declared scratch requests
- **PR #179**: fix: reject an aimed MazeRouter.connect whose goal set is not the singleton toward
- **Issue #182** (closed): attest/mint.sh refuses to re-mint items 1/9; its blocker lifted in klayout-tools 0.9.2
- **Issue #176** (closed): test_obstacle_clear3_and_cross_layer_independence does not pin clear3's M3.b spacing margin
- **Issue #173** (closed): MazeRouter.connect: guard that `toward` is consistent with `goals`
- **Issue #171** (closed): new_record's cleanup trap uses a directory-wide .*.json glob, so two run scripts sharing a sim/ directory can delete each other's in-flight scratch request
- **PR #170**: layout: remove 6 dead rule constants from the layout generators
- **PR #175**: docs: align README status, maturity ladder and repro steps with the signoff record
- **PR #174**: refactor: extract the rails obstacle model and unify the tie-to-lane search
- **Issue #167** (closed): Remove 6 dead rule constants from the layout generators: 3 restate a value a live constant's comment already carries
- **Issue #161** (closed): docs: README status says no layout exists; bring it in line with the signoff record
- **Issue #163** (closed): Gen.rails is 222 lines of closure scope: tie-to-lane search written twice, tie_maze takes 16 parameters to borrow it
- **PR #162**: refactor(router): one maze search for both of route_net's modes
- **PR #158**: docs: roadmap as of 2026-11-13
- **Issue #154** (closed): Unify MazeRouter.connect and connect_to: ~30 lines of the search loop are duplicated verbatim

### 2026-11-14

- **PR #169**: docs: state WORK_PLAN.md snapshot semantics in header prose
- **PR #168**: feat(attest): add pinned mint script for item 10 attestation envelope
- **PR #166**: test(layout): record klt array-check on the macro array and assert it in verify.sh
- **PR #164**: refactor(sim): fold duplicated run-script scaffolding into harness/common
- **Issue #160** (closed): layout: run klt array-check on the macro and commit the report
- **Issue #157** (closed): Consolidate the duplicated setup, record-dir and batch-submit scaffolding across sim/*/run_*.sh
- **Issue #156** (closed): WORK_PLAN.md header calls a stale snapshot "current" label state (the generator is measured correct)
- **Issue #155** (closed): Add a pinned mint script for the attest/ attestation envelopes
- **Issue #153** (closed): CI: a README.md edit breaks the item-10 attestation, so the docs lane deadlocks
- **Issue #105** (closed): layout: route decoder cell internals

### 2026-11-12

- **PR #148**: Bump Repo Skills 0.25.10 -> 0.26.1

### 2026-11-07

- **PR #143**: Bump Repo Skills 0.25.1 -> 0.25.10

### 2026-11-06

- **PR #141**: ci: run layout generator tests in CI
- **PR #139**: chore: remove superseded per-stage macro-record scripts
- **Issue #140** (closed): Run the layout generator tests (test_bitcell.py, test_macro.py) in CI
- **Issue #117** (closed): Remove superseded macro-record scripts generate-macro-routed.sh and generate-macro-rails.sh
- **Issue #102** (closed): Re-plan supply-rail routing around the wordline fan-out gap (PR #99 vs #94/#97)

### 2026-11-05

- **PR #136**: docs: remove column INVENTORY.md duplicated by attest/item1.json
- **Issue #135** (closed): Remove design/column/INVENTORY.md: merged into attest/item1.json by #24

### 2026-11-04

- **PR #82**: docs(spec): propose physical organization and wire-RC check
- **Issue #70** (closed): spec: no wire-RC check or physical organization
- **PR #85**: docs: propose access-time pass threshold relative to the shipped comp
- **Issue #73** (closed): spec: no access-time target value

### 2026-11-01

- **PR #128**: docs: move Views row to Re-derived in porting plan
- **Issue #89** (closed): spec/porting-plan.md: Deliverables row still says inherited after views decision
- **PR #79**: docs: record Verilog/CDL as target views and Liberty at all 45 corners
- **Issue #75** (closed): spec: Verilog and CDL views are only stretch; Liberty corner count unspecified
- **PR #123**: Bump Repo Skills 0.24.7 -> 0.25.1

### 2026-10-31

- **PR #121**: feat: route the decoder nets on main's router, one HIER_ROUTED for eight cells
- **Issue #119** (closed): Rebase decoder-net routing (PR #116) onto main's leaf-cell router

### 2026-10-30

- **PR #115**: feat: route latch and control nets between leaf cells
- **Issue #106** (closed): layout: route latch and control block internals
- **PR #112**: feat: net-aware Metal2/Metal3 router and leaf-cell signal nets with flat-net resolution
- **Issue #104** (closed): layout: signal router core, flat-net resolution and leaf-cell nets
- **PR #110**: chore: remove generate-macro.sh, which always refuses to run
- **Issue #100** (closed): Remove layout/reports/generate-macro.sh: always refuses to run
- **PR #99**: feat: wire periphery ties and bitcell risers to VDD/VSS rails
- **Issue #92** (closed): layout: macro supply rails and tie-to-rail connection
- **PR #91**: fix: clear macro NWell spacing and add full-array DRC evidence for item 3
- **Issue #29** (closed): T1 item 3 (DRC clean): klt drc on the full macro with coverage disclosed
- **PR #97**: feat: route macro wordlines and bit lines between array and periphery
- **Issue #94** (closed): layout: macro array-to-column-path and wordline routing
- **PR #96**: feat: add per-device body ties to the macro periphery
- **Issue #93** (closed): layout: macro supply rails and tie-to-rail connection
- **PR #83**: docs: verify SRAM comp row against primary Liberty/LEF/datasheet
- **Issue #76** (closed): spec: verify comp data against primary Liberty/LEF
- **PR #87**: feat: add SG13G2 macro layout generator, GDS, LEF and item 2 attestation
- **Issue #28** (closed): T1 item 2 (layout): 256x32 macro layout generator, GDS and LEF
- **PR #86**: feat: add SG13G2 6T bitcell generator with 2x2 tile and DRC/LVS evidence
- **Issue #27** (closed): T1 item 2 (layout): generated 6T bitcell layout with cell-level DRC/LVS pre-check

### 2026-10-28

- **PR #65**: refactor: share one run_klt helper across the sim run scripts
- **Issue #61** (closed): Consolidate duplicated run_klt helper across sim/*/run_*.sh (3 diverging copies)
- **PR #63**: docs: link gf180-sram issue for parents[2] default-root finding
- **Issue #62** (closed): Follow-on from PR #59: file the common/ layout parents[2] finding on gf180-sram
- **PR #60**: chore: drop unused vendored env_provenance.py and record departure
- **Issue #33** (closed): Remove env_provenance.py: dead vendored gf180 helper with no callers
- **PR #59**: chore: remove unrunnable vendored sign-off tooling and record the departure
- **Issue #36** (closed): Remove mint_sim_envelope.py and render_signoff_table.py: unrunnable vendored gf180 sign-off tooling (~660 LOC)
- **PR #58**: chore: drop vendored design-evidence-tiers.md, use klt-bundled copy
- **Issue #41** (closed): Remove vendored design-evidence-tiers.md: klt 0.8.0 bundles it (~1055 LOC)
- **PR #55**: feat: add array-level benches, testbench inventory and item 9 attestation
- **Issue #26** (closed): T1 item 9 (testbenches shipped): array read/write and access-time benches, inventory and --attest 9
- **PR #53**: feat: decoder, control, latch and macro-top schematics with item 1 attestation
- **Issue #24** (closed): T1 item 1 (design sources): row decoder, control timing and 256x32 macro top netlist + attest 1
- **PR #51**: feat: record write-driver width sweep and justify driver sizing
- **Issue #23** (closed): T1 item 1 (design sources): column path schematics (precharge, column mux, sense amp, write driver)
- **PR #49**: feat: batch-set write-driver width sweep and sizing summary for the column
- **PR #47**: fix: define each column subckt once by including only column.spice in the benches
- **Issue #46** (closed): Remove duplicated sub-block subckt definitions in the column deck (benches include them twice)

### 2026-10-27

- **PR #45**: chore: alias check:ci to npm test to remove drifted duplicate chain
- **PR #44**: feat: per-pair precharge enables keep the unselected bit-line pair precharged
- **PR #42**: feat: record nominal column bench on the batch fleet; fix netlist cwd and comment wrapping
- **PR #40**: docs: install two-key ratification keys and open post-hoc review record
- **Issue #43** (closed): Column bench: unselected-mux bit lines collapse to ~0.07 V while WL is high (needs per-pair precharge enable)
- **Issue #38** (closed): Collapse package.json check:ci into 'npm test': hand-copied chain already drifted
- **PR #34**: feat: column path schematics, derived netlists and nominal bench (bench not yet run)
- **PR #32**: docs: README spec table, reproduction steps and item 10 attestation (klt 0.8.0)
- **Issue #25** (closed): T1 item 10 (repo hygiene): README reproduction steps and spec table, klt signoff --attest 10

### 2026-10-23

- **PR #21**: feat: 6T bitcell reference cell with hold/read SNM and write margin over 45 corners
- **Issue #18** (closed): design+sim: SG13G2 6T bitcell schematic and hold/read SNM + 1 ns write-margin bench (typical corner, then the 45-corner grid)
- **PR #6**: chore: vendor gf180-sram PDK-free harness via reuse.lock.json and test it in CI
- **PR #19**: ci: add klt signoff manifest and byte-compare workflow
- **Issue #4** (closed): Port of gf180-sram: take the PDK-independent sim harness and CI checkers by pinned reference (reuse.lock.json)
- **Issue #17** (closed): T1 item 10: commit a klt signoff block manifest, vendored checklist and a signoff CI job as the verdict of record

### 2026-10-21

- **PR #12**: Bump Repo Skills 0.24.3 -> 0.24.7

### 2026-10-19

- **PR #10**: refactor(sim): take OpenVAF tag from build-osdi.sh and drop duplicate pins in pdk.json
- **Issue #9** (closed): Remove duplicated osdi_toolchain block from sim/pdk.json: false 'not consumed' claim, second copy of vendored pins

### 2026-10-17

- **PR #8**: feat(sim): pin IHP-Open-PDK, vendor OSDI build, add four-device smoke record
- **PR #7**: docs(spec): propose SG13G2 SRAM spec, porting plan and bitcell decision
- **PR #1**: chore(loom): Install Loom 0.19.1181
- **Issue #5** (closed): T1 item 9: pin IHP-Open-PDK, adopt the sibling OSDI model build by pinned reference, and commit a smoke simulation
- **Issue #2** (closed): Draft and ratify the target spec
