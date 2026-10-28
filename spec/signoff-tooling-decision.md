# Decision record: gf180-sram sign-off envelope and table tooling is not ported

**Status**: Approved by operator ruling on #36, 2026-10-28
**Resolves**: #36, "Remove mint_sim_envelope.py and render_signoff_table.py"
**Origin**: `gf180-sram` `sim/lib/mint_sim_envelope.py` and
`sim/lib/render_signoff_table.py`, vendored by #4

## Question

`spec/porting-plan.md` lists the sim harness as imported by pinned
reference, including `mint_sim_envelope.py` and `render_signoff_table.py`.
Should these two files stay vendored?

## Answer

**No. This is a departure from the porting plan.** Both files are removed
from `sim/lib/common/` and from `reuse.lock.json`. The rest of the harness
row is unchanged.

## Rationale

1. Nothing in this repo calls them. `package.json` and `.github/workflows/`
   never invoke them; the only link is `mint_sim_envelope.py` importing
   `render_signoff_table`.
2. They read per-claim `records` directories (read-snm, hold-snm,
   write-margin, access-time) under `sim/`. None exist here, so there is
   nothing to render or mint from.
3. Both default the repo root to `Path(__file__).resolve().parents[2]`,
   which is correct at upstream `sim/lib/` but resolves to `sim/` at the
   relocated `sim/lib/common/` path.
4. Neither has a test or CI check here, so keeping them would keep
   unverifiable code.

## Consequences

- Pinned-origin parity is given up for these two files only.
- Re-import from `gf180-sram` and adapt to this repo's `sim/<block>/records`
  layout when a multi-record corner sweep exists to render.
- `env_provenance.py` is out of scope (see #33).
- Origin finding, filed as `2AMLogic/gf180-sram#287`
  (https://github.com/2AMLogic/gf180-sram/issues/287): the `parents[2]` default
  root is wrong for a `sim/lib/common/` layout.
