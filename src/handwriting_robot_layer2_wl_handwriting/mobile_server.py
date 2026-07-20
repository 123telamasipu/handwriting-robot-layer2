from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import mimetypes
import secrets
import socket
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlsplit

from .capture_protocol import CAPTURE_SCHEMA_VERSION, CaptureSubmission
from .charset import CharacterEntry, default_charset_path, load_target_charset
from .storage import SampleStore


MAX_REQUEST_BYTES = 5 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, message: str, code: str = "invalid_request", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class MobileCollectorService:
    def __init__(
        self,
        entries: list[CharacterEntry],
        data_dir: Path,
        default_writer_id: str = "",
        default_writer_name: str = "",
    ) -> None:
        if not entries:
            raise ValueError("target charset cannot be empty")
        self.entries = list(entries)
        self.data_dir = Path(data_dir)
        self.default_writer_id = default_writer_id.strip()
        self.default_writer_name = default_writer_name.strip()
        self._entry_by_character = {entry.character: entry for entry in entries}
        self._write_lock = threading.RLock()

    def configuration(self) -> Dict[str, Any]:
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "application": "mobile_handwriting_collector",
            "default_writer": {
                "id": self.default_writer_id,
                "name": self.default_writer_name,
            },
            "variant_range": [1, 5],
            "entries": [asdict(entry) for entry in self.entries],
        }

    def _entry(self, character: str) -> CharacterEntry:
        entry = self._entry_by_character.get(character)
        if entry is None:
            raise ApiError("character is not in the target charset", "unknown_character")
        return entry

    @staticmethod
    def _variant(value: Any) -> int:
        try:
            variant = int(value)
        except (TypeError, ValueError) as error:
            raise ApiError("variant must be an integer") from error
        if not 1 <= variant <= 5:
            raise ApiError("variant must be between 1 and 5")
        return variant

    def _store(
        self, writer_id: str, writer_name: str = ""
    ) -> SampleStore:
        try:
            return SampleStore(self.data_dir, writer_id, writer_name)
        except ValueError as error:
            raise ApiError(str(error), "invalid_writer") from error

    @staticmethod
    def _progress(store: SampleStore, total: int) -> Dict[str, Any]:
        completed = store.completed_count()
        return {
            "completed": completed,
            "total": total,
            "coverage": completed / total if total else 1.0,
            "completed_characters": store.completed_characters(),
        }

    def progress(self, writer_id: str, writer_name: str = "") -> Dict[str, Any]:
        store = self._store(writer_id, writer_name)
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "writer_id": store.writer_id,
            "progress": self._progress(store, len(self.entries)),
        }

    def sample(
        self,
        writer_id: str,
        character: str,
        variant_value: Any,
        writer_name: str = "",
    ) -> Dict[str, Any]:
        entry = self._entry(character)
        variant = self._variant(variant_value)
        store = self._store(writer_id, writer_name)
        document, state = store.load_working_document(entry, variant)
        return {
            "schema_version": CAPTURE_SCHEMA_VERSION,
            "state": state,
            "entry": asdict(entry),
            "variant": variant,
            "sample": document,
            "progress": self._progress(store, len(self.entries)),
        }

    def save(self, value: Dict[str, Any]) -> Dict[str, Any]:
        try:
            submission = CaptureSubmission.from_dict(value)
        except ValueError as error:
            raise ApiError(str(error), "invalid_capture") from error

        entry = self._entry(submission.character)
        with self._write_lock:
            store = self._store(submission.writer_id, submission.writer_name)
            if submission.status == "draft":
                path = store.save_draft(
                    entry,
                    submission.variant,
                    submission.buffer,
                    capture_context=submission.capture_context,
                )
                state = "draft" if path else "missing"
            else:
                try:
                    path = store.commit_sample(
                        entry,
                        submission.variant,
                        submission.buffer,
                        capture_context=submission.capture_context,
                    )
                except ValueError as error:
                    raise ApiError(str(error), "incomplete_sample") from error
                state = "complete"

            return {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "state": state,
                "character": entry.character,
                "variant": submission.variant,
                "saved": path is not None,
                "progress": self._progress(store, len(self.entries)),
            }


class MobileCollectorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        service: MobileCollectorService,
        access_token: Optional[str],
        web_root: Path,
    ) -> None:
        self.service = service
        self.access_token = access_token
        self.web_root = Path(web_root)
        super().__init__(address, MobileCollectorRequestHandler)


