# manifests

Graded signoff record for the `sg13g2-sram` block (tracker #3).

- `sg13g2-sram.json` - block manifest (`kind: analog`, per `spec/sram.md`). `evidence["1"]`, `evidence["2"]`, `evidence["3"]`, `evidence["9"]` and `evidence["10"]` cite the item 1, 3, 9 and 10 evidence (item 3 cites the `klt drc` report `layout/reports/drc-macro.json` directly, pinned to the macro GDS hash; `attest/item1.envelope.json`, `attest/item2.envelope.json` (the pinned `content_hash` is the macro GDS's; produced with `klt signoff --attest 2` from klayout-tools `ce6583fe`, which 0.8.0 lacks but 0.8.0 grades), `attest/item9.envelope.json`, `attest/item10.envelope.json`; the pinned `content_hash` is the inventory's); every other item is uncited and grades `unmet`.
- `sg13g2-sram.signoff.json` - generated grader output; do not hand-edit. Regenerate from the repo root with:

      uvx --from "klayout-tools==0.8.0" klt signoff --manifest manifests/sg13g2-sram.json \
        --format json > manifests/sg13g2-sram.signoff.json

The T1-T4 checklist is the one bundled with the pinned klayout-tools wheel (not vendored here).

Graded with klayout-tools release `0.8.0`, pinned in `.github/workflows/signoff.yml`. Bump both together.
