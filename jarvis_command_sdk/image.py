"""Image parameters: photos the user attached, handed to a command's ``run()``.

A command declares ``JarvisParameter("photos", "image", ...)``. The value its
``run()`` receives is **always a list** of :class:`JarvisImage`, in the order
the user attached them (even for a single photo).

Wire contract (server → node ``tool_call``): the argument value for an image
parameter is a JSON list of ``{"mime": "image/jpeg", "data": "<base64>"}``,
at most :data:`MAX_IMAGES` items, each at most :data:`MAX_IMAGE_BYTES` decoded.
``IJarvisCommand.execute()`` turns that list into ``list[JarvisImage]`` before
``run()`` is called (see :func:`coerce_images`).

What the model sees in the tool schema is different: an array of 1-based photo
numbers, marked with ``"x-jarvis-type": "image"`` (:data:`IMAGE_SCHEMA_MARKER`)
so the server knows to swap the numbers for the bytes before the call reaches
the node.

No third-party dependencies: dimensions are read from the JPEG/PNG/WebP header
directly. :meth:`JarvisImage.to_pil` imports Pillow lazily.
"""

from __future__ import annotations

import base64
import binascii
import io
import struct
from pathlib import Path
from typing import Any

MAX_IMAGES: int = 4
MAX_IMAGE_BYTES: int = 2 * 1024 * 1024  # 2 MiB, decoded

IMAGE_MIME_TYPES: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")

# The tool-schema property key/value that marks an image parameter.
IMAGE_SCHEMA_MARKER: str = "x-jarvis-type"
IMAGE_SCHEMA_MARKER_VALUE: str = "image"

# Every spelling JarvisParameter accepts for an image parameter. All mean the
# same thing (a list of images); JarvisParameter normalizes them to "image".
IMAGE_PARAM_TYPES: frozenset[str] = frozenset({"image", "array<image>", "array[image]", "image[]"})

_EXTENSIONS: dict[str, str] = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

# Base64 grows 4/3; anything longer than this cannot decode to <= MAX_IMAGE_BYTES.
_MAX_B64_CHARS: int = ((MAX_IMAGE_BYTES + 2) // 3) * 4


class ImageValidationError(ValueError):
    """An image argument was malformed, too large, too many, or not an image.

    Messages never contain the image data itself.
    """


def is_image_param_type(param_type: Any) -> bool:
    """True when ``param_type`` declares an image parameter (any accepted spelling)."""
    return isinstance(param_type, str) and param_type.strip() in IMAGE_PARAM_TYPES


def sniff_mime(data: bytes) -> str | None:
    """Return the image MIME type from the magic bytes, or None if not JPEG/PNG/WebP."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    i = 2
    n = len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:  # standalone markers
            i += 2
            continue
        if marker == 0xD9:  # EOI before any frame header
            return None
        (seg_len,) = struct.unpack(">H", data[i + 2:i + 4])
        if seg_len < 2:
            return None
        # SOF0..SOF15, excluding DHT (C4), JPG (C8) and DAC (CC)
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > n:
                return None
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + seg_len
    return None


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8 ":
        if len(data) < 30 or data[23:26] != b"\x9d\x01\x2a":
            return None
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L":
        if len(data) < 25 or data[20] != 0x2F:
            return None
        (bits,) = struct.unpack("<I", data[21:25])
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        if len(data) < 30:
            return None
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    return None


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from a JPEG/PNG/WebP header, or None if unparseable."""
    mime = sniff_mime(data)
    try:
        if mime == "image/jpeg":
            return _jpeg_size(data)
        if mime == "image/png":
            return _png_size(data)
        if mime == "image/webp":
            return _webp_size(data)
    except (struct.error, IndexError):  # pragma: no cover — defensive; parsers bounds-check
        return None
    return None


class JarvisImage:
    """One photo the user attached, as received by a command's ``run()``.

    The type is sniffed from the bytes; a ``mime`` claimed on the wire is never
    trusted. ``repr()`` shows type, size and dimensions only — never the bytes —
    so logging a JarvisImage is safe.
    """

    __forge_hints__ = {
        "role": "One user-attached photo passed to run() for a param_type='image' parameter",
        "constructor": "You don't construct these — run() receives list[JarvisImage] for an image parameter",
        "attributes": {
            "data": "bytes — the raw image file",
            "mime": "'image/jpeg' | 'image/png' | 'image/webp' (sniffed from the bytes)",
            "size_bytes": "int",
            "width": "int | None (read from the header)",
            "height": "int | None (read from the header)",
        },
        "methods": {
            "save(path)": "Write to disk; adds .jpg/.png/.webp if the path has no extension; returns the Path",
            "as_base64()": "Standard base64 string",
            "as_data_url()": "'data:image/jpeg;base64,...' — ready for a vision API's image_url",
            "to_pil()": "PIL.Image.Image (needs Pillow in required_packages)",
        },
        "tips": [
            "An image parameter is ALWAYS a list, even when the user attached one photo",
            "Photos arrive in the order the user attached them",
            "At most 4 photos, each at most 2 MiB",
            "Photos only come from mobile chat; voice requests never carry them, so make the parameter "
            "required=True if the command can't work without one",
        ],
        "example": (
            "def run(self, request_info, **kwargs):\n"
            "    photos = kwargs.get('photos') or []  # list[JarvisImage]\n"
            "    first = photos[0]\n"
            "    resp = vision_api(first.as_data_url())"
        ),
    }

    __slots__ = ("_data", "_mime", "_dims")

    def __init__(self, data: bytes, mime: str | None = None) -> None:
        """Wrap raw image bytes. ``mime`` is ignored in favor of the sniffed type.

        Raises:
            ImageValidationError: ``data`` is not JPEG, PNG or WebP.
        """
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ImageValidationError("image data must be bytes")
        raw = bytes(data)
        sniffed = sniff_mime(raw)
        if sniffed is None:
            raise ImageValidationError("not a JPEG, PNG or WebP image")
        self._data: bytes = raw
        self._mime: str = sniffed
        self._dims: tuple[int, int] | None = image_dimensions(raw)

    # ── Constructors ─────────────────────────────────────────────────

    @classmethod
    def from_base64(cls, b64: str, mime: str | None = None) -> "JarvisImage":
        """Decode standard base64 into a JarvisImage (size-checked before decoding)."""
        if not isinstance(b64, str):
            raise ImageValidationError("image data must be a base64 string")
        if len(b64) > _MAX_B64_CHARS:
            raise ImageValidationError(f"image is larger than {MAX_IMAGE_BYTES} bytes")
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise ImageValidationError("image data is not valid base64") from None
        if not raw:
            raise ImageValidationError("image data is empty")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ImageValidationError(f"image is larger than {MAX_IMAGE_BYTES} bytes")
        return cls(raw, mime)

    @classmethod
    def from_wire(cls, item: Any) -> "JarvisImage":
        """Build from one wire item ``{"mime": ..., "data": "<base64>"}``."""
        if isinstance(item, JarvisImage):
            return item
        if not isinstance(item, dict) or "data" not in item:
            raise ImageValidationError('each image must be an object {"mime": ..., "data": "<base64>"}')
        return cls.from_base64(item["data"], item.get("mime"))

    # ── Properties ───────────────────────────────────────────────────

    @property
    def data(self) -> bytes:
        return self._data

    @property
    def mime(self) -> str:
        return self._mime

    @property
    def size_bytes(self) -> int:
        return len(self._data)

    @property
    def width(self) -> int | None:
        return self._dims[0] if self._dims else None

    @property
    def height(self) -> int | None:
        return self._dims[1] if self._dims else None

    @property
    def extension(self) -> str:
        """File extension for the sniffed type, with the dot (".jpg", ".png", ".webp")."""
        return _EXTENSIONS[self._mime]

    # ── Conversions ──────────────────────────────────────────────────

    def save(self, path: str | Path) -> Path:
        """Write the image to ``path`` and return the path written.

        If ``path`` has no extension, the one matching the image type is added.
        Parent directories are created.
        """
        p = Path(path)
        if not p.suffix:
            p = p.with_name(p.name + self.extension)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self._data)
        return p

    def as_base64(self) -> str:
        return base64.b64encode(self._data).decode("ascii")

    def as_data_url(self) -> str:
        return f"data:{self._mime};base64,{self.as_base64()}"

    def to_wire(self) -> dict[str, str]:
        """The wire form ``{"mime": ..., "data": "<base64>"}``."""
        return {"mime": self._mime, "data": self.as_base64()}

    def to_pil(self) -> Any:
        """Open as a ``PIL.Image.Image``. Requires Pillow (imported lazily)."""
        try:
            from PIL import Image  # noqa: PLC0415 — optional dependency, imported on demand
        except ImportError:
            raise ImportError(
                "JarvisImage.to_pil() needs Pillow, which is not installed. "
                "Add JarvisPackage('Pillow') to your command's required_packages, "
                "or use .data / .save() / .as_data_url() instead."
            ) from None
        return Image.open(io.BytesIO(self._data))

    # ── Dunder ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        dims = f", {self.width}x{self.height}" if self._dims else ""
        return f"JarvisImage(mime={self._mime!r}, size_bytes={self.size_bytes}{dims})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, JarvisImage) and other._data == self._data

    def __hash__(self) -> int:
        return hash(self._data)


