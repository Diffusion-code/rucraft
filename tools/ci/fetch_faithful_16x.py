#!/usr/bin/env python3
"""Fetch Faithful 32x (26.3), downscale 2x to crisp 16x16, and apply Faithful License attribution."""

from __future__ import annotations

import hashlib
import io
import os
import pathlib
import sys
import tempfile
import urllib.request
import zipfile
from PIL import Image

PACK_URL = (
    "https://cdn.modrinth.com/data/w0TnApzs/versions/lDYpMiqk/"
    "Faithful%2032x%20-%2026.3.zip"
)
PACK_SHA256 = "596035002e8c369ca673b5b922cd532a38a2aaabe80f317f5ac4d5c7680c7bf2"

NOTICE_BLOCK = """
## Faithful 32x (Modified / Downscaled 2x to 16x)
- Project: Faithful 32x (26.3-september-2026)
- Website: https://faithfulpack.net
- License: Faithful License v4 (https://faithfulpack.net/license, full text included in FAITHFUL-LICENSE.txt)
- Modifications: Block, item, GUI, entity, and environment PNG textures under resources/assets/minecraft/textures/ were programmatically downscaled 2x (from 32x32 to 16x16) for RuCraft, excluding RuCraft's own font and title logo.
""".lstrip("\n")


def download_pack(cache_path: pathlib.Path) -> pathlib.Path:
    if cache_path.is_file():
        if hashlib.sha256(cache_path.read_bytes()).hexdigest() == PACK_SHA256:
            print(f"[RuCraft] Using cached Faithful 32x zip: {cache_path}", flush=True)
            return cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    print("[RuCraft] Downloading Faithful 32x (26.3) from Modrinth...", flush=True)
    req = urllib.request.Request(PACK_URL, headers={"User-Agent": "rucraft-ci/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != PACK_SHA256:
        raise RuntimeError(f"SHA-256 mismatch for Faithful 32x zip: {digest}")
    cache_path.write_bytes(data)
    print(f"[RuCraft] Verified Faithful SHA-256 ({len(data)} bytes).", flush=True)
    return cache_path


def downscale_2x_crisp(raw_png: bytes, rel_path: str) -> bytes:
    if "gui/title/background/panorama_" in rel_path:
        return raw_png
    with Image.open(io.BytesIO(raw_png)) as im:
        w, h = im.size
        if w < 32 or h < 32 or w % 2 != 0 or h % 2 != 0:
            return raw_png
        rgba = im.convert("RGBA")
        px = rgba.tobytes()
        nw, nh = w // 2, h // 2
        has_translucent = any(0 < px[i + 3] < 255 for i in range(0, len(px), 4))
        if has_translucent:
            out_img = rgba.resize((nw, nh), Image.Resampling.BOX)
        else:
            out = bytearray(nw * nh * 4)
            stride = w * 4
            for y in range(nh):
                r0 = (y * 2) * stride
                r1 = r0 + stride
                for x in range(nw):
                    c0 = x * 8
                    p0 = r0 + c0
                    p1 = p0 + 4
                    p2 = r1 + c0
                    p3 = p2 + 4
                    sr = sg = sb = cnt = 0
                    for p in (p0, p1, p2, p3):
                        if px[p + 3] >= 128:
                            sr += px[p]
                            sg += px[p + 1]
                            sb += px[p + 2]
                            cnt += 1
                    di = (y * nw + x) * 4
                    if cnt >= 2:
                        out[di] = sr // cnt
                        out[di + 1] = sg // cnt
                        out[di + 2] = sb // cnt
                        out[di + 3] = 255
            out_img = Image.frombytes("RGBA", (nw, nh), bytes(out))
        buf = io.BytesIO()
        out_img.save(buf, format="PNG", optimize=False)
        return buf.getvalue()


def extract_and_downscale(zip_path: pathlib.Path, resources_dir: pathlib.Path) -> tuple[int, int]:
    extracted = 0
    downscaled = 0
    skip_exact = {
        "textures/gui/title/minecraft.png",
        "textures/gui/title/edition.png",
    }
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name == "LICENSE.txt":
                (resources_dir.parent / "FAITHFUL-LICENSE.txt").write_bytes(zf.read(info))
                continue
            if not name.startswith("assets/minecraft/"):
                continue
            rel = name[len("assets/minecraft/"):]
            if rel.startswith("textures/font/") or rel in skip_exact:
                continue
            if rel.startswith(("textures/", "texts/")):
                data = zf.read(info)
                if rel.startswith("textures/") and rel.endswith(".png"):
                    new_data = downscale_2x_crisp(data, rel)
                    if len(new_data) != len(data):
                        downscaled += 1
                    data = new_data
                out_path = resources_dir / name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(data)
                extracted += 1
    return extracted, downscaled


def append_notice(notices_path: pathlib.Path) -> None:
    if not notices_path.is_file():
        return
    text = notices_path.read_text(encoding="utf-8")
    if "Faithful 32x (Modified / Downscaled 2x to 16x)" in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    notices_path.write_text(text + "\n" + NOTICE_BLOCK, encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: fetch_faithful_16x.py <resources_dir>", file=sys.stderr)
        return 1
    resources_dir = pathlib.Path(sys.argv[1]).resolve()
    cache_path = pathlib.Path(os.environ.get("TEMP", tempfile.gettempdir())) / "faithful_26_3.zip"
    zip_path = download_pack(cache_path)
    extracted, downscaled = extract_and_downscale(zip_path, resources_dir)
    append_notice(resources_dir.parent / "THIRD_PARTY_NOTICES.md")
    print(
        f"[RuCraft] Extracted {extracted} Faithful assets ({downscaled} downscaled 2x to 16x) into {resources_dir}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
