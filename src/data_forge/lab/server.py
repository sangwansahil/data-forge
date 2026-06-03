from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from data_forge.lab.store_factory import build_lab_store


class LabRequestHandler(SimpleHTTPRequestHandler):
    project_root: Path
    store: object

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(self.project_root / "apps/lab-ui"), **kwargs)

    def _json_response(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _serve_artifact(self, relative_path: str, *, include_body: bool = True) -> None:
        target = (self.project_root / relative_path).resolve()
        allowed_roots = [
            (self.project_root / "generation/lab").resolve(),
            (self.project_root / "generation/niches").resolve(),
        ]
        if not any(target == root or root in target.parents for root in allowed_roots):
            self._json_response({"error": "artifact path not allowed"}, HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            self._json_response({"error": "artifact not found"}, HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        if target.name.endswith(".tar.gz"):
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.end_headers()
        if include_body:
            self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json_response({"ok": True, "service": "data-forge-lab"})
            return
        if path.startswith("/artifacts/"):
            self._serve_artifact(unquote(path.removeprefix("/artifacts/")).strip("/"))
            return
        if path == "/api/runs":
            self._json_response({"runs": [envelope.to_dict() for envelope in self.store.list()]})
            return
        if path.startswith("/api/runs/"):
            run_id = unquote(path.removeprefix("/api/runs/")).strip("/")
            try:
                self._json_response(self.store.get(run_id).to_dict())
            except KeyError:
                self._json_response({"error": "run not found", "run_id": run_id}, HTTPStatus.NOT_FOUND)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path.startswith("/artifacts/"):
            self._serve_artifact(unquote(path.removeprefix("/artifacts/")).strip("/"), include_body=False)
            return
        super().do_HEAD()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        try:
            payload = self._read_json_body()
            if path == "/api/runs":
                prompt = str(payload.get("prompt", "")).strip()
                if not prompt:
                    self._json_response({"error": "prompt is required"}, HTTPStatus.BAD_REQUEST)
                    return
                envelope = self.store.create(prompt, project_root=self.project_root)
                self._json_response(envelope.to_dict(), HTTPStatus.CREATED)
                return
            if path.startswith("/api/runs/") and path.endswith("/approve"):
                run_id = unquote(path.removeprefix("/api/runs/").removesuffix("/approve")).strip("/")
                envelope = self.store.approve(
                    run_id,
                    str(payload.get("gate_id", "")),
                    str(payload.get("choice", "Approve")),
                )
                self._json_response(envelope.to_dict())
                return
            if path.startswith("/api/runs/") and path.endswith("/advance"):
                run_id = unquote(path.removeprefix("/api/runs/").removesuffix("/advance")).strip("/")
                self._json_response(self.store.advance(run_id).to_dict())
                return
            if path.startswith("/api/runs/") and path.endswith("/run-next"):
                run_id = unquote(path.removeprefix("/api/runs/").removesuffix("/run-next")).strip("/")
                self._json_response(self.store.run_next(run_id, project_root=self.project_root).to_dict())
                return
        except KeyError as exc:
            self._json_response({"error": "run not found", "run_id": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        except ValueError as exc:
            self._json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except json.JSONDecodeError:
            self._json_response({"error": "invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return
        self._json_response({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)


def serve(*, project_root: Path, host: str, port: int, store_dir: Path) -> None:
    LabRequestHandler.project_root = project_root
    LabRequestHandler.store = build_lab_store(root=project_root, store_path=str(store_dir))
    server = ThreadingHTTPServer((host, port), LabRequestHandler)
    print(f"Data Forge Lab listening on http://{host}:{port}")
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Data Forge Lab server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root", default=".")
    parser.add_argument("--store", default="generation/lab/runs")
    args = parser.parse_args()
    project_root = Path(args.root).resolve()
    store_dir = Path(args.store)
    if not store_dir.is_absolute():
        store_dir = project_root / store_dir
    serve(project_root=project_root, host=args.host, port=args.port, store_dir=store_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
