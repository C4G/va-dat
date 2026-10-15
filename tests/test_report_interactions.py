"""Exercise the stakeholder's standalone report through the CLI and browser.

Set REPORT_BROWSER_MODULES to a directory containing Playwright, and
REPORT_BROWSER_EXECUTABLE to a Chromium executable to run these optional checks.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_full_report import (
    completed_review,
    full_workspace,
    report_all,
    review_rows,
    save_review,
)

# Re-export the synthetic saved-evidence fixtures for pytest discovery.
__all__ = ["completed_review", "full_workspace"]


@pytest.mark.parametrize("behavior", ["search", "filters", "disclosures", "print"])
def test_offline_report_interactions(completed_review, tmp_path, behavior):
    """Users can investigate saved evidence without resources beside the HTML."""
    modules = os.environ.get("REPORT_BROWSER_MODULES")
    executable = os.environ.get("REPORT_BROWSER_EXECUTABLE")
    if not modules or not executable or not shutil.which("node"):
        pytest.skip("Set REPORT_BROWSER_MODULES and REPORT_BROWSER_EXECUTABLE for browser checks")
    if behavior == "print" and not shutil.which("pdftotext"):
        pytest.skip("Install pdftotext for PDF content checks")
    run, manifest = completed_review
    if behavior == "print":
        child = run / manifest["pages"][0]["run_dir"]
        decisions = review_rows(child)
        decisions[0]["review_notes"] = "Long evidence begins. " + " ".join(
            f"Saved review line {number}: keyboard evidence remains readable."
            for number in range(250)
        ) + " Long evidence ends."
        save_review(child, decisions)
    assert report_all(run) == 0
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    parent = standalone / "full" / "report.html"
    child = standalone / "page" / "report.html"
    parent.parent.mkdir()
    child.parent.mkdir()
    shutil.copyfile(run / "report.html", parent)
    shutil.copyfile(run / manifest["pages"][0]["run_dir"] / "report.html", child)
    subprocess.run(
        ["node", str(Path(__file__).with_name("report_interactions.cjs")),
         behavior, str(parent), str(child)], check=True, timeout=60,
    )
