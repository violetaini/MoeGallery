from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import struct

from PIL import Image as PillowImage
from PIL import ImageOps, UnidentifiedImageError

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except (ImportError, OSError):
    pass

try:
    import imagecodecs
    import numpy as np
except ImportError:
    imagecodecs = None
    np = None

MIME_BY_FORMAT = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "HEIF": "image/heif",
    "HEIC": "image/heic",
    "AVIF": "image/avif",
    "JXR": "image/jxr",
}
WEBP_EXTENSION = ".webp"
WEBP_MIME_TYPE = "image/webp"
AVIF_EXTENSION = ".avif"
AVIF_MIME_TYPE = "image/avif"
JXR_EXTENSION = ".jxr"
JXR_MIME_TYPE = "image/jxr"
WEBP_QUALITY = 86
WEBP_METHOD = 6
DYNAMIC_RANGE_SDR = "sdr"
DYNAMIC_RANGE_HDR = "hdr"
HDR_TRANSFER_CHARACTERISTICS = {16, 18}
WIDE_GAMUT_COLOR_PRIMARIES = {9}
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heif",
    ".heic",
    ".avif",
    ".jxr",
}
HDR_AVIF_CRF = 18
HDR_AVIF_CPU_USED = 4
# AVIF/HEIF mdcv uses display primaries in G, B, R order.
HDR_MASTERING_DISPLAY_PRIMARIES = (
    (8500, 39850),  # Green
    (6550, 2300),   # Blue
    (35400, 14600), # Red
)
HDR_MASTERING_WHITE_POINT = (15635, 16450)
HDR_MASTERING_MAX_LUMINANCE = 10000000
HDR_MASTERING_MIN_LUMINANCE = 1
HDR_LUMA_COEFFICIENTS_BT2020 = (0.2627, 0.6780, 0.0593)
SC_RGB_TO_BT2020_MATRIX = (
    (0.6274039, 0.3292830, 0.0433131),
    (0.0690973, 0.9195404, 0.0113623),
    (0.0163914, 0.0880132, 0.8955954),
)
PQ_M1 = 2610.0 / 16384.0
PQ_M2 = 2523.0 / 32.0
PQ_C1 = 3424.0 / 4096.0
PQ_C2 = 2413.0 / 128.0
PQ_C3 = 2392.0 / 128.0
PREFERRED_EXTENSION_BY_FORMAT = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
    "HEIF": ".heic",
    "AVIF": ".avif",
    "JXR": ".jxr",
}


@dataclass(frozen=True)
class ImageInspection:
    width: int
    height: int
    mime_type: str
    format_name: str
    extension: str
    is_animated: bool
    dynamic_range: str
    bit_depth: int
    color_profile: str | None = None


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class HdrStaticMetadata:
    max_content_light_level: int
    max_pic_average_light_level: int


def validate_upload_filename(filename: str | None) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix in SUPPORTED_UPLOAD_EXTENSIONS:
        return
    allowed = ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
    raise InvalidImageError(f"仅支持以下图片后缀上传: {allowed}")


def validate_hdr_upload(inspection: ImageInspection) -> None:
    if inspection.is_animated:
        raise InvalidImageError("仅允许录入 HDR 静态图片，动图已禁止上传")
    if inspection.dynamic_range != DYNAMIC_RANGE_HDR:
        raise InvalidImageError("仅允许录入 HDR 图片，非 HDR 图片已禁止上传")


def _is_jpegxr(data: bytes) -> bool:
    return bool(imagecodecs and getattr(imagecodecs, "jpegxr_check", None) and imagecodecs.jpegxr_check(data))


def _source_mime(format_name: str | None, custom_mime: str | None = None) -> str:
    if custom_mime:
        return custom_mime
    if not format_name:
        return "application/octet-stream"
    return MIME_BY_FORMAT.get(format_name, PillowImage.MIME.get(format_name, f"image/{format_name.lower()}"))


def _source_extension(format_name: str | None, custom_mime: str | None = None) -> str:
    if not format_name:
        return ".img"
    if custom_mime:
        if "avif" in custom_mime:
            return ".avif"
        if "heic" in custom_mime:
            return ".heic"
        if "heif" in custom_mime:
            return ".heif"
    format_name = format_name.upper()
    if format_name in PREFERRED_EXTENSION_BY_FORMAT:
        return PREFERRED_EXTENSION_BY_FORMAT[format_name]
    PillowImage.init()
    extensions = sorted(
        ext
        for ext, registered_format in PillowImage.EXTENSION.items()
        if registered_format == format_name
    )
    return extensions[0] if extensions else ".img"


