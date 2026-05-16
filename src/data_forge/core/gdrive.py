from __future__ import annotations

import io
import json
import os
from functools import cached_property
from typing import Any

from data_forge.core.storage import StorageClient, StorageEntry, StorageWriteResult, parse_storage_uri


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveStorageClient(StorageClient):
    backend = "gdrive"

    def __init__(self, root_folder_id: str) -> None:
        self.root_folder_id = root_folder_id

    @cached_property
    def service(self) -> Any:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Drive storage requires google-api-python-client and google-auth. "
                "Install the project dependencies first."
            ) from exc

        raw_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
        if raw_json:
            info = json.loads(raw_json)
            creds = service_account.Credentials.from_service_account_info(info, scopes=DRIVE_SCOPES)
        else:
            creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            if not creds_path:
                raise ValueError(
                    "GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_APPLICATION_CREDENTIALS_JSON is required"
                )
            creds = service_account.Credentials.from_service_account_file(creds_path, scopes=DRIVE_SCOPES)
        return build("drive", "v3", credentials=creds, cache_discovery=False)

    def _gdrive_path(self, uri: str) -> str:
        scheme, path = parse_storage_uri(uri)
        if scheme != "gdrive":
            raise ValueError(f"GoogleDriveStorageClient cannot handle {uri!r}")
        return path.strip("/")

    def _query_child(self, parent_id: str, name: str, *, mime_type: str | None = None) -> dict[str, Any] | None:
        escaped_name = name.replace("'", "\\'")
        query = [f"'{parent_id}' in parents", f"name = '{escaped_name}'", "trashed = false"]
        if mime_type:
            query.append(f"mimeType = '{mime_type}'")
        response = (
            self.service.files()
            .list(
                q=" and ".join(query),
                spaces="drive",
                fields="files(id,name,mimeType)",
                pageSize=10,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None

    def _ensure_folder_path(self, folder_path: str) -> str:
        parent_id = self.root_folder_id
        if not folder_path:
            return parent_id
        for part in folder_path.strip("/").split("/"):
            existing = self._query_child(
                parent_id,
                part,
                mime_type="application/vnd.google-apps.folder",
            )
            if existing:
                parent_id = existing["id"]
                continue
            metadata = {
                "name": part,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = self.service.files().create(body=metadata, fields="id").execute()
            parent_id = folder["id"]
        return parent_id

    def _resolve_path(self, path: str) -> dict[str, Any] | None:
        parent_id = self.root_folder_id
        parts = [part for part in path.strip("/").split("/") if part]
        if not parts:
            return {
                "id": self.root_folder_id,
                "name": "",
                "mimeType": "application/vnd.google-apps.folder",
            }
        for index, part in enumerate(parts):
            found = self._query_child(parent_id, part)
            if not found:
                return None
            if index == len(parts) - 1:
                return found
            if found.get("mimeType") != "application/vnd.google-apps.folder":
                return None
            parent_id = found["id"]
        return None

    def read_text(self, uri: str) -> str:
        item = self._resolve_path(self._gdrive_path(uri))
        if not item:
            raise FileNotFoundError(uri)
        request = self.service.files().get_media(fileId=item["id"])
        buffer = io.BytesIO()
        try:
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError as exc:
            raise RuntimeError("google-api-python-client is required for Google Drive storage") from exc
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue().decode()

    def write_text(self, uri: str, content: str, *, overwrite: bool = False) -> StorageWriteResult:
        try:
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError as exc:
            raise RuntimeError("google-api-python-client is required for Google Drive storage") from exc

        path = self._gdrive_path(uri)
        folder_path, _, filename = path.rpartition("/")
        if not filename:
            raise ValueError(f"cannot write text to folder URI: {uri}")
        parent_id = self._ensure_folder_path(folder_path)
        existing = self._query_child(parent_id, filename)
        media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype="text/plain", resumable=False)
        if existing:
            if not overwrite:
                raise FileExistsError(f"{uri} already exists")
            updated = (
                self.service.files()
                .update(fileId=existing["id"], media_body=media, fields="id")
                .execute()
            )
            return StorageWriteResult(uri=uri, backend=self.backend, artifact_id=updated["id"])

        metadata = {"name": filename, "parents": [parent_id]}
        created = (
            self.service.files()
            .create(body=metadata, media_body=media, fields="id")
            .execute()
        )
        return StorageWriteResult(uri=uri, backend=self.backend, artifact_id=created["id"])

    def exists(self, uri: str) -> bool:
        return self._resolve_path(self._gdrive_path(uri)) is not None

    def list(self, uri: str) -> list[StorageEntry]:
        path = self._gdrive_path(uri)
        item = self._resolve_path(path)
        if not item:
            return []
        if item.get("mimeType") != "application/vnd.google-apps.folder":
            return [StorageEntry(uri=uri, name=item["name"], is_dir=False, artifact_id=item["id"])]
        response = (
            self.service.files()
            .list(
                q=f"'{item['id']}' in parents and trashed = false",
                spaces="drive",
                fields="files(id,name,mimeType)",
                pageSize=1000,
                orderBy="name",
            )
            .execute()
        )
        base = uri.rstrip("/")
        entries = []
        for child in response.get("files", []):
            entries.append(
                StorageEntry(
                    uri=f"{base}/{child['name']}",
                    name=child["name"],
                    is_dir=child.get("mimeType") == "application/vnd.google-apps.folder",
                    artifact_id=child["id"],
                )
            )
        return entries

    def ensure_dir(self, uri: str) -> StorageWriteResult:
        folder_id = self._ensure_folder_path(self._gdrive_path(uri))
        return StorageWriteResult(uri=uri, backend=self.backend, artifact_id=folder_id)
