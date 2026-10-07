"""Offline integrity checks and recoverable per-user data maintenance."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import __version__
from .models import Project, atomic_text, read_text_limited, strict_json

DATA_FILES = {"catalog.sqlite", "settings.ini", "recovery.gearforge"}


def lock_data_directory(directory: Path):
    from PySide6.QtCore import QLockFile
    lock = QLockFile(str(Path(directory) / ".gearforge.lock"))
    lock.setStaleLockTime(0)  # Never expire a live long-running CAD session.
    if not lock.tryLock(0):
        raise RuntimeError("GearForge data is already in use or cannot be locked. "
                           "Close the other session and check directory permissions.")
    return lock


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def bundle_files(directory: Path) -> dict[str, str]:
    result = {}
    for parent, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            if linked(Path(parent) / name):
                raise ValueError("Linked files or directories are not allowed in a bundle")
        for name in names:
            path = Path(parent) / name
            key = path.relative_to(directory).as_posix()
            if key != "manifest.json":
                result[key] = digest(path)
    return dict(sorted(result.items()))


def write_manifest(directory: Path, **metadata):
    manifest = dict(schema_version=1, app_version=__version__,
                    created_utc=datetime.now(timezone.utc).isoformat(), **metadata)
    manifest["files"] = bundle_files(directory)
    atomic_text(directory / "manifest.json", json.dumps(manifest, indent=2, allow_nan=False))
    return manifest


def verify_bundle(directory: Path) -> dict:
    directory = Path(directory)
    if linked(directory) or linked(directory / "manifest.json"):
        raise ValueError("Linked bundle paths are not allowed")
    manifest = strict_json(read_text_limited(directory / "manifest.json", 2_000_000, "Manifest"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
        raise ValueError("Invalid or empty bundle manifest")
    if "schema_version" in manifest and (type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1):
        raise ValueError("Unsupported manifest schema")
    for name, checksum in manifest["files"].items():
        parts = PurePosixPath(name).parts
        if (not parts or PurePosixPath(name).is_absolute() or ".." in parts
                or "\\" in name or ":" in name or name != PurePosixPath(name).as_posix()
                or name == "manifest.json" or not isinstance(checksum, str)
                or not re.fullmatch("[0-9a-f]{64}", checksum)):
            raise ValueError("Invalid manifest file entry")
    actual = bundle_files(directory)
    missing = sorted(set(manifest["files"]) - set(actual))
    extra = sorted(set(actual) - set(manifest["files"]))
    changed = sorted(key for key in actual.keys() & manifest["files"].keys()
                     if actual[key] != manifest["files"][key])
    if missing or extra or changed:
        raise ValueError(f"Bundle integrity failed: missing={missing}, unexpected={extra}, changed={changed}")
    return manifest


def _new_destination(path: Path):
    path = Path(path).absolute()
    if path.exists() or path.is_symlink():
        raise FileExistsError("Choose a new destination; existing data will not be overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _check_database(path: Path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Catalog database integrity check failed")
        if connection.execute("SELECT value FROM metadata WHERE key='schema'").fetchone() != ("1",):
            raise ValueError("Unsupported catalog database schema")
    finally:
        connection.close()


def backup_data(data_dir: Path, destination: Path) -> dict:
    data_dir = Path(data_dir).resolve()
    if not (data_dir / "catalog.sqlite").is_file():
        raise ValueError("Data directory does not contain a GearForge catalog")
    dest = _new_destination(destination)
    if dest.is_relative_to(data_dir):
        raise ValueError("Store backups outside the application data directory")
    lock = lock_data_directory(data_dir)
    try:
        with tempfile.TemporaryDirectory(prefix=".gearforge-backup-", dir=dest.parent) as temporary:
            stage = Path(temporary) / "data"
            stage.mkdir()
            for name in sorted(DATA_FILES):
                source = data_dir / name
                if linked(source):
                    raise ValueError("Linked application data cannot be backed up")
                if not source.is_file():
                    continue
                if name == "catalog.sqlite":
                    # Include committed WAL transactions using SQLite's backup API.
                    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
                    target = sqlite3.connect(stage / name)
                    try:
                        src.backup(target)
                        target.execute("PRAGMA journal_mode=DELETE")
                    finally:
                        target.close(); src.close()
                    _check_database(stage / name)
                else:
                    shutil.copy2(source, stage / name)
            manifest = write_manifest(stage, kind="gearforge-data-backup")
            if dest.exists():
                raise FileExistsError("Backup destination already exists")
            stage.rename(dest)
        return {"destination": str(dest), "files": len(manifest["files"])}
    finally:
        lock.unlock()


def restore_data(backup: Path, destination: Path) -> dict:
    backup = Path(backup)
    manifest = verify_bundle(backup)
    if (manifest.get("kind") != "gearforge-data-backup"
            or set(manifest["files"]) - DATA_FILES or "catalog.sqlite" not in manifest["files"]):
        raise ValueError("Not a supported GearForge data backup")
    dest = _new_destination(destination)
    with tempfile.TemporaryDirectory(prefix=".gearforge-restore-", dir=dest.parent) as temporary:
        stage = Path(temporary) / "data"
        stage.mkdir()
        for name, checksum in manifest["files"].items():
            shutil.copy2(backup / name, stage / name)
            if digest(stage / name) != checksum:
                raise ValueError("Backup changed during restore")
        _check_database(stage / "catalog.sqlite")
        if (stage / "recovery.gearforge").exists():
            Project.load(stage / "recovery.gearforge")
        if dest.exists():
            raise FileExistsError("Restore destination already exists")
        stage.rename(dest)
    return {"destination": str(dest), "files": len(manifest["files"])}
