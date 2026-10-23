# manifests

Graded signoff record for the `sg13g2-sram` block (tracker #3).

- `sg13g2-sram.json` - block manifest (`kind: analog`, per `spec/sram.md`). The `evidence` map is empty; no evidence is cited yet, so every item grades `unmet`.
- `design-evidence-tiers.md` - the T1-T4 checklist, vendored byte-identical from `docs/design-evidence-tiers.md` in `2AMLogic/klayout-tools` at commit `0e2362bda7309829398a35d54efaa989d5806065` (tag `v0.7.0`).
- `sg13g2-sram.signoff.json` - generated grader output; do not hand-edit. Regenerate from the repo root with:

      uvx --from "klayout-tools==0.7.0" klt signoff --manifest manifests/sg13g2-sram.json \
        --tiers-doc manifests/design-evidence-tiers.md --format json > manifests/sg13g2-sram.signoff.json

Graded with klayout-tools release `0.7.0`, pinned in `.github/workflows/signoff.yml`. Bump both together.
