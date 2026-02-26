"""
响应压缩中间件 — gzip + zstd

根据客户端 Accept-Encoding 自动选择最优压缩算法。
SSE (text/event-stream) 及已压缩的二进制格式自动跳过。
"""

import gzip
import io

from starlette.types import ASGIApp, Message, Receive, Scope, Send

try:
    import zstandard as _zstd  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _zstd = None  # type: ignore[assignment]


# Already-compressed or binary MIME types — never compress.
_SKIP_PREFIXES = ("image/", "video/", "audio/", "font/")
_SKIP_TYPES = frozenset(
    {
        "application/zip",
        "application/gzip",
        "application/x-gzip",
        "application/x-bzip2",
        "application/x-xz",
        "application/zstd",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/pdf",
        "application/octet-stream",
        "application/wasm",
    }
)


def _pick_encoding(accept: str) -> str | None:
    """Return best supported encoding from Accept-Encoding header value."""
    if not accept:
        return None

    supported: dict[str, float] = {}
    for part in accept.split(","):
        part = part.strip()
        if not part:
            continue
        if ";q=" in part:
            name, q = part.split(";q=", 1)
            try:
                weight = float(q.strip())
            except ValueError:
                weight = 1.0
        else:
            name = part
            weight = 1.0
        key = name.strip().lower()
        if weight > 0:
            supported[key] = weight

    # Prefer zstd (faster decode, better ratio) over gzip.
    if _zstd is not None and "zstd" in supported:
        return "zstd"
    if "gzip" in supported:
        return "gzip"
    return None


def _should_skip(content_type: str) -> bool:
    """Return True if this content type should not be compressed."""
    if not content_type:
        return True
    ct = content_type.split(";", 1)[0].strip().lower()
    if not ct:
        return True
    if ct == "text/event-stream":
        return True
    for prefix in _SKIP_PREFIXES:
        if ct.startswith(prefix):
            return True
    return ct in _SKIP_TYPES


def _compress(
    data: bytes,
    encoding: str,
    *,
    gzip_level: int = 6,
    zstd_level: int = 3,
) -> bytes:
    if encoding == "zstd" and _zstd is not None:
        return _zstd.ZstdCompressor(level=zstd_level).compress(data)  # type: ignore[no-any-return]
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=gzip_level) as f:
        f.write(data)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Header helpers — operate on raw ASGI header tuples to avoid Pyright issues
# with Starlette's MutableHeaders typing.
# ---------------------------------------------------------------------------

_RawHeaders = list[tuple[bytes, bytes]]


def _header_get(raw: _RawHeaders, name: bytes) -> bytes:
    for k, v in raw:
        if k == name:
            return v
    return b""


def _header_set(raw: _RawHeaders, name: bytes, value: bytes) -> _RawHeaders:
    """Replace or append a header."""
    found = False
    out: _RawHeaders = []
    for k, v in raw:
        if k == name:
            out.append((k, value))
            found = True
        else:
            out.append((k, v))
    if not found:
        out.append((name, value))
    return out


def _header_remove(raw: _RawHeaders, name: bytes) -> _RawHeaders:
    return [(k, v) for k, v in raw if k != name]


class CompressionMiddleware:
    """
    ASGI compression middleware — gzip + zstd.

    Buffers non-streaming HTTP responses and compresses the body
    using the best algorithm the client advertises in Accept-Encoding.

    Streaming responses (text/event-stream) and already-compressed
    content types are passed through unchanged.
    """

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        gzip_level: int = 6,
        zstd_level: int = 3,
    ) -> None:
        self.app = app
        self.minimum_size = minimum_size
        self.gzip_level = gzip_level
        self.zstd_level = zstd_level

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Parse Accept-Encoding from request headers.
        accept_encoding = ""
        for key, val in scope.get("headers", []):
            if key == b"accept-encoding":
                accept_encoding = val.decode("latin-1")
                break

        encoding = _pick_encoding(accept_encoding)
        if not encoding:
            await self.app(scope, receive, send)
            return

        responder = _CompressResponder(
            send=send,
            encoding=encoding,
            minimum_size=self.minimum_size,
            gzip_level=self.gzip_level,
            zstd_level=self.zstd_level,
        )
        await self.app(scope, receive, responder.wrapped_send)


class _CompressResponder:
    """Per-request state for buffering and compressing the response."""

    __slots__ = (
        "_send",
        "_encoding",
        "_minimum_size",
        "_gzip_level",
        "_zstd_level",
        "_start_message",
        "_skip",
        "_started",
        "_body_parts",
    )

    def __init__(
        self,
        send: Send,
        encoding: str,
        minimum_size: int,
        gzip_level: int,
        zstd_level: int,
    ) -> None:
        self._send = send
        self._encoding = encoding
        self._minimum_size = minimum_size
        self._gzip_level = gzip_level
        self._zstd_level = zstd_level
        self._start_message: Message = {}
        self._skip = False
        self._started = False
        self._body_parts: list[bytes] = []

    async def wrapped_send(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self._start_message = message

            raw: _RawHeaders = message.get("headers", [])

            # Already has Content-Encoding — skip.
            if _header_get(raw, b"content-encoding"):
                self._skip = True
                return

            ct = _header_get(raw, b"content-type").decode("latin-1")
            if _should_skip(ct):
                self._skip = True
            return

        if message["type"] != "http.response.body":
            await self._send(message)
            return

        body: bytes = message.get("body", b"")
        more_body: bool = message.get("more_body", False)

        # --- Pass-through path (SSE, already compressed, etc.) ---
        if self._skip:
            if not self._started:
                self._started = True
                await self._send(self._start_message)
            await self._send(message)
            return

        # --- Compression path: buffer all body chunks ---
        if body:
            self._body_parts.append(body)

        if more_body:
            return  # keep buffering

        # All body received.
        full_body = b"".join(self._body_parts)

        if len(full_body) < self._minimum_size:
            # Too small — send uncompressed.
            await self._send(self._start_message)
            await self._send({"type": "http.response.body", "body": full_body})
            return

        compressed = _compress(
            full_body,
            self._encoding,
            gzip_level=self._gzip_level,
            zstd_level=self._zstd_level,
        )

        # Rewrite headers on the start message.
        raw = list(self._start_message.get("headers", []))
        raw = _header_remove(raw, b"content-length")
        raw = _header_set(raw, b"content-encoding", self._encoding.encode("latin-1"))
        raw.append((b"content-length", str(len(compressed)).encode("latin-1")))

        # Append Vary: Accept-Encoding (merge with existing if present).
        existing_vary = _header_get(raw, b"vary").decode("latin-1")
        if existing_vary:
            if "accept-encoding" not in existing_vary.lower():
                raw = _header_set(
                    raw, b"vary", f"{existing_vary}, Accept-Encoding".encode("latin-1")
                )
        else:
            raw.append((b"vary", b"Accept-Encoding"))

        self._start_message["headers"] = raw

        await self._send(self._start_message)
        await self._send({"type": "http.response.body", "body": compressed})
