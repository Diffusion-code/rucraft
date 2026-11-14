#!/usr/bin/env python3
"""Fetch and overlay Pixel Perfection Legacy (CC-BY-4.0) assets onto RuCraft resources."""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import tempfile
import urllib.request
import zipfile

PACK_URL = (
    "https://cdn.modrinth.com/data/6w3F4SEu/versions/UT4foa3M/"
    "Pixel%20Perfection%2026.3-97.2.zip"
)
PACK_SHA512 = (
    "ea6a690ac750c01e836ce28c141faa30b0e7b90e4f6236c5873a32ee6c2bf3f2"
    "90e9cddd5246ff93c3fd01ef42a6f82fb3476fb0dccc5f276e9b67781bcbca86"
)
NOTICE_BLOCK = """
## Pixel Perfection Legacy Assets
- Project: Pixel Perfection Legacy (26.3-97.2)
- Authors: XSSheep, Nova Wostra, and Pixel Perfection Legacy contributors
- License: CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)
- Source: https://modrinth.com/resourcepack/pixel-perfection-legacy
- Usage: Block, item, GUI, entity, environment textures and sounds under resources/assets/minecraft/ (excluding RuCraft's own font and title logo).
""".lstrip("\n")


def download_pack(cache_path: pathlib.Path) -> pathlib.Path:
    if cache_path.is_file():
        if hashlib.sha512(cache_path.read_bytes()).hexdigest() == PACK_SHA512:
            print(f"[RuCraft] Using cached Pixel Perfection zip: {cache_path}", flush=True)
            return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[RuCraft] Downloading Pixel Perfection Legacy from Modrinth...", flush=True)
    req = urllib.request.Request(PACK_URL, headers={"User-Agent": "rucraft-ci/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    digest = hashlib.sha512(data).hexdigest()
    if digest != PACK_SHA512:
        raise RuntimeError(f"SHA-512 mismatch for Pixel Perfection zip: {digest}")
    cache_path.write_bytes(data)
    print(f"[RuCraft] Verified SHA-512 ({len(data)} bytes).", flush=True)
    return cache_path


def extract_assets(zip_path: pathlib.Path, resources_dir: pathlib.Path) -> int:
    extracted = 0
    skip_exact = {
        "textures/gui/title/minecraft.png",
        "textures/gui/title/edition.png",
    }
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not name.startswith("assets/minecraft/"):
                continue
            rel = name[len("assets/minecraft/"):]
            if rel.startswith("textures/font/") or rel in skip_exact:
                continue
            if rel == "sounds.json" or rel.startswith(("textures/", "sounds/", "texts/")):
                out_path = resources_dir / name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(zf.read(info))
                extracted += 1
    return extracted


def append_notice(notices_path: pathlib.Path) -> None:
    if not notices_path.is_file():
        return
    text = notices_path.read_text(encoding="utf-8")
    if "Pixel Perfection Legacy Assets" in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    notices_path.write_text(text + "\n" + NOTICE_BLOCK, encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fetch_pixel_perfection.py <resources_dir>", file=sys.stderr)
        return 1
    resources_dir = pathlib.Path(sys.argv[1]).resolve()
    cache_path = pathlib.Path(os.environ.get("TEMP", tempfile.gettempdir())) / "pp_26_3.zip"
    zip_path = download_pack(cache_path)
    count = extract_assets(zip_path, resources_dir)
    append_notice(resources_dir.parent / "THIRD_PARTY_NOTICES.md")
    print(f"[RuCraft] Extracted {count} Pixel Perfection assets into {resources_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
