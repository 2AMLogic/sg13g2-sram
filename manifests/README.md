# manifests

Graded signoff record for the `sg13g2-sram` block (tracker #3).

- `sg13g2-sram.json` - block manifest (`kind: analog`, per `spec/sram.md`). `evidence["1"]`, `evidence["9"]` and `evidence["10"]` cite the item 1, 9 and 10 attestation envelopes (`attest/item1.envelope.json`, `attest/item9.envelope.json`, `attest/item10.envelope.json`; the pinned `content_hash` is the inventory's); every other item is uncited and grades `unmet`.
- `design-evidence-tiers.md` - the T1-T4 checklist, vendored byte-identical from `docs/design-evidence-tiers.md` in `2AMLogic/klayout-tools` at commit `c572046be644e0407f693f2410f3abb799d68a3a` (tag `v0.8.0`).
- `sg13g2-sram.signoff.json` - generated grader output; do not hand-edit. Regenerate from the repo root with:

      uvx --from "klayout-tools==0.8.0" klt signoff --manifest manifests/sg13g2-sram.json \
        --tiers-doc manifests/design-evidence-tiers.md --format json > manifests/sg13g2-sram.signoff.json

Graded with klayout-tools release `0.8.0`, pinned in `.github/workflows/signoff.yml`. Bump both together.
