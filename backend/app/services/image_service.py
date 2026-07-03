from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Character, Image, Tag, Work
from app.services.storage_service import delete_storage_file, save_image_files
from app.utils.hash import average_hash_bytes, sha256_bytes
from app.utils.image_process import InvalidImageError, inspect_image, render_webp_preview_bytes, validate_upload_filename


class ImageService:
    def __init__(self, db: Session):
        self.db = db

    def create_from_bytes(
        self,
        data: bytes,
        original_filename: str | None,
        content_type: str | None,
        rating: str = "safe",
        is_public: bool = True,
        source_url: str | None = None,
        artist_name: str | None = None,
        work_ids: list[int] | None = None,
        character_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        merge_duplicate_relations: bool = False,
    ) -> tuple[Image, bool]:
        if not data:
            raise ValueError("Empty upload")
        if len(data) > settings.max_upload_size:
            raise ValueError("File is larger than configured upload limit")

        validate_upload_filename(original_filename)
        inspection = inspect_image(data)
        # Browser supplied MIME is advisory; Pillow detection is authoritative.

        sha256 = sha256_bytes(data)
        existing = self.db.scalar(select(Image).where(Image.sha256 == sha256))
        if existing:
            if merge_duplicate_relations:
                self._apply_relations(existing, work_ids, character_ids, tag_ids)
                self.db.commit()
                self.db.refresh(existing)
            return existing, True

        phash = self._create_phash(data)
        paths = save_image_files(data, sha256, original_filename, inspection)
        image = Image(
            filename=paths["filename"],
            original_filename=paths["original_filename"],
            file_path=paths["file_path"],
            preview_path=paths["preview_path"],
            thumbnail_path=paths["thumbnail_path"],
            width=inspection.width,
            height=inspection.height,
            file_size=paths["file_size"],
            mime_type=paths["mime_type"],
            is_animated=inspection.is_animated,
            dynamic_range=paths["dynamic_range"],
            bit_depth=paths["bit_depth"],
            color_profile=paths["color_profile"],
            sha256=sha256,
            phash=phash,
            rating=rating,
            is_public=is_public,
            source_url=source_url,
            artist_name=artist_name,
        )
        self._apply_relations(image, work_ids, character_ids, tag_ids)
        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)
        return image, False

    def _create_phash(self, data: bytes) -> str | None:
        try:
            return average_hash_bytes(data)
        except ValueError:
            try:
                preview = render_webp_preview_bytes(data, max_size=256)
                return average_hash_bytes(preview)
            except (InvalidImageError, ValueError):
                return None

    def update_relations(
        self,
        image: Image,
        work_ids: list[int] | None = None,
        character_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
    ) -> None:
        self._apply_relations(image, work_ids, character_ids, tag_ids)

    def delete_image(self, image: Image) -> None:
        paths = [image.file_path, image.preview_path, image.thumbnail_path]
        self.db.delete(image)
        self.db.commit()
        for path in paths:
            delete_storage_file(path)

    def _apply_relations(
        self,
        image: Image,
        work_ids: list[int] | None,
        character_ids: list[int] | None,
        tag_ids: list[int] | None,
    ) -> None:
        if work_ids is not None:
            image.works = list(self.db.scalars(select(Work).where(Work.id.in_(work_ids))).all()) if work_ids else []
        if character_ids is not None:
            image.characters = (
                list(self.db.scalars(select(Character).where(Character.id.in_(character_ids))).all())
                if character_ids
                else []
            )
        if tag_ids is not None:
            image.tags = list(self.db.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all()) if tag_ids else []
