#!/usr/bin/env python3
"""Build and verify a deterministic runtime-only release archive."""

from __future__ import annotations

import argparse
import stat
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ADDON_ID = "plugin.video.plexkodiconnect.tvshows"
RUNTIME_FILES = ("addon.xml", "changelog.txt", "default.py", "icon.png")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def read_identity(addon_xml: bytes) -> tuple[str, str]:
    root = ElementTree.fromstring(addon_xml)
    addon_id = root.get("id", "")
    version = root.get("version", "")
    if addon_id != ADDON_ID:
        raise ValueError(f"add-on ID must be {ADDON_ID}, got {addon_id!r}")
    if not version:
        raise ValueError("add-on version is missing")
    return addon_id, version


def collect(source: Path, expected_version: str | None) -> list[tuple[str, bytes]]:
    members = []
    for name in RUNTIME_FILES:
        path = source / name
        if path.is_symlink():
            raise ValueError(f"symlinked runtime file is not allowed: {name}")
        if not path.is_file():
            raise ValueError(f"required runtime file is missing or not regular: {name}")
        members.append((f"{ADDON_ID}/{name}", path.read_bytes()))
    _, version = read_identity(dict(members)[f"{ADDON_ID}/addon.xml"])
    if expected_version is not None and version != expected_version:
        raise ValueError(f"add-on version {version!r} does not match {expected_version!r}")
    return sorted(members)


def verify(output: Path, expected_version: str | None = None) -> list[str]:
    expected = {f"{ADDON_ID}/{name}" for name in RUNTIME_FILES}
    with zipfile.ZipFile(output) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or len({name.casefold() for name in names}) != len(names):
            raise ValueError("archive contains duplicate or case-colliding members")
        if set(names) != expected:
            raise ValueError(f"archive members differ from runtime allowlist: {sorted(names)}")
        for info in infos:
            if info.is_dir() or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError(f"archive member is not a regular file: {info.filename}")
            if info.date_time != FIXED_TIME:
                raise ValueError(f"archive member timestamp is not deterministic: {info.filename}")
        _, version = read_identity(archive.read(f"{ADDON_ID}/addon.xml"))
    if expected_version is not None and version != expected_version:
        raise ValueError(f"archive version {version!r} does not match {expected_version!r}")
    return sorted(names)


def build(source: Path, output: Path, expected_version: str | None = None) -> list[str]:
    members = collect(source, expected_version)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in members:
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)
    return verify(output, expected_version)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-version")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        names = verify(args.output, args.expected_version) if args.verify_only else build(args.source, args.output, args.expected_version)
    except (OSError, ValueError, ElementTree.ParseError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("\n".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
