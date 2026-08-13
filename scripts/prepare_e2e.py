#!/usr/bin/env python3
"""Create isolated database and storage fixtures for browser end-to-end tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from io import BytesIO
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, help="Disposable directory whose name must contain e2e")
    return parser.parse_args()


def ensure_disposable_workspace(raw_workspace: str) -> Path:
    workspace = Path(raw_workspace).expanduser().resolve()
    if "e2e" not in workspace.name.lower() or workspace == Path(workspace.anchor):
        raise ValueError("The E2E workspace must be a non-root directory whose name contains e2e")
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def main() -> int:
    args = parse_args()
    workspace = ensure_disposable_workspace(args.workspace)
    database_path = workspace / "moegallery-e2e.db"
    storage_path = workspace / "storage"
    database_url = f"sqlite:///{database_path.as_posix()}"

    os.environ["AGMS_DATABASE_URL"] = database_url
    os.environ["AGMS_STORAGE_PATH"] = str(storage_path)
    os.environ["AGMS_AUTH_SECRET"] = "e2e-auth-secret-with-at-least-thirty-two-characters-20260804"
    os.environ["AGMS_API_KEYS"] = "e2e:agms_e2e_api_key_with_at_least_thirty_two_characters_20260804"

    backend_dir = ROOT_DIR / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from PIL import Image as PillowImage
    from sqlalchemy.orm import sessionmaker

    from app.database import create_database_engine
    from app.models import Character, Image, Work
    from app.services.install_service import initialize_admin, mark_installation_complete, run_migrations

    run_migrations(database_url)
    initialize_admin(database_url, "e2e-admin", "E2E-admin-password-2026")
    mark_installation_complete(database_url)

    original_dir = storage_path / "original"
    thumbnail_dir = storage_path / "thumbnail"
    original_dir.mkdir(parents=True, exist_ok=True)
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    fixture_images = []
    for filename, color in (
        ("e2e-work-only.webp", (91, 153, 219)),
        ("e2e-character.webp", (220, 126, 162)),
    ):
        image_buffer = BytesIO()
        PillowImage.new("RGB", (160, 90), color=color).save(image_buffer, format="WEBP", quality=82)
        image_bytes = image_buffer.getvalue()
        (original_dir / filename).write_bytes(image_bytes)
        (thumbnail_dir / filename).write_bytes(image_bytes)
        fixture_images.append(
            Image(
                filename=filename,
                original_filename=filename,
                file_path=f"original/{filename}",
                thumbnail_path=f"thumbnail/{filename}",
                preview_path=None,
                width=160,
                height=90,
                orientation="landscape",
                file_size=len(image_bytes),
                mime_type="image/webp",
                sha256=hashlib.sha256(image_bytes).hexdigest(),
                rating="safe",
                is_public=True,
            )
        )

    engine = create_database_engine(database_url)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    try:
        with Session() as db:
            db.add_all(fixture_images)
            db.flush()
            work = Work(name="E2E 作品", original_name="E2E Work")
            db.add(work)
            db.flush()
            character = Character(work_id=work.id, name="E2E 角色", original_name="E2E Character")
            db.add(character)
            db.flush()
            fixture_images[0].works.append(work)
            fixture_images[1].works.append(work)
            fixture_images[1].characters.append(character)
            db.commit()
    finally:
        engine.dispose()

    print(
        json.dumps(
            {
                "database_url": database_url,
                "storage_path": str(storage_path),
                "username": "e2e-admin",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
