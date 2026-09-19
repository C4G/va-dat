"""Immutable benchmark snapshots for model evaluation."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import cast
from urllib.parse import urlparse

from vision_aid.evaluation.workspace import PrivateInputError, PrivateWorkspace

SNAPSHOT_DIRECTORY_NAME = "pristine-homepage"
SNAPSHOT_HTML_FILENAME = "source.html"
SNAPSHOT_METADATA_FILENAME = "metadata.json"
DAT_VISION_AID_FIXTURE = "dat_visionaid_home.html"
HTTP_TIMEOUT = (5, 30)
PIPELINE_USER_AGENT = "Mozilla/5.0"


@dataclass(frozen=True)
class SnapshotHTTPMetadata:
    """HTTP request and response details that identify captured content."""

    content_length: str | None
    content_type: str | None
    etag: str | None
    final_url: str
    last_modified: str | None
    request_user_agent: str
    status_code: int


@dataclass(frozen=True)
class SnapshotMetadata:
    """Required provenance for one immutable benchmark snapshot."""

    byte_length: int
    html_file: str
    http: SnapshotHTTPMetadata
    retrieved_at: str
    sha256: str
    source_url: str
    temporal_assumption: str

    def to_json(self) -> object:
        """Return the JSON-compatible representation stored beside the HTML."""
        return asdict(self)

    @classmethod
    def from_json(cls, value: object) -> "SnapshotMetadata":
        """Validate and construct snapshot provenance loaded from JSON."""
        if not isinstance(value, dict):
            raise ValueError("snapshot metadata must be a JSON object")
        http_value = value.get("http")
        if not isinstance(http_value, dict):
            raise ValueError("snapshot HTTP metadata must be a JSON object")

        required_strings = (
            "html_file",
            "retrieved_at",
            "sha256",
            "source_url",
            "temporal_assumption",
        )
        if any(not isinstance(value.get(name), str) for name in required_strings):
            raise ValueError("snapshot metadata has a missing string field")
        required_http_strings = (
            "final_url",
            "request_user_agent",
        )
        if any(
            not isinstance(http_value.get(name), str)
            for name in required_http_strings
        ):
            raise ValueError("snapshot HTTP metadata has a missing string field")
        optional_http_strings = (
            "content_length",
            "content_type",
            "etag",
            "last_modified",
        )
        if any(
            http_value.get(name) is not None
            and not isinstance(http_value.get(name), str)
            for name in optional_http_strings
        ):
            raise ValueError("snapshot HTTP metadata has an invalid header field")
        byte_length = value.get("byte_length")
        status_code = http_value.get("status_code")
        if not isinstance(byte_length, int) or isinstance(byte_length, bool):
            raise ValueError("snapshot byte length must be an integer")
        if not isinstance(status_code, int) or isinstance(status_code, bool):
            raise ValueError("snapshot HTTP status must be an integer")

        return cls(
            byte_length=byte_length,
            html_file=cast(str, value["html_file"]),
            http=SnapshotHTTPMetadata(
                content_length=cast(str | None, http_value.get("content_length")),
                content_type=cast(str | None, http_value.get("content_type")),
                etag=cast(str | None, http_value.get("etag")),
                final_url=cast(str, http_value["final_url"]),
                last_modified=cast(str | None, http_value.get("last_modified")),
                request_user_agent=cast(str, http_value["request_user_agent"]),
                status_code=status_code,
            ),
            retrieved_at=cast(str, value["retrieved_at"]),
            sha256=cast(str, value["sha256"]),
            source_url=cast(str, value["source_url"]),
            temporal_assumption=cast(str, value["temporal_assumption"]),
        )


@dataclass(frozen=True)
class BenchmarkSnapshot:
    """A verified raw HTML benchmark and its provenance record."""

    html_path: Path
    metadata_path: Path
    metadata: SnapshotMetadata
    reused: bool


def prepare_benchmark_snapshot(
    workspace: PrivateWorkspace,
    source_url: str,
    temporal_assumption: str | None,
) -> BenchmarkSnapshot:
    """Capture a benchmark once or verify an existing immutable capture."""
    _require_http_source(source_url)
    snapshot_directory = (
        workspace.root / "snapshots" / SNAPSHOT_DIRECTORY_NAME
    )
    html_path = snapshot_directory / SNAPSHOT_HTML_FILENAME
    metadata_path = snapshot_directory / SNAPSHOT_METADATA_FILENAME

    if snapshot_directory.exists():
        return _load_snapshot(
            html_path,
            metadata_path,
            source_url,
            temporal_assumption,
        )

    assumption = (temporal_assumption or "").strip()
    if not assumption:
        raise PrivateInputError(
            "A new benchmark snapshot requires --temporal-assumption so the "
            "stakeholder-supported relationship to the workbook audit is explicit."
        )

    import requests

    try:
        response = requests.get(
            source_url,
            headers={"User-Agent": PIPELINE_USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
    except requests.RequestException as error:
        raise PrivateInputError(
            f"Could not retrieve Pristine benchmark source {source_url}: {error}"
        ) from error

    if response.status_code != 200:
        raise PrivateInputError(
            f"Pristine benchmark source returned HTTP {response.status_code}; "
            "no snapshot was saved."
        )
    content_type = response.headers.get("Content-Type")
    if content_type is not None and not content_type.lower().startswith("text/html"):
        raise PrivateInputError(
            f"Pristine benchmark source returned {content_type!r}, not raw HTML; "
            "no snapshot was saved."
        )
    body = response.content
    if not body:
        raise PrivateInputError(
            "Pristine benchmark source returned an empty body; no snapshot was saved."
        )
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PrivateInputError(
            "Pristine benchmark HTML is not valid UTF-8 and cannot be consumed "
            "by the existing audit pipeline; no snapshot was saved."
        ) from error

    metadata = SnapshotMetadata(
        byte_length=len(body),
        html_file=SNAPSHOT_HTML_FILENAME,
        http=SnapshotHTTPMetadata(
            content_length=response.headers.get("Content-Length"),
            content_type=content_type,
            etag=response.headers.get("ETag"),
            final_url=response.url,
            last_modified=response.headers.get("Last-Modified"),
            request_user_agent=PIPELINE_USER_AGENT,
            status_code=response.status_code,
        ),
        retrieved_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        sha256=hashlib.sha256(body).hexdigest(),
        source_url=source_url,
        temporal_assumption=assumption,
    )
    _save_new_snapshot(snapshot_directory, body, metadata)
    return BenchmarkSnapshot(html_path, metadata_path, metadata, reused=False)


def _require_http_source(source_url: str) -> None:
    """Reject local substitutes and malformed benchmark source URLs."""
    parsed = urlparse(source_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return
    if Path(source_url).name == DAT_VISION_AID_FIXTURE:
        raise PrivateInputError(
            "The DAT Vision Aid fixture is not a Pristine benchmark input. "
            "Capture the authorized Pristine homepage over HTTP(S)."
        )
    raise PrivateInputError(
        "Benchmark snapshot sources must be HTTP(S) URLs. Local HTML files "
        "cannot substitute for the Pristine homepage."
    )


def _load_snapshot(
    html_path: Path,
    metadata_path: Path,
    source_url: str,
    temporal_assumption: str | None,
) -> BenchmarkSnapshot:
    """Validate an existing snapshot without fetching or changing it."""
    if not html_path.is_file() or not metadata_path.is_file():
        raise PrivateInputError(
            "The benchmark snapshot is incomplete. It will not be refetched or "
            "overwritten; restore the matching HTML and metadata files."
        )
    try:
        metadata = SnapshotMetadata.from_json(
            json.loads(metadata_path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise PrivateInputError(
            "The benchmark snapshot metadata is unreadable. The existing "
            "snapshot will not be overwritten."
        ) from error
    if metadata.source_url != source_url:
        raise PrivateInputError(
            "The existing benchmark snapshot was captured from "
            f"{metadata.source_url!r}, "
            f"not {source_url!r}. It will not be refetched or overwritten."
        )
    supplied_assumption = (temporal_assumption or "").strip()
    if (
        supplied_assumption
        and supplied_assumption != metadata.temporal_assumption
    ):
        raise PrivateInputError(
            "The supplied temporal assumption differs from the immutable snapshot "
            "metadata. The existing snapshot will not be overwritten."
        )

    try:
        body = html_path.read_bytes()
    except OSError as error:
        raise PrivateInputError(
            "The benchmark snapshot HTML is unreadable. The existing snapshot "
            "will not be overwritten."
        ) from error
    actual_sha256 = hashlib.sha256(body).hexdigest()
    if metadata.sha256 != actual_sha256:
        raise PrivateInputError(
            "The benchmark snapshot checksum does not match its metadata. The "
            "existing snapshot will not be refetched or overwritten."
        )
    if metadata.byte_length != len(body):
        raise PrivateInputError(
            "The benchmark snapshot byte length does not match its metadata. The "
            "existing snapshot will not be refetched or overwritten."
        )
    if metadata.html_file != html_path.name:
        raise PrivateInputError(
            "The benchmark metadata identifies a different HTML file. The "
            "existing snapshot will not be refetched or overwritten."
        )
    return BenchmarkSnapshot(html_path, metadata_path, metadata, reused=True)


def _save_new_snapshot(
    snapshot_directory: Path,
    body: bytes,
    metadata: SnapshotMetadata,
) -> None:
    """Stage both artifacts and publish their directory as one atomic unit."""
    metadata_bytes = (
        json.dumps(
            metadata.to_json(),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    staged_directory = Path(
        mkdtemp(
            prefix=f".{SNAPSHOT_DIRECTORY_NAME}-",
            dir=snapshot_directory.parent,
        )
    )
    try:
        (staged_directory / SNAPSHOT_HTML_FILENAME).write_bytes(body)
        (staged_directory / SNAPSHOT_METADATA_FILENAME).write_bytes(metadata_bytes)
        if snapshot_directory.exists():
            raise FileExistsError(snapshot_directory)
        staged_directory.rename(snapshot_directory)
    except OSError as error:
        if snapshot_directory.exists():
            message = (
                "A benchmark snapshot appeared during capture. It was not "
                "overwritten; rerun prepare to verify the existing snapshot."
            )
        else:
            message = f"Could not save the benchmark snapshot: {error}"
        raise PrivateInputError(message) from error
    finally:
        if staged_directory.exists():
            for staged_file in staged_directory.iterdir():
                staged_file.unlink()
            staged_directory.rmdir()
