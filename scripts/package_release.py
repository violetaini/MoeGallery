import argparse
import hashlib
import shutil
import subprocess
import tarfile
import zipfile
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "MoeGallery"


@lru_cache(maxsize=1)
def _tracked_repository_files() -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Release packaging requires a Git checkout so local-only files can be excluded.") from exc
    return {
        item.decode("utf-8").replace("\\", "/")
        for item in result.stdout.split(b"\0")
        if item
    }


def _ignore_untracked(path: str, names: list[str]) -> set[str]:
    directory = Path(path)
    if not directory.is_absolute():
        directory = ROOT / directory
    try:
        relative_directory = directory.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return set(names)

    tracked = _tracked_repository_files()
    ignored: set[str] = set()
    for name in names:
        relative_path = f"{relative_directory}/{name}" if relative_directory != "." else name
        if relative_path in tracked:
            continue
        prefix = f"{relative_path}/"
        if not any(item.startswith(prefix) for item in tracked):
            ignored.add(name)
    return ignored


def _ignore_backend(path: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    database_suffixes = (".db", ".sqlite", ".sqlite3")
    database_sidecars = tuple(f"{suffix}-{kind}" for suffix in database_suffixes for kind in ("journal", "wal", "shm"))
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo", *database_suffixes, *database_sidecars)))
    ignored.update(name for name in names if name.startswith("anime_gallery.db"))
    ignored.update(_ignore_untracked(path, names))
    return ignored


def _ignore_runtime_cache(path: str, names: list[str]) -> set[str]:
    ignored = {"__pycache__", ".pytest_cache"}
    ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
    ignored.update(_ignore_untracked(path, names))
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
                "- backend FastAPI source, Alembic migrations, and hash-locked Python requirements",
                "- prebuilt frontend assets in `frontend/dist`",
                "- one-command installer, built-in update launcher, backup tools, documentation, and license",
                "- empty `storage/` and `logs/` directories for deployment layout",
                "",
                "Not included:",
                "",
                "- `.env`, `installed.lock`, database files, uploaded images, logs, virtualenvs, node_modules, or private keys",
                "",
                "Recommended deployment:",
                "",
                "```bash",
                "curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh",
                "sudo bash install.sh",
                "```",
                "",
                "For a clean deployment, configure SQLite/MySQL, the admin account, and the session secret in the web installer.",
                "The installer only configures a local or public listen address and does not manage domains, TLS, firewalls, or reverse proxies.",
                "Panel updates are coordinated by the built-in launcher; no separate updater service or sudoers rule is required.",
                "Manual `.env` editing is only needed when bypassing the installer or upgrading an existing deployment.",
                "",
                "Upgrade an existing deployment:",
                "",
                "```bash",
                "sudo bash /opt/moegallery/scripts/upgrade_release.sh /tmp/MoeGallery-<version>.tar.gz",
                "```",
                "",
                "The upgrade script creates a pre-upgrade backup by default, stops the service, replaces application files,",
                "installs Python dependencies, runs Alembic migrations, restarts the service, and checks `/api/health`.",
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
    for filename in ("requirements.lock.txt", "requirements-test.lock.txt"):
        source = ROOT / "backend" / filename
        if not source.is_file():
            raise SystemExit(f"Missing dependency lock: backend/{filename}")
        _copy_file(source, stage_root / "backend" / filename)
    _copytree(frontend_dist, stage_root / "frontend" / "dist")
    _copytree(ROOT / "scripts", stage_root / "scripts", ignore=_ignore_runtime_cache)
    if (ROOT / "docs").exists():
        _copytree(ROOT / "docs", stage_root / "docs")

    for filename in [
        "install.sh",
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
        "storage/updates",
        "storage/runtime",
        "logs",
        "backups",
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
