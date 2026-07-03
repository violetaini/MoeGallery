import argparse
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Image
from app.utils.image_process import InvalidImageError, WEBP_EXTENSION, WEBP_MIME_TYPE, inspect_image, save_webp_image


@dataclass
class Summary:
    checked: int = 0
    converted: int = 0
    skipped_webp: int = 0
    skipped_animated: int = 0
    skipped_hdr: int = 0
    missing: int = 0
    failed: int = 0


def storage_path(relative_path: str) -> Path:
    base = settings.storage_path.resolve()
    target = (settings.storage_path / relative_path).resolve()
    target.relative_to(base)
    return target


def relative_storage_path(path: Path) -> str:
    return path.resolve().relative_to(settings.storage_path.resolve()).as_posix()


def converted_path(source: Path) -> Path:
    target = source.with_suffix(WEBP_EXTENSION)
    if not target.exists() or target.resolve() == source.resolve():
        return target

    index = 1
    while True:
        candidate = source.with_name(f"{source.stem}-converted-{index}{WEBP_EXTENSION}")
        if not candidate.exists():
            return candidate
        index += 1


def convert_image(image: Image, apply: bool, keep_source: bool) -> str:
    source = storage_path(image.file_path)
    if not source.exists() or not source.is_file():
        return "missing"

    data = source.read_bytes()
    inspection = inspect_image(data)
    image.is_animated = inspection.is_animated
    image.dynamic_range = inspection.dynamic_range
    image.bit_depth = inspection.bit_depth
    image.color_profile = inspection.color_profile
    image.width = inspection.width
    image.height = inspection.height
    if inspection.is_animated:
        return "animated"
    if inspection.dynamic_range == "hdr":
        return "hdr"

    if source.suffix.lower() == WEBP_EXTENSION and image.mime_type == WEBP_MIME_TYPE:
        return "webp"

    target = converted_path(source)
    temp = target.with_name(f"{target.name}.tmp")
    save_webp_image(data, temp)

    if not apply:
        temp.unlink(missing_ok=True)
        return "converted"

    temp.replace(target)
    if not keep_source and source.resolve() != target.resolve():
        source.unlink(missing_ok=True)

    image.filename = target.name
    image.file_path = relative_storage_path(target)
    image.mime_type = WEBP_MIME_TYPE
    image.file_size = target.stat().st_size
    return "converted"


def run(apply: bool, keep_source: bool) -> Summary:
    summary = Summary()
    with SessionLocal() as db:
        images = db.scalars(select(Image).order_by(Image.id)).all()
        for image in images:
            summary.checked += 1
            try:
                result = convert_image(image, apply=apply, keep_source=keep_source)
                if result == "converted":
                    summary.converted += 1
                    if apply:
                        db.commit()
                elif result == "webp":
                    summary.skipped_webp += 1
                    if apply:
                        db.commit()
                elif result == "animated":
                    summary.skipped_animated += 1
                    if apply:
                        db.commit()
                elif result == "hdr":
                    summary.skipped_hdr += 1
                    if apply:
                        db.commit()
                elif result == "missing":
                    summary.missing += 1
            except (InvalidImageError, OSError, ValueError) as exc:
                db.rollback()
                summary.failed += 1
                print(f"FAILED image_id={image.id} file_path={image.file_path}: {exc}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert existing static original images to WebP.")
    parser.add_argument("--apply", action="store_true", help="Write converted files and update database rows.")
    parser.add_argument("--keep-source", action="store_true", help="Keep old non-WebP original files after conversion.")
    args = parser.parse_args()

    summary = run(apply=args.apply, keep_source=args.keep_source)
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode}: checked={summary.checked} converted={summary.converted} "
        f"skipped_webp={summary.skipped_webp} skipped_animated={summary.skipped_animated} "
        f"skipped_hdr={summary.skipped_hdr} "
        f"missing={summary.missing} failed={summary.failed}"
    )


if __name__ == "__main__":
    main()
