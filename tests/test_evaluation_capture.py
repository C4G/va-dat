"""Capture Benchmark snapshots through the public evaluator CLI."""

import hashlib
import json
from pathlib import Path

import openpyxl
import pytest
import requests

from vision_aid.evaluation.cli import main


def audit(path: Path, *urls: str | None) -> Path:
    """Create a synthetic URL list without private Human audit evidence."""
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "URL list"
    sheet.append(["#", "Web page name", "URL", "Status"])
    for number, url in enumerate(urls, start=1):
        sheet.append([number, "Repeated name", url, ""])
    book.save(path)
    return path


def capture(human_audit: Path, output: Path) -> int:
    """Invoke capture through the public CLI with the supplied audit and output."""
    return main(["capture", "--human-audit", str(human_audit), "--output-dir", str(output)])


def test_capture_saves_only_listed_urls_in_order_and_preserves_redirect_identity(
    tmp_path, monkeypatch, capsys,
):
    """A key-free capture saves separate HTML and a reusable relative mapping."""
    source = audit(tmp_path / "audit.xlsx", "https://example.test/old/", None,
                   "https://example.test/contact/")
    output = tmp_path / "snapshots"
    downloads = []

    def get(url, **options):
        """Record downloads and return separate HTML with a redirected URL."""
        downloads.append((url, options))
        response = requests.Response()
        response.status_code = 200
        response.url = "https://example.test/redirected/"
        response._content = (b"<html>First page</html>" if len(downloads) == 1
                             else b"<html>Second page</html>")
        return response

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("anthropic.Anthropic", lambda **_: pytest.fail("provider access"))
    monkeypatch.setattr("openai.OpenAI", lambda **_: pytest.fail("provider access"))
    assert capture(source, output) == 0
    mapping = json.loads((output / "snapshots.json").read_text())
    assert mapping == {
        "human_audit_filename": "audit.xlsx",
        "human_audit_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "snapshots": [
            {"source_url": "https://example.test/old/", "html": "page-001.html"},
            {"source_url": "https://example.test/contact/", "html": "page-002.html"},
        ],
    }
    assert (output / "page-001.html").read_text() == "<html>First page</html>"
    assert (output / "page-002.html").read_text() == "<html>Second page</html>"
    assert [url for url, _ in downloads] == [
        "https://example.test/old/", "https://example.test/contact/",
    ]
    assert all(options.get("allow_redirects", True) for _, options in downloads)
    assert str(output / "snapshots.json") in capsys.readouterr().out


@pytest.mark.parametrize("status", [404, 503])
def test_capture_stops_after_http_error_and_keeps_saved_evidence(
    tmp_path, monkeypatch, capsys, status,
):
    """Failed download leaves earlier HTML but no complete snapshot mapping."""
    source = audit(tmp_path / "audit.xlsx", "https://example.test/first/",
                   "https://example.test/failing/", "https://example.test/later/")
    output = tmp_path / "snapshots"
    downloads = []

    def get(url, **options):
        """Return saved HTML first, then the requested HTTP error."""
        downloads.append(url)
        response = requests.Response()
        response.status_code = 200 if len(downloads) == 1 else status
        response.url = url
        response._content = b"<html>Saved first page</html>"
        return response

    monkeypatch.setattr(requests, "get", get)
    with pytest.raises(SystemExit) as error:
        capture(source, output)
    assert error.value.code == 2
    assert downloads == ["https://example.test/first/", "https://example.test/failing/"]
    assert {path.name for path in output.iterdir()} == {"page-001.html"}
    assert (output / "page-001.html").read_text() == "<html>Saved first page</html>"
    assert str(status) in capsys.readouterr().err


def test_capture_requires_a_new_directory_before_downloading(tmp_path, monkeypatch, capsys):
    """Saved Benchmark snapshots cannot be replaced by another capture."""
    source = audit(tmp_path / "audit.xlsx", "https://example.test/")
    output = tmp_path / "snapshots"
    output.mkdir()
    (output / "saved.html").write_text("Previously captured")
    monkeypatch.setattr(requests, "get", lambda *_, **__: pytest.fail("download"))
    with pytest.raises(SystemExit) as error:
        capture(source, output)
    assert error.value.code == 2
    assert (output / "saved.html").read_text() == "Previously captured"
    assert "exists" in capsys.readouterr().err.lower()


@pytest.mark.parametrize("urls", [(), (None, " ")])
def test_capture_rejects_an_empty_url_list_before_downloading(
    tmp_path, monkeypatch, capsys, urls,
):
    """An audit without targets cannot publish a complete snapshot set."""
    source = audit(tmp_path / "audit.xlsx", *urls)
    output = tmp_path / "snapshots"
    monkeypatch.setattr(requests, "get", lambda *_, **__: pytest.fail("download"))
    with pytest.raises(SystemExit) as error:
        capture(source, output)
    assert error.value.code == 2
    assert not output.exists()
    assert "no target URLs" in capsys.readouterr().err
