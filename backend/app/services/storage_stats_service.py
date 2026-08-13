import os
import time
from pathlib import Path
from threading import Lock


STORAGE_STATS_CACHE_SECONDS = 30
_cache_lock = Lock()
_directory_cache: dict[str, dict[str, object]] = {}


def _scan_directory(path: Path) -> dict[str, object]:
    exists = path.exists()
    count = 0
    size = 0
    if exists:
        pending = [path]
        while pending:
            directory = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                pending.append(Path(entry.path))
                            elif entry.is_file(follow_symlinks=False):
                                count += 1
                                size += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            continue
            except OSError:
                continue
    return {"path": str(path), "exists": exists, "file_count": count, "size_bytes": size}


def directory_stats(path: Path, *, force_refresh: bool = False) -> dict[str, object]:
    key = str(path.absolute())
    now = time.monotonic()
    with _cache_lock:
        cached = _directory_cache.get(key)
        if (
            cached
            and not force_refresh
            and now - float(cached["checked_at"]) < STORAGE_STATS_CACHE_SECONDS
        ):
            return dict(cached["data"])
        data = _scan_directory(path)
        _directory_cache[key] = {"checked_at": now, "data": data}
        return dict(data)


def media_storage_stats(storage_path: Path, *, force_refresh: bool = False) -> dict[str, dict[str, object]]:
    return {
        name: directory_stats(storage_path / name, force_refresh=force_refresh)
        for name in ("original", "preview", "thumbnail")
    }


def invalidate_storage_stats_cache(storage_path: Path | None = None) -> None:
    with _cache_lock:
        if storage_path is None:
            _directory_cache.clear()
            return
        prefix = str(storage_path.absolute())
        for key in [key for key in _directory_cache if key == prefix or key.startswith(prefix + os.sep)]:
            _directory_cache.pop(key, None)
