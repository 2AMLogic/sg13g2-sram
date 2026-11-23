"""Negative controls: the ``klt erc`` supply spec must have teeth (issue #229).

Runs the two single-defect variants of the committed ``macro.gds`` built by
``erc_controls.py`` through ``klt erc`` and asserts each produces exactly its
injected finding, against the as-built baseline read from the committed report
``layout/reports/erc-macro.json`` (append-only evidence -- a layout change
mints a new report and the baseline follows it):

* **severed** (VSS Metal5 trunk cut once): ``erc.unconnected_net`` island count
  for VSS rises by exactly one (the rail network splits in two; both halves
  stay labelled, so nothing goes unlabelled), VDD is untouched and no tie goes
  missing -- the control differs from as-built by the cut and nothing else.
* **no_tie** (bitcell n-well tie removed): ``erc.missing_tie`` fires on
  ``nwell_vdd`` (the array's merged n-well bands have no tap left), while the
  VDD/VSS island counts stay at the as-built values.

The unmodified macro's own expectations (two ``erc.unconnected_net`` findings,
no short, no missing tie, nothing unlabelled) are asserted from the committed
report first, so a regenerating drift cannot silently defang the controls.

    cd layout/sram_256x32 && uv run --with pytest --with klayout pytest -q test_erc_controls.py

Needs ``klt`` on PATH (CI installs the pinned ``klayout-tools``); falls back to
``uvx --from klayout-tools==0.9.2`` when it is absent.
"""

import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import erc_controls  # noqa: E402
import generate as g  # noqa: E402

def _pinned_klt_version() -> str:
    """The klt version the committed report was minted with (its provenance)."""
    with open(os.path.join(ROOT, ".github", "workflows", "signoff.yml")) as f:
        m = re.search(r'^\s*KLT_VERSION:\s*"([^"]+)"', f.read(), re.M)
    assert m, "KLT_VERSION not found in signoff.yml"
    return m.group(1)


# Always the signoff pin, never whichever klt happens to be on PATH.
KLT = ["uvx", "--from", f"klayout-tools=={_pinned_klt_version()}", "klt"]

SPEC = os.path.join(HERE, "macro.supply.json")
AS_BUILT_REPORT = os.path.join(ROOT, "layout", "reports", "erc-macro.json")


def _run_erc(gds: str) -> dict:
    proc = subprocess.run(
        KLT + [
            "erc", gds, SPEC,
            "--top", "macro", "--deck", "sg13g2",
            "--findings-only", "--compact", "--omit-antenna-tables",
            "--format", "json",
        ],
        capture_output=True,
        text=True,
    )
    # 3 = erc findings present (the expected verdict for every run here);
    # 0 = clean. Anything else (or no JSON) is a tool failure, not a verdict.
    assert proc.returncode in (0, 3), f"klt erc exited {proc.returncode}: {proc.stderr}"
    return json.loads(proc.stdout)


def _islands(report: dict, net: str) -> int:
    return next(n["matched_islands"] for n in report["nets"] if n["name"] == net)


def _unlabelled(report: dict, net: str) -> int:
    return next(n["unlabelled_islands"] for n in report["nets"] if n["name"] == net)


@pytest.fixture(scope="module")
def variant_dir(tmp_path_factory) -> str:
    outdir = str(tmp_path_factory.mktemp("erc-variants"))
    erc_controls.build_variants(g.GDS_PATH, outdir)
    return outdir


@pytest.fixture(scope="module")
def as_built() -> dict:
    with open(AS_BUILT_REPORT) as f:
        return json.load(f)


def test_as_built_report_is_the_expected_honest_result(as_built):
    """Two unconnected-net findings (rails + pin squares + the un-joined supply
    S/D terminal bars), no short, no missing tie, nothing unlabelled."""
    assert as_built["erc_status"] == "violations"
    rules = [f["rule"] for f in as_built["erc_findings"]]
    assert rules == ["erc.unconnected_net", "erc.unconnected_net"]
    assert {f["net"] for f in as_built["erc_findings"]} == {"VDD", "VSS"}
    # more than rail + pin square on each: the supply S/D terminal fragments
    # (generate.py "What is NOT drawn") are counted, not suppressed
    for net in ("VDD", "VSS"):
        assert _islands(as_built, net) >= 3
        assert _unlabelled(as_built, net) == 0
    for cov in ("skipped", "inapplicable"):
        assert as_built["erc_coverage"][cov] == []


def test_supply_spec_is_current():
    """macro.supply.json is the output of supply_spec.py (derived from the
    generator constants), never hand-edited."""
    import supply_spec

    with open(SPEC) as f:
        committed = json.load(f)
    assert supply_spec.spec() == committed, (
        "macro.supply.json differs from supply_spec.py output -- re-run "
        "supply_spec.py and commit the result"
    )


def test_severed_trunk_is_one_more_vss_island(variant_dir, as_built):
    report = _run_erc(os.path.join(variant_dir, "macro-severed.gds"))
    assert _islands(report, "VSS") == _islands(as_built, "VSS") + 1
    assert _islands(report, "VDD") == _islands(as_built, "VDD")
    # the severed rail must produce the VSS finding itself, not only a count delta
    vss = [
        f for f in report["erc_findings"]
        if f["rule"] == "erc.unconnected_net" and f.get("net") == "VSS"
    ]
    assert vss, "the severed VSS trunk must produce an erc.unconnected_net finding on VSS"
    assert not [f for f in report["erc_findings"] if f["rule"] == "erc.missing_tie"]
    for net in ("VDD", "VSS"):
        assert _unlabelled(report, net) == 0


def test_removed_bitcell_tie_is_a_missing_tie(variant_dir, as_built):
    report = _run_erc(os.path.join(variant_dir, "macro-no-tie.gds"))
    missing = [f for f in report["erc_findings"] if f["rule"] == "erc.missing_tie"]
    assert missing, "the removed bitcell n-well tie must produce erc.missing_tie"
    assert {f["layer"] for f in missing} == {"nwell_vdd"}
    assert {f["net"] for f in missing} == {"VDD"}
    # the defect is isolated: the supply island picture is the as-built one
    assert _islands(report, "VDD") == _islands(as_built, "VDD")
    assert _islands(report, "VSS") == _islands(as_built, "VSS")


def test_tie_contact_without_diffusion_is_a_missing_tie(variant_dir, as_built):
    """A Cont (with its metal) over no Activ is not a body tie."""
    report = _run_erc(os.path.join(variant_dir, "macro-no-activ.gds"))
    missing = [f for f in report["erc_findings"] if f["rule"] == "erc.missing_tie"]
    assert missing, "a tie Cont without Activ must produce erc.missing_tie"
    assert {f["layer"] for f in missing} == {"nwell_vdd"}
    assert {f["net"] for f in missing} == {"VDD"}
    assert _islands(report, "VDD") == _islands(as_built, "VDD")
    assert _islands(report, "VSS") == _islands(as_built, "VSS")
