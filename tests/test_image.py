"""Tests for image parameters: JarvisImage, coercion, schema export, execute()."""

import base64
import builtins
import json
import struct
import zlib
from pathlib import Path

import pytest

from jarvis_command_sdk import (
    IMAGE_SCHEMA_MARKER,
    MAX_IMAGE_BYTES,
    MAX_IMAGES,
    CommandExample,
    CommandResponse,
    IJarvisCommand,
    ImageValidationError,
    JarvisImage,
    JarvisParameter,
    RequestInformation,
    coerce_images,
)
from jarvis_command_sdk.forge import generate_spec, generate_spec_markdown
from jarvis_command_sdk.image import image_dimensions, is_image_param_type, sniff_mime


# ── Fixtures: minimal real headers ────────────────────────────────────


def make_png(width: int = 3, height: int = 2) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def make_jpeg(width: int = 640, height: int = 480, sof: int = 0xC0) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    dht = b"\xff\xc4" + struct.pack(">H", 4) + b"\x00\x00"  # must be skipped, not read as a frame
    sof_seg = bytes([0xFF, sof]) + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + dht + b"\xff" + sof_seg + b"\xff\xd9"


def make_webp_vp8(width: int = 100, height: int = 50) -> bytes:
    payload = b"\x00\x00\x00" + b"\x9d\x01\x2a" + struct.pack("<HH", width, height) + b"\x00" * 4
    body = b"WEBP" + b"VP8 " + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def make_webp_vp8l(width: int = 7, height: int = 9) -> bytes:
    bits = (width - 1) | ((height - 1) << 14)
    payload = b"\x2f" + struct.pack("<I", bits) + b"\x00" * 4
    body = b"WEBP" + b"VP8L" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def make_webp_vp8x(width: int = 1920, height: int = 1080) -> bytes:
    payload = b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    body = b"WEBP" + b"VP8X" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body


def wire(data: bytes, mime: str = "image/jpeg") -> dict:
    return {"mime": mime, "data": base64.b64encode(data).decode()}


# ── Sniffing + dimensions ─────────────────────────────────────────────


class TestSniffAndDimensions:
    @pytest.mark.parametrize(
        "data,mime,dims",
        [
            (make_png(3, 2), "image/png", (3, 2)),
            (make_jpeg(640, 480), "image/jpeg", (640, 480)),
            (make_jpeg(800, 600, sof=0xC2), "image/jpeg", (800, 600)),  # progressive
            (make_webp_vp8(100, 50), "image/webp", (100, 50)),
            (make_webp_vp8l(7, 9), "image/webp", (7, 9)),
            (make_webp_vp8x(1920, 1080), "image/webp", (1920, 1080)),
        ],
    )
    def test_known_formats(self, data, mime, dims):
        assert sniff_mime(data) == mime
        assert image_dimensions(data) == dims

    def test_not_an_image(self):
        assert sniff_mime(b"GIF89a....") is None
        assert image_dimensions(b"hello") is None

    @pytest.mark.parametrize(
        "data",
        [
            b"\xff\xd8\xff",  # JPEG magic, nothing else
            b"\xff\xd8\xff\xe0\x00\x01",  # bad segment length
            b"\xff\xd8\xff\xe0\x00\x04\x00\x00" + b"\x00" * 8,  # junk where a marker should be
            b"\xff\xd8\xff\xd9\x00\x00",  # EOI before frame
            b"\xff\xd8\xff\xc0\x00\x11\x08",  # truncated SOF
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 8,  # PNG without IHDR
            b"RIFF\x00\x00\x00\x00WEBPVP8 \x00",  # truncated VP8
            b"RIFF\x00\x00\x00\x00WEBPVP8L" + b"\x00" * 13,  # VP8L bad signature
            b"RIFF\x00\x00\x00\x00WEBPVP8X\x00",  # truncated VP8X
            b"RIFF\x00\x00\x00\x00WEBPABCD" + b"\x00" * 20,  # unknown chunk
        ],
    )
    def test_unparseable_headers_give_none(self, data):
        assert image_dimensions(data) is None

    def test_jpeg_skips_fill_and_standalone_markers(self):
        data = make_jpeg(10, 20)
        # FF FF 01 = a fill byte then TEM; FF D0 = RST0. Both standalone, both skipped.
        data = data[:2] + b"\xff\xd0" + b"\xff\xff\x01" + data[2:]
        assert image_dimensions(data) == (10, 20)


# ── JarvisImage ───────────────────────────────────────────────────────


