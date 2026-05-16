from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse


@dataclass(frozen=True)
class StorageWriteResult:
    uri: str
    backend: str
    artifact_id: str | None = None


@dataclass(frozen=True)
class StorageEntry:
    uri: str
    name: str
    is_dir: bool = False
    artifact_id: str | None = None


class StorageClient:
    backend = "base"

    def read_text(self, uri: str) -> str:
        raise NotImplementedError

    def write_text(self, uri: str, content: str, *, overwrite: bool = False) -> StorageWriteResult:
        raise NotImplementedError

    def exists(self, uri: str) -> bool:
        raise NotImplementedError

    def list(self, uri: str) -> list[StorageEntry]:
        raise NotImplementedError

    def ensure_dir(self, uri: str) -> StorageWriteResult:
        raise NotImplementedError


def parse_storage_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme in {"local", "gdrive"}:
        path = parsed.netloc + parsed.path
        return parsed.scheme, path.lstrip("/") if parsed.scheme == "gdrive" else path
    return "local", uri


def join_uri(base_uri: str, *parts: str) -> str:
    scheme, path = parse_storage_uri(base_uri)
    cleaned = [path.rstrip("/")]
    cleaned.extend(part.strip("/") for part in parts if part)
    joined = "/".join(part for part in cleaned if part)
    if scheme == "local":
        if base_uri.startswith("local://"):
            return f"local://{joined}"
        return joined
    return f"gdrive://{joined}"


def default_run_base_uri(storage: str, run_id: str) -> str:
    suffix = f"niches/text-to-sql/runs/{run_id}"
    if storage == "gdrive":
        return f"gdrive://{suffix}"
    return f"local://generation/{suffix}"


class LocalStorageClient(StorageClient):
    backend = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd()

    def _path(self, uri: str) -> Path:
        scheme, path = parse_storage_uri(uri)
        if scheme != "local":
            raise ValueError(f"LocalStorageClient cannot handle {uri!r}")
        if path.startswith("//"):
            path = path[1:]
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.root / candidate

    def read_text(self, uri: str) -> str:
        return self._path(uri).read_text()

    def write_text(self, uri: str, content: str, *, overwrite: bool = False) -> StorageWriteResult:
        path = self._path(uri)
        if path.exists() and not overwrite:
            raise FileExistsError(f"{uri} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return StorageWriteResult(uri=uri, backend=self.backend, artifact_id=str(path))

    def exists(self, uri: str) -> bool:
        return self._path(uri).exists()

    def list(self, uri: str) -> list[StorageEntry]:
        path = self._path(uri)
        if not path.exists():
            return []
        if path.is_file():
            return [StorageEntry(uri=uri, name=path.name, is_dir=False, artifact_id=str(path))]
        entries = []
        for child in sorted(path.iterdir(), key=lambda item: item.name):
            child_uri = str(child)
            entries.append(StorageEntry(uri=child_uri, name=child.name, is_dir=child.is_dir(), artifact_id=str(child)))
        return entries

    def ensure_dir(self, uri: str) -> StorageWriteResult:
        path = self._path(uri)
        path.mkdir(parents=True, exist_ok=True)
        return StorageWriteResult(uri=uri, backend=self.backend, artifact_id=str(path))


def get_storage_client(
    *,
    storage: str | None = None,
    drive_root_id: str | None = None,
    local_root: Path | None = None,
) -> StorageClient:
    selected = storage or os.environ.get("DATA_FORGE_STORAGE", "local")
    if selected == "local":
        return LocalStorageClient(root=local_root)
    if selected == "gdrive":
        from data_forge.core.gdrive import GoogleDriveStorageClient

        root_id = drive_root_id or os.environ.get("DATA_FORGE_DRIVE_ROOT_ID")
        if not root_id:
            raise ValueError("DATA_FORGE_DRIVE_ROOT_ID or --drive-root-id is required for gdrive storage")
        return GoogleDriveStorageClient(root_folder_id=root_id)
    raise ValueError(f"unknown storage backend: {selected}")


def client_for_uri(uri: str, *, drive_root_id: str | None = None, local_root: Path | None = None) -> StorageClient:
    scheme, _ = parse_storage_uri(uri)
    return get_storage_client(storage=scheme, drive_root_id=drive_root_id, local_root=local_root)


def iter_json_records_from_text(text: str, *, source: str = "<memory>") -> Iterator[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"{source}: JSON array items must be objects")
            yield item
        return
    if isinstance(payload, dict):
        yield payload
        return

    lines = stripped.splitlines()
    for line_no, line in enumerate(lines, start=1):
        line = line.strip()
        if line:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{source}:{line_no}: invalid JSONL line") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{source}:{line_no}: JSONL records must be objects")
            yield payload


def read_json_records(storage: StorageClient, uri: str) -> list[dict[str, Any]]:
    entries = storage.list(uri)
    points_to_single_file = len(entries) == 1 and entries[0].uri == uri and not entries[0].is_dir
    if entries and not points_to_single_file:
        records: list[dict[str, Any]] = []
        for entry in entries:
            if entry.is_dir or not entry.name.endswith((".jsonl", ".json")):
                continue
            records.extend(iter_json_records_from_text(storage.read_text(entry.uri), source=entry.uri))
        return records
    return list(iter_json_records_from_text(storage.read_text(uri), source=uri))


def write_json(storage: StorageClient, uri: str, payload: Any, *, overwrite: bool = False) -> StorageWriteResult:
    return storage.write_text(uri, json.dumps(payload, indent=2, sort_keys=True) + "\n", overwrite=overwrite)


def write_jsonl(
    storage: StorageClient,
    uri: str,
    records: Iterable[dict[str, Any]],
    *,
    overwrite: bool = False,
) -> StorageWriteResult:
    content = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    return storage.write_text(uri, content, overwrite=overwrite)
