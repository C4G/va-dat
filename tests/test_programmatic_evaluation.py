from pathlib import Path

from vision_aid.evaluation.programmatic import run_programmatic_audit


def test_existing_programmatic_checks_are_adapted_without_duplicating_rules(
    tmp_path: Path,
) -> None:
    """The evaluation adapter calls all existing deterministic checkers."""
    html = tmp_path / "benchmark.html"
    html.write_text(
        "<html lang='en'><head><title>Synthetic</title></head>"
        "<body><h1>One</h1><h1>Two</h1><img src='hero.png'></body></html>",
        encoding="utf-8",
    )

    result = run_programmatic_audit(
        html,
        run_id="run-1",
        page_url="https://example.test/",
    )

    rule_ids = {finding.problem_family for finding in result.findings}
    assert "HEAD_002" in rule_ids
    assert "NON_TEXT_001" in rule_ids
    assert result.raw_findings
    assert all(
        finding.raw_source in result.raw_findings
        for finding in result.findings
    )