class TestJarvisImage:
    def test_attributes(self):
        data = make_jpeg(640, 480)
        img = JarvisImage(data)
        assert img.data == data
        assert img.mime == "image/jpeg"
        assert img.size_bytes == len(data)
        assert (img.width, img.height) == (640, 480)
        assert img.extension == ".jpg"

    def test_mime_is_sniffed_not_trusted(self):
        img = JarvisImage.from_wire(wire(make_png(), mime="image/jpeg"))
        assert img.mime == "image/png"

    def test_dimensions_none_when_unparseable(self):
        img = JarvisImage(b"\xff\xd8\xff\xe0\x00")
        assert img.width is None and img.height is None
        assert "x" not in repr(img).split("size_bytes")[1]

    def test_rejects_non_image_bytes(self):
        with pytest.raises(ImageValidationError, match="not a JPEG, PNG or WebP"):
            JarvisImage(b"%PDF-1.4 nope")

    def test_rejects_non_bytes(self):
        with pytest.raises(ImageValidationError, match="must be bytes"):
            JarvisImage("abc")  # type: ignore[arg-type]

    def test_accepts_bytearray(self):
        assert JarvisImage(bytearray(make_png())).mime == "image/png"

    def test_base64_and_data_url_round_trip(self):
        data = make_webp_vp8()
        img = JarvisImage(data)
        assert base64.b64decode(img.as_base64()) == data
        assert img.as_data_url() == "data:image/webp;base64," + img.as_base64()
        assert JarvisImage.from_wire(img.to_wire()) == img

    def test_repr_never_contains_data(self):
        img = JarvisImage(make_png(3, 2))
        r = repr(img)
        assert r == f"JarvisImage(mime='image/png', size_bytes={img.size_bytes}, 3x2)"
        assert img.as_base64() not in r

    def test_eq_and_hash(self):
        a, b = JarvisImage(make_png()), JarvisImage(make_png())
        assert a == b and hash(a) == hash(b)
        assert a != JarvisImage(make_jpeg())
        assert a != "not an image"

    def test_save_adds_extension(self, tmp_path: Path):
        img = JarvisImage(make_png())
        out = img.save(tmp_path / "sub" / "plant")
        assert out == tmp_path / "sub" / "plant.png"
        assert out.read_bytes() == img.data

    def test_save_keeps_given_extension(self, tmp_path: Path):
        img = JarvisImage(make_jpeg())
        out = img.save(str(tmp_path / "x.jpeg"))
        assert out == tmp_path / "x.jpeg"
        assert out.read_bytes() == img.data

    def test_to_pil_without_pillow(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "PIL" or name.startswith("PIL."):
                raise ImportError("no PIL")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(ImportError, match="needs Pillow"):
            JarvisImage(make_png()).to_pil()

    def test_to_pil_with_pillow(self):
        pil = pytest.importorskip("PIL.Image")
        im = JarvisImage(make_png(3, 2)).to_pil()
        assert isinstance(im, pil.Image)
        assert im.size == (3, 2)

    def test_from_base64_rejects_bad_input(self):
        with pytest.raises(ImageValidationError, match="base64 string"):
            JarvisImage.from_base64(123)  # type: ignore[arg-type]
        with pytest.raises(ImageValidationError, match="not valid base64"):
            JarvisImage.from_base64("!!!notbase64")
        with pytest.raises(ImageValidationError, match="empty"):
            JarvisImage.from_base64("")

    def test_from_wire_rejects_wrong_shape(self):
        with pytest.raises(ImageValidationError, match="must be an object"):
            JarvisImage.from_wire("abc")
        with pytest.raises(ImageValidationError, match="must be an object"):
            JarvisImage.from_wire({"mime": "image/png"})

    def test_from_wire_passes_through_jarvis_image(self):
        img = JarvisImage(make_png())
        assert JarvisImage.from_wire(img) is img


# ── Coercion ──────────────────────────────────────────────────────────


class TestCoerceImages:
    def test_wire_list_in_order(self):
        items = [wire(make_png()), wire(make_jpeg()), wire(make_webp_vp8())]
        imgs = coerce_images(items, "photos")
        assert [i.mime for i in imgs] == ["image/png", "image/jpeg", "image/webp"]
        assert all(isinstance(i, JarvisImage) for i in imgs)

    def test_single_object_becomes_list(self):
        imgs = coerce_images(wire(make_png()), "photos")
        assert len(imgs) == 1

    def test_idempotent(self):
        imgs = coerce_images([wire(make_png())], "photos")
        assert coerce_images(imgs, "photos") == imgs
        assert coerce_images(imgs[0], "photos") == imgs

    def test_empty_list(self):
        assert coerce_images([], "photos") == []

    def test_too_many(self):
        with pytest.raises(ImageValidationError, match=f"at most {MAX_IMAGES} images, got 5"):
            coerce_images([wire(make_png())] * (MAX_IMAGES + 1), "photos")

    def test_exactly_max_ok(self):
        assert len(coerce_images([wire(make_png())] * MAX_IMAGES, "photos")) == MAX_IMAGES

    def test_too_big_decoded(self):
        big = make_jpeg() + b"\x00" * (MAX_IMAGE_BYTES - len(make_jpeg()) + 1)
        with pytest.raises(ImageValidationError, match="image 1: image is larger than"):
            coerce_images([wire(big)], "photos")

    def test_exactly_max_bytes_ok(self):
        exact = make_jpeg() + b"\x00" * (MAX_IMAGE_BYTES - len(make_jpeg()))
        assert coerce_images([wire(exact)], "photos")[0].size_bytes == MAX_IMAGE_BYTES

    def test_too_big_rejected_before_decoding(self):
        huge = "A" * (MAX_IMAGE_BYTES * 2)
        with pytest.raises(ImageValidationError, match="larger than"):
            coerce_images([{"mime": "image/jpeg", "data": huge}], "photos")

    def test_bad_base64_names_item(self):
        with pytest.raises(ImageValidationError, match=r"Parameter 'photos', image 2: image data is not valid base64"):
            coerce_images([wire(make_png()), {"mime": "image/png", "data": "@@@@"}], "photos")

    def test_non_image_bytes(self):
        with pytest.raises(ImageValidationError, match="not a JPEG, PNG or WebP"):
            coerce_images([wire(b"GIF89a" + b"\x00" * 20, "image/gif")], "photos")

    def test_not_a_list(self):
        with pytest.raises(ImageValidationError, match="must be a list of images"):
            coerce_images("nope", "photos")

    def test_unsubstituted_photo_numbers(self):
        with pytest.raises(ImageValidationError, match="never swapped for photos"):
            coerce_images([1, 2], "photos")

    def test_error_messages_never_contain_data(self):
        payload = base64.b64encode(b"NOTANIMAGE" * 50).decode()
        with pytest.raises(ImageValidationError) as exc:
            coerce_images([{"mime": "image/png", "data": payload}], "photos")
        assert payload not in str(exc.value)
        assert payload[:20] not in str(exc.value)


# ── JarvisParameter ───────────────────────────────────────────────────


class TestImageParameter:
    @pytest.mark.parametrize("spelling", ["image", "array<image>", "array[image]", "image[]"])
    def test_aliases_normalize(self, spelling):
        p = JarvisParameter("photos", spelling, required=True)
        assert p.param_type == "image"
        assert is_image_param_type(spelling)

    def test_is_image_param_type_rejects_others(self):
        assert not is_image_param_type("string")
        assert not is_image_param_type(None)

    def test_validate_type_is_list(self):
        p = JarvisParameter("photos", "image", required=True)
        assert p.validate([JarvisImage(make_png())]) == (True, None)
        ok, msg = p.validate("x")
        assert not ok and "must be of type image" in msg

    def test_to_dict_type(self):
        assert JarvisParameter("photos", "array<image>").to_dict()["type"] == "image"


# ── Command integration ───────────────────────────────────────────────


class PlantCommand(IJarvisCommand):
    def __init__(self, required: bool = True):
        self._required = required
        self.received: dict | None = None

    @property
    def command_name(self) -> str:
        return "identify_plant"

    @property
    def description(self) -> str:
        return "Identify a plant from a photo"

    @property
    def parameters(self):
        return [
            JarvisParameter("photos", "image", required=self._required, description="Photos of the plant."),
            JarvisParameter("note", "string", required=False),
        ]

    @property
    def required_secrets(self):
        return []

    @property
    def keywords(self):
        return ["plant"]

    def generate_prompt_examples(self):
        return [CommandExample("what plant is this", {"photos": [1]}, is_primary=True)]

    def generate_adapter_examples(self):
        return self.generate_prompt_examples()

    def run(self, request_info, **kwargs):
        self.received = kwargs
        return CommandResponse.success_response(context_data={"n": len(kwargs.get("photos") or [])})


RI = RequestInformation(voice_command="what plant is this", conversation_id="c1")


class TestToolSchema:
    def test_image_property(self):
        schema = PlantCommand().to_openai_tool_schema()
        prop = schema["function"]["parameters"]["properties"]["photos"]
        assert prop[IMAGE_SCHEMA_MARKER] == "image"
        assert IMAGE_SCHEMA_MARKER == "x-jarvis-type"
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "integer", "minimum": 1}
        assert prop["maxItems"] == MAX_IMAGES
        assert prop["description"].startswith("Photos of the plant. Photo numbers:")
        assert "1 = the first photo" in prop["description"]
        assert schema["function"]["parameters"]["required"] == ["photos"]

    def test_optional_not_required(self):
        schema = PlantCommand(required=False).to_openai_tool_schema()
        assert schema["function"]["parameters"]["required"] == []

    def test_no_description(self):
        class Bare(PlantCommand):
            @property
            def parameters(self):
                return [JarvisParameter("photos", "image")]

        prop = Bare().to_openai_tool_schema()["function"]["parameters"]["properties"]["photos"]
        assert prop["description"].startswith("Photo numbers:")

    def test_marker_survives_json_round_trip(self):
        # report_tools POSTs client_tools as JSON; the marker must survive it.
        schema = json.loads(json.dumps(PlantCommand().to_openai_tool_schema()))
        assert schema["function"]["parameters"]["properties"]["photos"]["x-jarvis-type"] == "image"

    def test_command_schema_param_type(self):
        params = PlantCommand().get_command_schema()["parameters"]
        assert params[0]["type"] == "image"


