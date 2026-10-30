# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide
triage agent. Newest first.

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
