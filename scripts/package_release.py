import argparse
import hashlib
import shutil
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "MoeGallery"


def _ignore_backend(path: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo", ".db", ".db-journal")))
    ignored.update(name for name in names if name.startswith("anime_gallery.db"))
    return ignored


def _copytree(src: Path, dst: Path, ignore=None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _write_release_notes(stage_root: Path, version: str) -> None:
    (stage_root / "RELEASE_NOTES.md").write_text(
        "\n".join(
            [
                f"# {PACKAGE_NAME} {version}",
                "",
                "This package contains a deployable MoeGallery build.",
                "",
                "Included:",
                "",
                "- backend FastAPI source, Alembic migrations, and Python requirements",
                "- prebuilt frontend assets in `frontend/dist`",
                "- deployment scripts, Nginx/systemd examples, documentation, and license",
                "- empty `storage/` and `logs/` directories for deployment layout",
                "",
                "Not included:",
                "",
                "- `.env`, `installed.lock`, database files, uploaded images, logs, virtualenvs, node_modules, or private keys",
                "",
                "Typical deployment:",
                "",
                "```bash",
                "sudo mkdir -p /opt/anime-gallery",
                "sudo tar -xzf MoeGallery-<version>.tar.gz -C /opt/anime-gallery --strip-components=1",
                "cd /opt/anime-gallery",
                "sudo python3 -m venv venv",
                "sudo ./venv/bin/pip install -r backend/requirements.txt",
                "sudo cp .env.example .env",
                "# edit .env, run migrations, and enable the systemd/Nginx examples",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _stage(version: str, output_dir: Path) -> Path:
    frontend_dist = ROOT / "frontend" / "dist"
    if not frontend_dist.exists():
        raise SystemExit("frontend/dist does not exist. Run `npm run build` in frontend first.")

    stage_parent = output_dir / "_stage"
    if stage_parent.exists():
        shutil.rmtree(stage_parent)
    stage_root = stage_parent / f"{PACKAGE_NAME}-{version}"
    stage_root.mkdir(parents=True)

    _copytree(ROOT / "backend", stage_root / "backend", ignore=_ignore_backend)
    _copytree(frontend_dist, stage_root / "frontend" / "dist")
    _copytree(ROOT / "scripts", stage_root / "scripts")
    if (ROOT / "docs").exists():
        _copytree(ROOT / "docs", stage_root / "docs")

    for filename in [
        ".env.example",
        "LICENSE",
        "README.md",
        "README_zh.md",
        "README_zh-TW.md",
        "README_ja.md",
    ]:
        src = ROOT / filename
        if src.exists():
            _copy_file(src, stage_root / filename)

    for directory in [
        "storage/original",
        "storage/preview",
        "storage/thumbnail",
        "storage/tasks",
        "logs",
    ]:
        (stage_root / directory).mkdir(parents=True, exist_ok=True)

    (stage_root / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    _write_release_notes(stage_root, version)
    return stage_root


def _make_zip(stage_root: Path, output_dir: Path, version: str) -> Path:
    archive_path = output_dir / f"{PACKAGE_NAME}-{version}.zip"
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(stage_root.rglob("*")):
            archive.write(path, path.relative_to(stage_root.parent).as_posix())
    return archive_path


def _make_tar(stage_root: Path, output_dir: Path, version: str) -> Path:
    archive_path = output_dir / f"{PACKAGE_NAME}-{version}.tar.gz"
    if archive_path.exists():
        archive_path.unlink()
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(stage_root, arcname=stage_root.name)
    return archive_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MoeGallery release archives.")
    parser.add_argument("--version", required=True, help="Release version, for example v0.1.0")
    parser.add_argument("--output-dir", default="dist-release", help="Archive output directory")
    args = parser.parse_args()

    version = args.version.strip()
    if not version:
        raise SystemExit("version is required")

    output_dir = (ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stage_root = _stage(version, output_dir)
    artifacts = [
        _make_zip(stage_root, output_dir, version),
        _make_tar(stage_root, output_dir, version),
    ]
    sums_path = output_dir / "SHA256SUMS.txt"
    sums_path.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )

    print(f"Built release artifacts in {output_dir}")
    for path in artifacts + [sums_path]:
        print(path)


if __name__ == "__main__":
    main()