class TestExecute:
    def test_run_gets_list_of_jarvis_image(self):
        cmd = PlantCommand()
        resp = cmd.execute(RI, photos=[wire(make_jpeg(640, 480)), wire(make_png())])
        assert resp.success
        photos = cmd.received["photos"]
        assert [type(p) for p in photos] == [JarvisImage, JarvisImage]
        assert (photos[0].width, photos[0].height) == (640, 480)
        assert photos[1].mime == "image/png"

    def test_single_photo_still_a_list(self):
        cmd = PlantCommand()
        cmd.execute(RI, photos=[wire(make_png())])
        assert isinstance(cmd.received["photos"], list) and len(cmd.received["photos"]) == 1

    def test_missing_required_raises(self):
        with pytest.raises(ValueError, match="Missing required params: photos"):
            PlantCommand().execute(RI)

    def test_empty_list_required_is_validation_error(self):
        resp = PlantCommand().execute(RI, photos=[])
        assert not resp.success
        assert resp.context_data["_validation_error"] is True
        assert "needs at least one photo" in resp.error_details

    def test_empty_list_optional_ok(self):
        cmd = PlantCommand(required=False)
        assert cmd.execute(RI, photos=[]).success
        assert cmd.received["photos"] == []

    def test_optional_absent_not_injected(self):
        cmd = PlantCommand(required=False)
        assert cmd.execute(RI, note="hi").success
        assert "photos" not in cmd.received

    def test_bad_image_is_validation_error(self):
        cmd = PlantCommand()
        resp = cmd.execute(RI, photos=[wire(make_png())] * 5)
        assert not resp.success
        assert resp.context_data["errors"][0]["param"] == "photos"
        assert "at most 4" in resp.error_details
        assert cmd.received is None

    def test_unsubstituted_numbers_are_validation_error(self):
        resp = PlantCommand().execute(RI, photos=[1])
        assert not resp.success
        assert "no photos are attached" in resp.error_details

    def test_already_coerced_passes(self):
        cmd = PlantCommand()
        imgs = [JarvisImage(make_png())]
        assert cmd.execute(RI, photos=imgs).success
        assert cmd.received["photos"] == imgs


class TestForge:
    def test_image_in_manifest_param_types(self):
        spec = generate_spec()
        valid = spec["manifest_schema"]["fields"]["parameters"]["item_fields"]["param_type"]["valid_values"]
        assert "image" in valid

    def test_jarvis_image_documented(self):
        spec = generate_spec()
        assert "JarvisImage" in spec["supporting_classes"]
        assert "image" in spec["supporting_classes"]["JarvisParameter"]["forge_hints"]["allowed_types"]
        assert "JarvisImage" in generate_spec_markdown()


def test_exports():
    import jarvis_command_sdk

    for name in ("JarvisImage", "ImageValidationError", "coerce_images", "MAX_IMAGES", "MAX_IMAGE_BYTES",
                 "IMAGE_SCHEMA_MARKER", "IMAGE_MIME_TYPES"):
        assert name in jarvis_command_sdk.__all__
    assert jarvis_command_sdk.__version__ == "0.11.0"