def _is_animated(image: PillowImage.Image) -> bool:
    return bool(getattr(image, "is_animated", False) or getattr(image, "n_frames", 1) > 1)


def _first_frame(image: PillowImage.Image) -> PillowImage.Image:
    try:
        image.seek(0)
    except EOFError:
        pass
    return ImageOps.exif_transpose(image.copy())


def _webp_ready(image: PillowImage.Image) -> PillowImage.Image:
    has_alpha = "A" in image.getbands() or image.mode == "P" and "transparency" in image.info
    target_mode = "RGBA" if has_alpha else "RGB"
    if image.mode != target_mode:
        return image.convert(target_mode)
    return image


def _encode_webp_bytes(image: PillowImage.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, "WEBP", quality=WEBP_QUALITY, method=WEBP_METHOD)
    return stream.getvalue()


def _decode_jpegxr(data: bytes):
    if not imagecodecs or np is None:
        raise InvalidImageError("JPEG XR support requires imagecodecs")
    try:
        return imagecodecs.jpegxr_decode(data).astype(np.float32, copy=False)
    except Exception as exc:
        raise InvalidImageError("Unsupported or broken JPEG XR file") from exc


def _jpegxr_dynamic_range(decoded) -> str:
    if np is None:
        return DYNAMIC_RANGE_HDR
    rgb = decoded[..., :3] if decoded.ndim == 3 else decoded
    finite = np.nan_to_num(rgb, nan=0.0, posinf=0.0, neginf=0.0)
    max_value = float(np.max(finite)) if finite.size else 0.0
    min_value = float(np.min(finite)) if finite.size else 0.0
    if max_value > 1.0 or min_value < 0.0:
        return DYNAMIC_RANGE_HDR
    return DYNAMIC_RANGE_SDR


def _jpegxr_to_sdr_image(data: bytes, max_size: int | None = None) -> PillowImage.Image:
    decoded = _decode_jpegxr(data)
    if decoded.ndim == 2:
        decoded = decoded[..., None]

    channels = decoded.shape[2]
    rgb = np.nan_to_num(decoded[..., : min(3, channels)], nan=0.0, posinf=16.0, neginf=0.0).astype(np.float32, copy=False)
    rgb = np.maximum(rgb, 0.0)
    rgb = rgb / (1.0 + rgb)
    rgb = np.power(np.clip(rgb, 0.0, 1.0), 1 / 2.2)
    rgb8 = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)

    if rgb8.shape[2] == 1:
        image = PillowImage.fromarray(rgb8[..., 0], mode="L")
    else:
        mode = "RGB"
        if channels >= 4:
            alpha = np.nan_to_num(decoded[..., 3], nan=1.0, posinf=1.0, neginf=0.0).astype(np.float32, copy=False)
            alpha8 = np.clip(alpha * 255.0 + 0.5, 0, 255).astype(np.uint8)
            rgba8 = np.dstack([rgb8[..., :3], alpha8])
            image = PillowImage.fromarray(rgba8, mode="RGBA")
            mode = "RGBA"
        else:
            image = PillowImage.fromarray(rgb8[..., :3], mode=mode)

    image = ImageOps.exif_transpose(image)
    if max_size is not None:
        image.thumbnail((max_size, max_size))
    return image


