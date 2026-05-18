"""Optional on-disk HTTP cache.

Civic-data work is iterative. You pull a dataset, look at it, change a flag,
pull again. Hitting the Legistar API for the same bytes ten times in a row is
slow and rude. This module wraps httpx with a content-keyed file cache.

Cache is keyed on (method, URL, query string) and stored as JSON. Entries are
trusted indefinitely; if you want fresh data, delete the cache directory (or
just don't pass --cache).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx


def default_dir() -> Path:
    return Path.home() / ".cache" / "convene"


class CachingTransport(httpx.BaseTransport):
    """Wraps an httpx transport with a file-backed cache."""

    def __init__(self, cache_dir: Path, inner: httpx.BaseTransport | None = None):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.inner = inner or httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            return self.inner.handle_request(request)
        cache_path = self._path_for(request)
        if cache_path.exists():
            payload = json.loads(cache_path.read_text())
            return httpx.Response(
                status_code=payload["status"],
                headers=payload["headers"],
                content=payload["body"].encode("utf-8"),
                request=request,
            )
        resp = self.inner.handle_request(request)
        if 200 <= resp.status_code < 300:
            body = resp.read().decode("utf-8")
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({
                "status": resp.status_code,
                "headers": [list(h) for h in resp.headers.items()],
                "body": body,
            }))
        return resp

    def _path_for(self, req: httpx.Request) -> Path:
        key = hashlib.sha256(str(req.url).encode("utf-8")).hexdigest()
        # First two chars as a subdir so we don't end up with 10k files in one place
        return self.cache_dir / key[:2] / f"{key}.json"


def build_client(*, cache: bool = False, cache_dir: Path | None = None,
                 timeout: float = 30.0) -> httpx.Client:
    headers = {"Accept": "application/json"}
    if not cache:
        return httpx.Client(timeout=timeout, headers=headers)
    transport = CachingTransport(cache_dir or default_dir())
    return httpx.Client(timeout=timeout, headers=headers, transport=transport)