def coerce_images(value: Any, param_name: str = "image") -> list[JarvisImage]:
    """Turn a wire value into ``list[JarvisImage]``, validating as it goes.

    Accepts the wire list (``[{"mime", "data"}, ...]``), a single wire object
    (treated as a one-item list), or JarvisImage instances (idempotent).

    Raises:
        ImageValidationError: wrong shape, more than MAX_IMAGES, an item over
            MAX_IMAGE_BYTES, invalid base64, or bytes that aren't an image.
            The message names the parameter and the item number, never data.
    """
    if isinstance(value, (dict, JarvisImage)):
        value = [value]
    if not isinstance(value, list):
        raise ImageValidationError(f"Parameter '{param_name}' must be a list of images")
    if value and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
        raise ImageValidationError(
            f"Parameter '{param_name}' got photo numbers that were never swapped for photos — "
            "no photos are attached to this conversation"
        )
    if len(value) > MAX_IMAGES:
        raise ImageValidationError(f"Parameter '{param_name}' accepts at most {MAX_IMAGES} images, got {len(value)}")
    images: list[JarvisImage] = []
    for idx, item in enumerate(value, start=1):
        try:
            images.append(JarvisImage.from_wire(item))
        except ImageValidationError as e:
            raise ImageValidationError(f"Parameter '{param_name}', image {idx}: {e}") from None
    return images


def image_tool_schema(description: str | None) -> dict[str, Any]:
    """The JSON-schema property the model sees for an image parameter.

    An array of 1-based photo numbers, tagged with IMAGE_SCHEMA_MARKER so the
    server substitutes the photos' bytes before the call reaches the node.
    """
    hint = (
        f"Photo numbers: a list of integers, 1 = the first photo the user attached, "
        f"2 = the second, and so on (at most {MAX_IMAGES})."
    )
    return {
        "type": "array",
        "items": {"type": "integer", "minimum": 1},
        "maxItems": MAX_IMAGES,
        "description": f"{description.rstrip()} {hint}" if description else hint,
        IMAGE_SCHEMA_MARKER: IMAGE_SCHEMA_MARKER_VALUE,
    }