def _jpegxr_to_bt2020_pq_u16(data: bytes):
    decoded = _decode_jpegxr(data)
    if decoded.ndim != 3 or decoded.shape[2] < 3:
        raise InvalidImageError("JPEG XR image must contain RGB channels")

    rgb = np.nan_to_num(decoded[..., :3], nan=0.0, posinf=16.0, neginf=0.0).astype(np.float32, copy=False)
    rgb = np.maximum(rgb, 0.0)
    matrix = np.asarray(SC_RGB_TO_BT2020_MATRIX, dtype=np.float32)
    rgb2020 = rgb @ matrix.T
    nits = np.clip(rgb2020 * 80.0, 0.0, 10000.0)
    luminance = np.clip(nits / 10000.0, 0.0, 1.0)
    luminance_m1 = np.power(luminance, PQ_M1)
    pq = np.power((PQ_C1 + PQ_C2 * luminance_m1) / (1.0 + PQ_C3 * luminance_m1), PQ_M2)
    encoded = np.clip(np.round(pq * 65535.0), 0, 65535).astype(np.uint16)
    luminance_nits = (
        rgb2020[..., 0] * HDR_LUMA_COEFFICIENTS_BT2020[0]
        + rgb2020[..., 1] * HDR_LUMA_COEFFICIENTS_BT2020[1]
        + rgb2020[..., 2] * HDR_LUMA_COEFFICIENTS_BT2020[2]
    )
    max_cll = int(np.clip(np.ceil(float(np.max(luminance_nits))) if luminance_nits.size else 0.0, 0.0, 65535.0))
    max_pall = int(np.clip(np.ceil(float(np.mean(luminance_nits))) if luminance_nits.size else 0.0, 0.0, 65535.0))
    metadata = HdrStaticMetadata(
        max_content_light_level=max_cll,
        max_pic_average_light_level=max_pall,
    )
    return encoded, metadata


def _read_box_size(buffer: bytes | bytearray, offset: int) -> int:
    return struct.unpack_from(">I", buffer, offset)[0]


def _write_box_size(buffer: bytearray, offset: int, size: int) -> None:
    struct.pack_into(">I", buffer, offset, size)


