"""Exercise the stakeholder's standalone report through the CLI and browser.

Set REPORT_BROWSER_MODULES to a directory containing Playwright, and
REPORT_BROWSER_EXECUTABLE to a Chromium executable to run these optional checks.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_full_report import completed_review, full_workspace, report_all

# Re-export the synthetic saved-evidence fixtures for pytest discovery.
__all__ = ["completed_review", "full_workspace"]


@pytest.mark.parametrize("behavior", ["search", "filters", "disclosures"])
def test_offline_report_interactions(completed_review, tmp_path, behavior):
    """Users can investigate saved evidence without resources beside the HTML."""
    modules = os.environ.get("REPORT_BROWSER_MODULES")
    executable = os.environ.get("REPORT_BROWSER_EXECUTABLE")
    if not modules or not executable or not shutil.which("node"):
        pytest.skip("Set REPORT_BROWSER_MODULES and REPORT_BROWSER_EXECUTABLE for browser checks")
    run, manifest = completed_review
    assert report_all(run) == 0
    standalone = tmp_path / "standalone"
    standalone.mkdir()
    parent = standalone / "full.html"
    child = standalone / "page.html"
    shutil.copyfile(run / "report.html", parent)
    shutil.copyfile(run / manifest["pages"][0]["run_dir"] / "report.html", child)
    subprocess.run(
        ["node", str(Path(__file__).with_name("report_interactions.cjs")),
         behavior, str(parent), str(child)], check=True, timeout=60,
    )
