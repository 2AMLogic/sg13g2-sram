# Decision record: `env_provenance.py` is not vendored from `gf180-sram`

**Status**: Operator-approved, 2026-10-28 (option a on #33)
**Resolves**: #33, "Remove env_provenance.py: dead vendored gf180 helper with no callers"
**Origin**: `gf180-sram` `sim/lib/env_provenance.py` @ `d0bacc0`
(departure from `spec/porting-plan.md`, sim harness row)

## Question

`spec/porting-plan.md` listed `env_provenance.py` among the sim harness files
taken from the origin by pinned reference, and #4 vendored it. Should it stay?

## Answer

**No. The file is removed and its `reuse.lock.json` entry dropped.**

- No caller exists in this repo. Its only function, `pdk_identity`, is not
  imported anywhere; `mint_sim_envelope.py` imports only `render_signoff_table`.
- It classifies a gf180mcu PDK install; this repo is SG13G2.
- Its stated reason to exist (the pinned `klt` lacked `env-provenance`) is
  stale: the worker's `klt` provides `klt env-provenance`, and
  `klayout_tools.env_provenance` is importable.

If a harness here later needs environment provenance, it calls
`klt env-provenance emit` rather than a vendored copy.

## Consequences

- Pinned-origin parity is given up for this one file; every other harness file
  stays by pinned reference.
- The origin carries the same dead, stale-claim copy. That finding belongs on
  `gf180-sram` (CLAUDE.md origin rule) and is not filed by this change.