def _find_box_path(buffer: bytes | bytearray, start: int, end: int, path: tuple[str, ...]):
    position = start
    target = path[0]
    while position + 8 <= end:
        size = _read_box_size(buffer, position)
        box_type = bytes(buffer[position + 4 : position + 8]).decode("latin1")
        header_size = 8
        if size == 1:
            size = struct.unpack_from(">Q", buffer, position + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        box_end = position + size
        content_start = position + header_size + (4 if box_type == "meta" else 0)
        if box_type == target:
            if len(path) == 1:
                return position, size, content_start, box_end
            return _find_box_path(buffer, content_start, box_end, path[1:])
        position = box_end
    raise InvalidImageError(f"Required AVIF box path not found: {'/'.join(path)}")


def _build_mdcv_box() -> bytes:
    payload = struct.pack(
        ">6H2H2I",
        HDR_MASTERING_DISPLAY_PRIMARIES[0][0],
        HDR_MASTERING_DISPLAY_PRIMARIES[0][1],
        HDR_MASTERING_DISPLAY_PRIMARIES[1][0],
        HDR_MASTERING_DISPLAY_PRIMARIES[1][1],
        HDR_MASTERING_DISPLAY_PRIMARIES[2][0],
        HDR_MASTERING_DISPLAY_PRIMARIES[2][1],
        HDR_MASTERING_WHITE_POINT[0],
        HDR_MASTERING_WHITE_POINT[1],
        HDR_MASTERING_MAX_LUMINANCE,
        HDR_MASTERING_MIN_LUMINANCE,
    )
    return struct.pack(">I4s", 8 + len(payload), b"mdcv") + payload


def _build_clli_box(metadata: HdrStaticMetadata) -> bytes:
    payload = struct.pack(
        ">2H",
        metadata.max_content_light_level,
        metadata.max_pic_average_light_level,
    )
    return struct.pack(">I4s", 8 + len(payload), b"clli") + payload


def _patch_avif_hdr_boxes(avif_path: Path, metadata: HdrStaticMetadata) -> None:
    data = bytearray(avif_path.read_bytes())
    meta = _find_box_path(data, 0, len(data), ("meta",))
    iprp = _find_box_path(data, meta[2], meta[3], ("iprp",))
    ipco = _find_box_path(data, iprp[2], iprp[3], ("ipco",))
    ipma = _find_box_path(data, iprp[2], iprp[3], ("ipma",))
    iloc = _find_box_path(data, meta[2], meta[3], ("iloc",))
    mdat = _find_box_path(data, 0, len(data), ("mdat",))

    if b"mdcv" in data and b"clli" in data:
        avif_path.write_bytes(data)
        return

    property_blob = _build_mdcv_box() + _build_clli_box(metadata)
    insert_at = ipco[3]
    data[insert_at:insert_at] = property_blob
    property_delta = len(property_blob)

    _write_box_size(data, ipco[0], ipco[1] + property_delta)
    _write_box_size(data, iprp[0], iprp[1] + property_delta)
    _write_box_size(data, meta[0], meta[1] + property_delta)

    # ipma is located after ipco; iloc is before ipco and does not move.
    ipma_offset = ipma[0] + property_delta
    ipma_content = ipma[2] + property_delta
    entry_count_offset = ipma_content + 4
    item_id_offset = entry_count_offset + 4
    association_count_offset = item_id_offset + 2
    association_data_offset = association_count_offset + 1
    association_count = data[association_count_offset]
    data[association_count_offset] = association_count + 2
    data[association_data_offset + association_count : association_data_offset + association_count] = bytes([5, 6])
    _write_box_size(data, ipma_offset, ipma[1] + 2)
    _write_box_size(data, iprp[0], _read_box_size(data, iprp[0]) + 2)
    _write_box_size(data, meta[0], _read_box_size(data, meta[0]) + 2)

    total_delta = property_delta + 2

    iloc_payload = memoryview(data)[iloc[2] : iloc[3]]
    version = iloc_payload[0]
    if version not in (0, 1, 2):
        raise InvalidImageError(f"Unsupported iloc version: {version}")
    offset_size = iloc_payload[4] >> 4
    length_size = iloc_payload[4] & 0x0F
    base_offset_size = iloc_payload[5] >> 4
    index_size = iloc_payload[5] & 0x0F if version in (1, 2) else 0
    if version < 2:
        item_count = int.from_bytes(iloc_payload[6:8], "big")
        payload_offset = 8
    else:
        item_count = iloc_payload[6]
        payload_offset = 7

    for _ in range(item_count):
        payload_offset += 2  # item_id
        if version in (1, 2):
            payload_offset += 2  # construction_method
        payload_offset += 2  # data_reference_index
        payload_offset += base_offset_size
        extent_count = int.from_bytes(iloc_payload[payload_offset : payload_offset + 2], "big")
        payload_offset += 2
        for __ in range(extent_count):
            if version in (1, 2) and index_size:
                payload_offset += index_size
            extent_offset_position = payload_offset
            extent_offset = int.from_bytes(
                iloc_payload[extent_offset_position : extent_offset_position + offset_size],
                "big",
            )
            payload_offset += offset_size
            if extent_offset >= mdat[0]:
                new_offset = extent_offset + total_delta
                data[
                    iloc[2] + extent_offset_position : iloc[2] + extent_offset_position + offset_size
                ] = new_offset.to_bytes(offset_size, "big")
            payload_offset += length_size

    avif_path.write_bytes(data)


def _bit_depth_from_mode(mode: str) -> int:
    mode = mode or ""
    if ";16" in mode or mode in {"I", "I;16", "I;16B", "I;16L", "F"}:
        return 16
    if ";12" in mode:
        return 12
    if ";10" in mode:
        return 10
    return 8


def _nclx_value(nclx_profile: object, key: str) -> int | None:
    if not isinstance(nclx_profile, dict):
        return None
    value = nclx_profile.get(key)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _color_profile_name(image: PillowImage.Image) -> str | None:
    nclx = image.info.get("nclx_profile")
    transfer = _nclx_value(nclx, "transfer_characteristics")
    primaries = _nclx_value(nclx, "color_primaries")
    if transfer == 16:
        return "bt2100-pq"
    if transfer == 18:
        return "bt2100-hlg"
    if primaries == 9:
        return "bt2020"
    if image.info.get("icc_profile"):
        return "icc"
    return None


def _dynamic_range(image: PillowImage.Image, bit_depth: int) -> str:
    nclx = image.info.get("nclx_profile")
    transfer = _nclx_value(nclx, "transfer_characteristics")
    primaries = _nclx_value(nclx, "color_primaries")
    if bit_depth > 8:
        return DYNAMIC_RANGE_HDR
    if transfer in HDR_TRANSFER_CHARACTERISTICS:
        return DYNAMIC_RANGE_HDR
    if bit_depth > 8 and primaries in WIDE_GAMUT_COLOR_PRIMARIES:
        return DYNAMIC_RANGE_HDR
    if bit_depth > 8 and image.format in {"HEIF", "AVIF"}:
        return DYNAMIC_RANGE_HDR
    return DYNAMIC_RANGE_SDR


def inspect_image(data: bytes) -> ImageInspection:
    if _is_jpegxr(data):
        decoded = _decode_jpegxr(data)
        height, width = decoded.shape[:2]
        return ImageInspection(
            width=width,
            height=height,
            mime_type="image/jxr",
            format_name="JXR",
            extension=".jxr",
            is_animated=False,
            dynamic_range=_jpegxr_dynamic_range(decoded),
            bit_depth=16,
            color_profile="scRGB",
        )

    try:
        with PillowImage.open(BytesIO(data)) as image:
            fmt = image.format
            source_mime = _source_mime(fmt, getattr(image, "custom_mimetype", None))
            image.verify()
        with PillowImage.open(BytesIO(data)) as image:
            fmt = image.format
            is_animated = _is_animated(image)
            normalized = _first_frame(image)
            width, height = normalized.size
            heif_bit_depth = image.info.get("bit_depth")
            try:
                heif_bit_depth = int(heif_bit_depth) if heif_bit_depth is not None else None
            except (TypeError, ValueError):
                heif_bit_depth = None
            bit_depth = max(heif_bit_depth or 0, _bit_depth_from_mode(image.mode), _bit_depth_from_mode(normalized.mode))
            color_profile = _color_profile_name(image)
            dynamic_range = _dynamic_range(image, bit_depth)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("Unsupported or broken image file") from exc

    if not fmt:
        raise InvalidImageError("Unsupported image format")

    return ImageInspection(
        width=width,
        height=height,
        mime_type=source_mime,
        format_name=fmt,
        extension=_source_extension(fmt, source_mime),
        is_animated=is_animated,
        dynamic_range=dynamic_range,
        bit_depth=bit_depth,
        color_profile=color_profile,
    )


def save_hdr_avif_image(data: bytes, destination: Path) -> None:
    if not _is_jpegxr(data):
        raise InvalidImageError("HDR AVIF transcoding currently supports JPEG XR input only")
    if imagecodecs is None or np is None:
        raise InvalidImageError("HDR AVIF transcoding requires imagecodecs")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise InvalidImageError("HDR AVIF transcoding requires ffmpeg")

    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded, metadata = _jpegxr_to_bt2020_pq_u16(data)

    with tempfile.TemporaryDirectory(prefix="agms-jxr-avif-") as temp_dir:
        temp_input = Path(temp_dir) / "source.tiff"
        temp_output = Path(temp_dir) / "output.avif"
        try:
            temp_input.write_bytes(imagecodecs.tiff_encode(encoded))
        except Exception as exc:
            raise InvalidImageError("Unable to prepare HDR source frame for AVIF encoding") from exc

        command = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(temp_input),
            "-vf",
            "setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=tv",
            "-frames:v",
            "1",
            "-c:v",
            "libaom-av1",
            "-still-picture",
            "1",
            "-bsf:v",
            "av1_metadata=color_primaries=9:transfer_characteristics=16:matrix_coefficients=9:color_range=0",
            "-pix_fmt",
            "yuv444p10le",
            "-crf",
            str(HDR_AVIF_CRF),
            "-cpu-used",
            str(HDR_AVIF_CPU_USED),
            str(temp_output),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or "ffmpeg failed"
            raise InvalidImageError(f"Unable to encode HDR AVIF: {detail}") from exc

        if not temp_output.exists():
            raise InvalidImageError("Unable to encode HDR AVIF: output file missing")

        _patch_avif_hdr_boxes(temp_output, metadata)
        shutil.copyfile(temp_output, destination)


def save_webp_image(data: bytes, destination: Path, max_size: int | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(render_webp_preview_bytes(data, max_size=max_size))


def render_webp_preview_bytes(data: bytes, max_size: int | None = None) -> bytes:
    if _is_jpegxr(data):
        try:
            image = _jpegxr_to_sdr_image(data, max_size=max_size)
            image = _webp_ready(image)
            return _encode_webp_bytes(image)
        except (InvalidImageError, OSError, ValueError) as exc:
            raise InvalidImageError("Unable to convert JPEG XR image to WebP") from exc
    try:
        with PillowImage.open(BytesIO(data)) as image:
            image = _first_frame(image)
            if max_size is not None:
                image.thumbnail((max_size, max_size))
            image = _webp_ready(image)
            return _encode_webp_bytes(image)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("Unable to convert image to WebP") from exc


def save_webp_derivative(data: bytes, destination: Path, max_size: int) -> None:
    save_webp_image(data, destination, max_size=max_size)