class MobileCollectorRequestHandler(BaseHTTPRequestHandler):
    server: MobileCollectorHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        del format, args

    def _parsed(self):
        return urlsplit(self.path)

    def _query(self) -> Dict[str, str]:
        values = parse_qs(self._parsed().query, keep_blank_values=True)
        return {key: items[-1] for key, items in values.items()}

    def _authorized(self) -> bool:
        expected = self.server.access_token
        if expected is None:
            return True
        supplied = self._query().get("token", "") or self.headers.get(
            "X-Access-Token", ""
        )
        return hmac.compare_digest(supplied, expected)

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "script-src 'self'; style-src 'self'",
        )

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, value: Dict[str, Any], status: int = 200) -> None:
        body = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _send_error(self, error: ApiError) -> None:
        self._send_json(
            {
                "schema_version": CAPTURE_SCHEMA_VERSION,
                "error": {"code": error.code, "message": error.message},
            },
            error.status,
        )

    def _require_authorized(self) -> None:
        if not self._authorized():
            raise ApiError("invalid or missing access token", "forbidden", 403)

    def _serve_static(self, relative_path: str) -> None:
        allowed = {
            "index.html": "index.html",
            "assets/app.css": "assets/app.css",
            "assets/app.js": "assets/app.js",
            "assets/favicon.svg": "assets/favicon.svg",
        }
        name = allowed.get(relative_path)
        if name is None:
            raise ApiError("resource not found", "not_found", 404)
        path = self.server.web_root / name
        if not path.is_file():
            raise ApiError("resource not found", "not_found", 404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self._send_bytes(path.read_bytes(), content_type)

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = self._parsed().path
            if path in {
                "/assets/app.css",
                "/assets/app.js",
                "/assets/favicon.svg",
            }:
                self._serve_static(path.lstrip("/"))
                return
            self._require_authorized()
            query = self._query()
            if path == "/":
                self._serve_static("index.html")
            elif path == "/api/health":
                self._send_json(
                    {
                        "schema_version": CAPTURE_SCHEMA_VERSION,
                        "status": "ok",
                    }
                )
            elif path == "/api/config":
                self._send_json(self.server.service.configuration())
            elif path == "/api/progress":
                self._send_json(
                    self.server.service.progress(
                        query.get("writer_id", ""), query.get("writer_name", "")
                    )
                )
            elif path == "/api/sample":
                self._send_json(
                    self.server.service.sample(
                        query.get("writer_id", ""),
                        query.get("character", ""),
                        query.get("variant", "1"),
                        query.get("writer_name", ""),
                    )
                )
            else:
                raise ApiError("resource not found", "not_found", 404)
        except ApiError as error:
            self._send_error(error)
        except OSError:
            self._send_error(ApiError("storage operation failed", "storage_error", 500))

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._require_authorized()
            if self._parsed().path != "/api/sample":
                raise ApiError("resource not found", "not_found", 404)
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ApiError("invalid Content-Length") from error
            if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
                raise ApiError("request body size is invalid", "invalid_body", 413)
            try:
                value = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ApiError("request body must be UTF-8 JSON", "invalid_json") from error
            self._send_json(self.server.service.save(value))
        except ApiError as error:
            self._send_error(error)
        except OSError:
            self._send_error(ApiError("storage operation failed", "storage_error", 500))


def create_server(
    host: str,
    port: int,
    service: MobileCollectorService,
    access_token: Optional[str],
    web_root: Optional[Path] = None,
) -> MobileCollectorHTTPServer:
    root = web_root or Path(__file__).resolve().parent / "web"
    return MobileCollectorHTTPServer((host, port), service, access_token, root)


def discover_lan_addresses() -> list[str]:
    addresses = set()
    try:
        candidates = socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM
        )
    except socket.gaierror:
        candidates = []
    for candidate in candidates:
        address = candidate[4][0]
        parsed = ipaddress.ip_address(address)
        if not parsed.is_loopback and not parsed.is_link_local:
            addresses.add(address)
    return sorted(addresses)


def build_parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Mobile handwriting collector server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--charset", type=Path, default=default_charset_path())
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=repository_root / "runtime_data" / "handwriting",
    )
    parser.add_argument("--writer-id", default="")
    parser.add_argument("--writer-name", default="")
    parser.add_argument(
        "--access-token",
        default="",
        help="Access token included in the phone URL; generated when omitted",
    )
    parser.add_argument(
        "--no-auth",
        action="store_true",
        help="Disable access-token protection on the local network",
    )
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not 0 <= args.port <= 65535:
        print("port must be between 0 and 65535")
        return 2
    try:
        entries = load_target_charset(args.charset)
        service = MobileCollectorService(
            entries,
            args.data_dir,
            default_writer_id=args.writer_id,
            default_writer_name=args.writer_name,
        )
        token = None
        if not args.no_auth:
            token = args.access_token or f"{secrets.randbelow(1000000):06d}"
        server = create_server(args.host, args.port, service, token)
    except (OSError, ValueError) as error:
        print(f"mobile collector failed to start: {error}")
        return 1

    actual_port = server.server_address[1]
    query = "" if token is None else f"?token={token}"
    print("手机笔迹采集服务已启动")
    print(f"笔记本访问: http://127.0.0.1:{actual_port}/{query}")
    for address in discover_lan_addresses():
        print(f"手机访问:   http://{address}:{actual_port}/{query}")
    print("手机和笔记本需要连接同一局域网。按 Ctrl+C 停止服务。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
