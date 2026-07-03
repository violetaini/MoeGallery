import hashlib
from io import BytesIO

from PIL import Image as PillowImage
from PIL import ImageOps, UnidentifiedImageError


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def average_hash_bytes(data: bytes, hash_size: int = 8) -> str:
    if hash_size < 4 or hash_size > 16:
        raise ValueError("hash_size must be between 4 and 16")
    try:
        with PillowImage.open(BytesIO(data)) as image:
            try:
                image.seek(0)
            except EOFError:
                pass
            normalized = ImageOps.exif_transpose(image.copy()).convert("L")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unsupported image for perceptual hash") from exc

    resampling = getattr(PillowImage, "Resampling", PillowImage).LANCZOS
    normalized = normalized.resize((hash_size, hash_size), resampling)
    pixels = list(normalized.getdata())
    average = sum(pixels) / len(pixels)
    value = 0
    for pixel in pixels:
        value = (value << 1) | int(pixel >= average)
    return f"{value:0{hash_size * hash_size // 4}x}"
