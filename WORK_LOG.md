# Work Log

Chronological record of merged PRs and closed issues, maintained by the Guide
triage agent. Newest first.

### 2026-10-27

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
