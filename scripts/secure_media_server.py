"""Small loopback media gateway. Put behind a trusted TLS reverse proxy in clinics."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import stat
import sys
from threading import BoundedSemaphore

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.db import init_db
from backend.production import authorize_media_token, prune_expired_capabilities

MAX_RANGE_BYTES = 8 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
MEDIA_PATH = re.compile(r"/media/([A-Za-z0-9_-]{43})\Z")


def parse_range(header: str | None, size: int) -> tuple[int, int, bool]:
    if header is None:
        return 0, size - 1, False
    if len(header) > 128:
        raise ValueError("Invalid range.")
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or not any(match.groups()):
        raise ValueError("Invalid range.")
    start, end = match.groups()
    if not start:
        count = int(end)
        if count < 1:
            raise ValueError("Invalid range.")
        start, end = max(0, size - min(count, MAX_RANGE_BYTES)), size - 1
    else:
        start = int(start)
        end = min(int(end) if end else size - 1, size - 1, start + MAX_RANGE_BYTES - 1)
    if start >= size or start < 0 or end < start:
        raise ValueError("Invalid range.")
    return start, end, True


class MediaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, *args, **kwargs):
        self._slots = BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        # Do not let standard-library traceback/access logs retain bearer paths or IPs.
        pass


class MediaHandler(BaseHTTPRequestHandler):
    server_version = "ParkinSenseMedia"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        pass

    def _headers(self, status, *, length=0, mime="text/plain", content_range=None, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "private, no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-site")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Accept-Ranges", "bytes")
        if content_range:
            self.send_header("Content-Range", content_range)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()

    def _serve(self, *, head=False):
        if self.path == "/health":
            self._headers(200, length=2)
            if not head:
                self.wfile.write(b"ok")
            return
        match = MEDIA_PATH.fullmatch(self.path)
        if not match:
            self._headers(404)
            return
        token = match.group(1)
        try:
            resource = authorize_media_token(token)
            descriptor = os.open(resource.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except (PermissionError, LookupError, ValueError, OSError):
            self._headers(404)
            return
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != resource.size_bytes:
                self._headers(404)
                return
            try:
                start, end, partial = parse_range(self.headers.get("Range"), info.st_size)
            except ValueError:
                self._headers(416, content_range=f"bytes */{info.st_size}")
                return
            length = end - start + 1
            self._headers(206 if partial else 200, length=length, mime=resource.mime_type,
                          content_range=f"bytes {start}-{end}/{info.st_size}" if partial else None,
                          filename=resource.filename)
            if head:
                return
            handle.seek(start)
            remaining = length
            try:
                while remaining:
                    # Revocation also stops an in-progress full-file stream, not just subsequent seeks.
                    authorize_media_token(token)
                    chunk = handle.read(min(CHUNK_BYTES, remaining))
                    if not chunk:
                        self.close_connection = True
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (PermissionError, LookupError, ValueError, OSError, BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    def do_GET(self):
        self._serve()

    def do_HEAD(self):
        self._serve(head=True)

    def do_POST(self):
        self._headers(405)
        self.close_connection = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1", "localhost"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8503)
    parser.add_argument("--prune-expired", action="store_true", help="Remove expired export files/capability hashes and exit.")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged port between 1024 and 65535.")
    init_db()
    if args.prune_expired:
        result = prune_expired_capabilities()
        print(f"Removed {result['expired_exports_removed']} expired private exports; source recordings retained.")
        return
    server = MediaHTTPServer((args.host, args.port), MediaHandler)
    print(f"Private media gateway listening on loopback port {args.port}. Access logging disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
