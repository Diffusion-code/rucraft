#!/usr/bin/env python3
"""
Generate a standalone, Mojang-independent procedural resource bundle for RuCraft.

Uses only the Python 3 standard library to synthesize 16x16 pixel-art textures,
colormaps, panorama faces, JSON registries/models/recipes, and uncompressed NBT
collision/occlusion/movement tables compatible with the Horizon/RuCraft engine.
"""

from __future__ import annotations

import itertools
import json
import math
import pathlib
import random
import struct
import sys
import zlib
from typing import Any


DATA_VERSION = 5023
SCHEMA_VERSION = 7
OUTPUT_VERSION = 4


# ---------------------------------------------------------------------------
# Minimal PNG writer (RGBA 8-bit)
# ---------------------------------------------------------------------------

def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    body = tag + payload
    crc = zlib.crc32(body) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", crc)


def encode_png(width: int, height: int, pixels: bytes) -> bytes:
    """Encode width*height*4 RGBA bytes into a valid PNG."""
    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start : start + stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), level=6))
        + _png_chunk(b"IEND", b"")
    )


def clamp_u8(v: float) -> int:
    return max(0, min(255, int(round(v))))


def make_grid(w: int, h: int, color: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    return [color] * (w * h)


def write_png(path: pathlib.Path, w: int, h: int, grid: list[tuple[int, int, int, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = bytearray(w * h * 4)
    for i, (r, g, b, a) in enumerate(grid):
        off = i * 4
        buf[off] = r
        buf[off + 1] = g
        buf[off + 2] = b
        buf[off + 3] = a
    path.write_bytes(encode_png(w, h, bytes(buf)))


# ---------------------------------------------------------------------------
# Procedural 16x16 texture generators
# ---------------------------------------------------------------------------

def _noise_tex(seed: int, base: tuple[int, int, int], spread: int, a: int = 255) -> list[tuple[int, int, int, int]]:
    rng = random.Random(seed)
    out = []
    for _ in range(256):
        d = rng.randint(-spread, spread)
        out.append((clamp_u8(base[0] + d), clamp_u8(base[1] + d), clamp_u8(base[2] + d), a))
    return out


def gen_bedrock() -> list[tuple[int, int, int, int]]:
    rng = random.Random(101)
    out = []
    for y in range(16):
        for x in range(16):
            v = 48 if (x + y * 3) % 5 == 0 else 72
            v += rng.randint(-26, 22)
            c = clamp_u8(v)
            out.append((c, c, c, 255))
    return out


def gen_stone(ore: tuple[int, int, int] | None = None, seed: int = 202) -> list[tuple[int, int, int, int]]:
    rng = random.Random(seed)
    grid = []
    for y in range(16):
        for x in range(16):
            band = 4 if ((x + y) % 7 == 0) else 0
            v = 128 + band + rng.randint(-12, 12)
            c = clamp_u8(v)
            grid.append((c, c, clamp_u8(v + 3), 255))
    if ore is not None:
        spots = [(3, 3), (4, 3), (10, 4), (11, 5), (6, 9), (7, 9), (7, 10), (12, 11), (4, 13), (5, 13)]
        for x, y in spots:
            grid[y * 16 + x] = (ore[0], ore[1], ore[2], 255)
            if x + 1 < 16:
                grid[y * 16 + x + 1] = (clamp_u8(ore[0] * 0.8), clamp_u8(ore[1] * 0.8), clamp_u8(ore[2] * 0.8), 255)
    return grid


def gen_cobblestone() -> list[tuple[int, int, int, int]]:
    rng = random.Random(303)
    grid = []
    for y in range(16):
        for x in range(16):
            mortar = (y % 4 == 0) or ((x + (y // 4) * 3) % 5 == 0)
            base = 84 if mortar else 128 + ((x // 5 + y // 4) % 3) * 10
            d = rng.randint(-10, 10)
            c = clamp_u8(base + d)
            grid.append((c, c, c, 255))
    return grid


def gen_dirt() -> list[tuple[int, int, int, int]]:
    rng = random.Random(404)
    grid = []
    for _ in range(256):
        d = rng.randint(-14, 14)
        speck = 18 if rng.random() < 0.08 else 0
        grid.append((clamp_u8(134 + d + speck), clamp_u8(94 + d + speck), clamp_u8(65 + d), 255))
    return grid


def gen_grass_top() -> list[tuple[int, int, int, int]]:
    rng = random.Random(505)
    grid = []
    for _ in range(256):
        d = rng.randint(-14, 14)
        grid.append((clamp_u8(102 + d), clamp_u8(168 + d), clamp_u8(74 + d), 255))
    return grid


def gen_grass_side(snowy: bool = False) -> list[tuple[int, int, int, int]]:
    dirt = gen_dirt()
    top_col = (238, 244, 248, 255) if snowy else (96, 162, 68, 255)
    rng = random.Random(506 if not snowy else 507)
    for y in range(16):
        for x in range(16):
            overhang = 3 + ((x * 5 + 2) % 3)
            if y < overhang:
                d = rng.randint(-10, 10)
                dirt[y * 16 + x] = (
                    clamp_u8(top_col[0] + d),
                    clamp_u8(top_col[1] + d),
                    clamp_u8(top_col[2] + d),
                    255,
                )
    return dirt


def gen_planks() -> list[tuple[int, int, int, int]]:
    rng = random.Random(606)
    grid = []
    for y in range(16):
        for x in range(16):
            seam = (y % 4 == 0) or (x == 0 and (y // 4) % 2 == 0) or (x == 8 and (y // 4) % 2 == 1)
            d = rng.randint(-8, 8)
            if seam:
                grid.append((118, 86, 52, 255))
            else:
                grid.append((clamp_u8(178 + d), clamp_u8(139 + d), clamp_u8(90 + d), 255))
    return grid


def gen_log_side() -> list[tuple[int, int, int, int]]:
    rng = random.Random(707)
    grid = []
    for y in range(16):
        for x in range(16):
            ridge = -16 if (x % 3 == 0 and (y + x) % 5 != 0) else 8
            d = rng.randint(-6, 6) + ridge
            grid.append((clamp_u8(108 + d), clamp_u8(82 + d), clamp_u8(54 + d), 255))
    return grid


def gen_log_top() -> list[tuple[int, int, int, int]]:
    grid = []
    for y in range(16):
        for x in range(16):
            dx = abs(x - 7.5)
            dy = abs(y - 7.5)
            dist = max(dx, dy)
            if dist >= 6.5:
                grid.append((96, 72, 48, 255))
            elif int(dist) % 2 == 0:
                grid.append((182, 145, 96, 255))
            else:
                grid.append((154, 118, 76, 255))
    return grid


def gen_leaves() -> list[tuple[int, int, int, int]]:
    rng = random.Random(808)
    grid = []
    for y in range(16):
        for x in range(16):
            if ((x * 7 + y * 13) % 9 == 0) or rng.random() < 0.18:
                grid.append((0, 0, 0, 0))
            else:
                d = rng.randint(-18, 18)
                grid.append((clamp_u8(74 + d), clamp_u8(140 + d), clamp_u8(54 + d), 255))
    return grid


def gen_bricks() -> list[tuple[int, int, int, int]]:
    rng = random.Random(909)
    grid = []
    for y in range(16):
        for x in range(16):
            row = y // 4
            mortar = (y % 4 == 3) or ((x + row * 4) % 8 == 7)
            if mortar:
                grid.append((196, 192, 184, 255))
            else:
                d = rng.randint(-10, 10)
                grid.append((clamp_u8(162 + d), clamp_u8(76 + d), clamp_u8(60 + d), 255))
    return grid


def gen_glass() -> list[tuple[int, int, int, int]]:
    grid = []
    for y in range(16):
        for x in range(16):
            edge = x in (0, 15) or y in (0, 15)
            gleam = (x - y) in (3, 4) and 2 <= x <= 11
            if edge:
                grid.append((195, 228, 240, 255))
            elif gleam:
                grid.append((230, 248, 255, 175))
            else:
                grid.append((190, 232, 248, 65))
    return grid


def gen_short_grass() -> list[tuple[int, int, int, int]]:
    grid = make_grid(16, 16, (0, 0, 0, 0))
    blades = [
        (3, 5, 16), (5, 7, 16), (8, 4, 16), (10, 6, 16), (12, 8, 16),
    ]
    for bx, top, bottom in blades:
        for y in range(top, bottom):
            shade = 20 if y < top + 3 else 0
            grid[y * 16 + bx] = (72 + shade, 156 + shade, 54, 255)
            if y > top + 2 and bx + 1 < 16:
                grid[y * 16 + bx + 1] = (62, 138, 46, 255)
    return grid


def gen_torch() -> list[tuple[int, int, int, int]]:
    grid = make_grid(16, 16, (0, 0, 0, 0))
    for y in range(8, 16):
        for x in (7, 8):
            grid[y * 16 + x] = (142, 102, 58, 255)
    for y in range(6, 8):
        for x in (7, 8):
            grid[y * 16 + x] = (255, 198, 68, 255)
    grid[5 * 16 + 7] = (255, 242, 148, 255)
    grid[5 * 16 + 8] = (255, 140, 32, 255)
    return grid


def gen_fluid(base: tuple[int, int, int], alpha: int, seed: int) -> list[tuple[int, int, int, int]]:
    rng = random.Random(seed)
    grid = []
    for y in range(16):
        for x in range(16):
            wave = int(12 * math.sin((x + y * 0.6) * math.pi / 4.0))
            d = rng.randint(-8, 8) + wave
            grid.append((clamp_u8(base[0] + d), clamp_u8(base[1] + d), clamp_u8(base[2] + d), alpha))
    return grid


def gen_crafting_top() -> list[tuple[int, int, int, int]]:
    grid = gen_planks()
    for y in range(2, 14):
        for x in range(2, 14):
            border = x in (2, 13) or y in (2, 13) or x in (6, 9) or y in (6, 9)
            if border:
                grid[y * 16 + x] = (92, 62, 38, 255)
            else:
                grid[y * 16 + x] = (196, 158, 108, 255)
    return grid


def gen_furnace_front(lit: bool) -> list[tuple[int, int, int, int]]:
    grid = gen_cobblestone()
    for y in range(9, 14):
        for x in range(4, 12):
            if y in (9, 13) or x in (4, 11):
                grid[y * 16 + x] = (64, 64, 68, 255)
            elif lit:
                grid[y * 16 + x] = (255, 168 if y < 12 else 110, 40, 255)
            else:
                grid[y * 16 + x] = (32, 32, 36, 255)
    return grid


def gen_item_tool(head: tuple[int, int, int]) -> list[tuple[int, int, int, int]]:
    grid = make_grid(16, 16, (0, 0, 0, 0))
    for i in range(4, 13):
        grid[(15 - i) * 16 + i] = (132, 94, 52, 255)
    for x, y in [(9, 2), (10, 2), (11, 2), (12, 3), (13, 4), (13, 5), (13, 6), (8, 3), (12, 7)]:
        grid[y * 16 + x] = (head[0], head[1], head[2], 255)
    return grid


def gen_item_oval(main: tuple[int, int, int], stem: tuple[int, int, int] | None = None) -> list[tuple[int, int, int, int]]:
    grid = make_grid(16, 16, (0, 0, 0, 0))
    for y in range(5, 14):
        for x in range(4, 12):
            dx = (x - 7.5) / 3.8
            dy = (y - 9.0) / 4.2
            if dx * dx + dy * dy <= 1.0:
                hi = 25 if (x < 7 and y < 8) else 0
                grid[y * 16 + x] = (clamp_u8(main[0] + hi), clamp_u8(main[1] + hi), clamp_u8(main[2] + hi), 255)
    if stem is not None:
        grid[3 * 16 + 7] = (*stem, 255)
        grid[4 * 16 + 7] = (*stem, 255)
    return grid


def gen_destroy_stage(stage: int) -> list[tuple[int, int, int, int]]:
    grid = make_grid(16, 16, (0, 0, 0, 0))
    rng = random.Random(1000 + stage)
    count = (stage + 1) * 18
    for _ in range(count):
        x = rng.randint(1, 14)
        y = rng.randint(1, 14)
        grid[y * 16 + x] = (24, 24, 24, 195)
    return grid


def gen_colormap(r_fn, g_fn, b_fn) -> list[tuple[int, int, int, int]]:
    grid = []
    for y in range(256):
        for x in range(256):
            grid.append((clamp_u8(r_fn(x, y)), clamp_u8(g_fn(x, y)), clamp_u8(b_fn(x, y)), 255))
    return grid


def gen_panorama_face(face: int, size: int = 64) -> list[tuple[int, int, int, int]]:
    grid = []
    for y in range(size):
        t = y / max(1, size - 1)
        for x in range(size):
            if face == 4:
                r, g, b = 78, 138, 224
            elif face == 5:
                r, g, b = 52, 84, 58
            else:
                horizon = math.exp(-((t - 0.56) * 5.0) ** 2)
                hill = 0.56 + 0.06 * math.sin((x + face * 17) * 0.22)
                if t > hill:
                    r, g, b = 64, 118, 66
                else:
                    r = 88 + 90 * horizon
                    g = 152 + 65 * horizon
                    b = 232 + 18 * horizon
            grid.append((clamp_u8(r), clamp_u8(g), clamp_u8(b), 255))
    return grid


# ---------------------------------------------------------------------------
# Uncompressed big-endian NBT encoder
# ---------------------------------------------------------------------------

TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


def _nbt_str(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack(">H", len(raw)) + raw


def nbt_payload(val: tuple[int, Any]) -> bytes:
    tag_type, data = val
    if tag_type == TAG_BYTE:
        return struct.pack(">b", int(data))
    if tag_type == TAG_SHORT:
        return struct.pack(">h", int(data))
    if tag_type == TAG_INT:
        return struct.pack(">i", int(data))
    if tag_type == TAG_LONG:
        return struct.pack(">q", int(data))
    if tag_type == TAG_FLOAT:
        return struct.pack(">f", float(data))
    if tag_type == TAG_DOUBLE:
        return struct.pack(">d", float(data))
    if tag_type == TAG_BYTE_ARRAY:
        arr = bytes(int(x) & 0xFF for x in data)
        return struct.pack(">i", len(arr)) + arr
    if tag_type == TAG_STRING:
        return _nbt_str(str(data))
    if tag_type == TAG_LIST:
        elem_type, items = data
        out = bytearray(struct.pack(">Bi", elem_type, len(items)))
        for item in items:
            out.extend(nbt_payload((elem_type, item)))
        return bytes(out)
    if tag_type == TAG_COMPOUND:
        out = bytearray()
        for k, v in data.items():
            out.append(v[0])
            out.extend(_nbt_str(k))
            out.extend(nbt_payload(v))
        out.append(TAG_END)
        return bytes(out)
    if tag_type == TAG_INT_ARRAY:
        out = bytearray(struct.pack(">i", len(data)))
        for x in data:
            out.extend(struct.pack(">i", int(x)))
        return bytes(out)
    if tag_type == TAG_LONG_ARRAY:
        out = bytearray(struct.pack(">i", len(data)))
        for x in data:
            out.extend(struct.pack(">q", int(x)))
        return bytes(out)
    raise ValueError(f"unsupported NBT tag type {tag_type}")


def write_nbt_root(path: pathlib.Path, fields: dict[str, tuple[int, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = bytes([TAG_COMPOUND]) + _nbt_str("") + nbt_payload((TAG_COMPOUND, fields))
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# Block & Item definitions
# ---------------------------------------------------------------------------

def f64_hex(v: float) -> str:
    return f"{struct.unpack('>Q', struct.pack('>d', v))[0]:016x}"


def f32_hex(v: float) -> str:
    return f"{struct.unpack('>I', struct.pack('>f', v))[0]:08x}"


BLOCKS_SPEC: list[dict[str, Any]] = [
    {
        "name": "minecraft:air",
        "props": {},
        "default": {},
        "air": True,
        "fluid": False,
        "solid": False,
        "occlude": False,
        "hardness": 0.0,
        "resistance": 0.0,
        "emission": 0,
        "replaceable": True,
        "has_item": False,
        "map_color": 0,
    },
    {
        "name": "minecraft:water",
        "props": {"level": [str(i) for i in range(16)]},
        "default": {"level": "0"},
        "air": False,
        "fluid": True,
        "solid": False,
        "occlude": False,
        "hardness": 100.0,
        "resistance": 100.0,
        "emission": 0,
        "replaceable": True,
        "has_item": False,
        "map_color": 0x3F76E4,
    },
    {
        "name": "minecraft:lava",
        "props": {"level": [str(i) for i in range(16)]},
        "default": {"level": "0"},
        "air": False,
        "fluid": True,
        "solid": False,
        "occlude": False,
        "hardness": 100.0,
        "resistance": 100.0,
        "emission": 15,
        "replaceable": True,
        "has_item": False,
        "map_color": 0xFF6600,
    },
    {"name": "minecraft:bedrock", "props": {}, "default": {}, "hardness": -1.0, "resistance": 3600000.0, "map_color": 0x565656},
    {"name": "minecraft:stone", "props": {}, "default": {}, "hardness": 1.5, "resistance": 6.0, "requires_tool": True, "map_color": 0x707070},
    {"name": "minecraft:cobblestone", "props": {}, "default": {}, "hardness": 2.0, "resistance": 6.0, "requires_tool": True, "map_color": 0x7A7A7A},
    {"name": "minecraft:dirt", "props": {}, "default": {}, "hardness": 0.5, "resistance": 0.5, "map_color": 0x976D4D},
    {
        "name": "minecraft:grass_block",
        "props": {"snowy": ["false", "true"]},
        "default": {"snowy": "false"},
        "hardness": 0.6,
        "resistance": 0.6,
        "random_ticks": True,
        "map_color": 0x6DB043,
    },
    {"name": "minecraft:sand", "props": {}, "default": {}, "hardness": 0.5, "resistance": 0.5, "map_color": 0xDAD0A0},
    {"name": "minecraft:gravel", "props": {}, "default": {}, "hardness": 0.6, "resistance": 0.6, "map_color": 0x807E7B},
    {"name": "minecraft:oak_planks", "props": {}, "default": {}, "hardness": 2.0, "resistance": 3.0, "map_color": 0x8F7748},
    {
        "name": "minecraft:oak_log",
        "props": {"axis": ["x", "y", "z"]},
        "default": {"axis": "y"},
        "hardness": 2.0,
        "resistance": 2.0,
        "map_color": 0x675231,
    },
    {
        "name": "minecraft:oak_leaves",
        "props": {"distance": [str(i) for i in range(1, 8)], "persistent": ["false", "true"], "waterlogged": ["false", "true"]},
        "default": {"distance": "7", "persistent": "false", "waterlogged": "false"},
        "occlude": False,
        "hardness": 0.2,
        "resistance": 0.2,
        "random_ticks": True,
        "map_color": 0x458E30,
    },
    {"name": "minecraft:bricks", "props": {}, "default": {}, "hardness": 2.0, "resistance": 6.0, "requires_tool": True, "map_color": 0x993333},
    {"name": "minecraft:glass", "props": {}, "default": {}, "occlude": False, "hardness": 0.3, "resistance": 0.3, "map_color": 0xC0E8F8},
    {
        "name": "minecraft:short_grass",
        "props": {},
        "default": {},
        "solid": False,
        "occlude": False,
        "hardness": 0.0,
        "resistance": 0.0,
        "replaceable": True,
        "map_color": 0x4EA338,
    },
    {
        "name": "minecraft:torch",
        "props": {},
        "default": {},
        "solid": False,
        "occlude": False,
        "hardness": 0.0,
        "resistance": 0.0,
        "emission": 14,
        "map_color": 0xFFCC44,
    },
    {"name": "minecraft:coal_ore", "props": {}, "default": {}, "hardness": 3.0, "resistance": 3.0, "requires_tool": True, "map_color": 0x5A5A5A},
    {"name": "minecraft:iron_ore", "props": {}, "default": {}, "hardness": 3.0, "resistance": 3.0, "requires_tool": True, "map_color": 0x8F7E70},
    {"name": "minecraft:snow_block", "props": {}, "default": {}, "hardness": 0.2, "resistance": 0.2, "map_color": 0xFFFFFF},
    {"name": "minecraft:crafting_table", "props": {}, "default": {}, "hardness": 2.5, "resistance": 2.5, "map_color": 0x8F6840},
    {
        "name": "minecraft:furnace",
        "props": {"facing": ["north", "south", "east", "west"], "lit": ["false", "true"]},
        "default": {"facing": "north", "lit": "false"},
        "hardness": 3.5,
        "resistance": 3.5,
        "requires_tool": True,
        "block_entity": True,
        "map_color": 0x707070,
    },
]


def expand_states() -> tuple[dict[str, int], list[dict[str, Any]]]:
    defaults: dict[str, int] = {}
    expanded: list[dict[str, Any]] = []
    for spec in BLOCKS_SPEC:
        props = spec["props"]
        keys = list(props.keys())
        combos = [{}] if not keys else [dict(zip(keys, vals)) for vals in itertools.product(*(props[k] for k in keys))]
        for c in combos:
            sid = len(expanded)
            if c == spec["default"]:
                defaults[spec["name"]] = sid
            expanded.append({"sid": sid, "spec": spec, "props": c})
    return defaults, expanded


# ---------------------------------------------------------------------------
# Writers for JSON, NBT, Assets & Data
# ---------------------------------------------------------------------------

def write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def generate_textures(root: pathlib.Path) -> None:
    tex = root / "assets/minecraft/textures"
    block = tex / "block"
    item = tex / "item"
    gui_bg = tex / "gui/title/background"
    cm = tex / "colormap"

    block_textures = {
        "bedrock": gen_bedrock(),
        "stone": gen_stone(None, 202),
        "cobblestone": gen_cobblestone(),
        "dirt": gen_dirt(),
        "grass_block_top": gen_grass_top(),
        "grass_block_side": gen_grass_side(False),
        "grass_block_snow": gen_grass_side(True),
        "sand": _noise_tex(610, (218, 206, 158), 10),
        "gravel": _noise_tex(611, (130, 127, 124), 18),
        "oak_planks": gen_planks(),
        "oak_log": gen_log_side(),
        "oak_log_top": gen_log_top(),
        "oak_leaves": gen_leaves(),
        "bricks": gen_bricks(),
        "glass": gen_glass(),
        "short_grass": gen_short_grass(),
        "torch": gen_torch(),
        "coal_ore": gen_stone((38, 38, 42), 203),
        "iron_ore": gen_stone((216, 174, 146), 204),
        "snow": _noise_tex(612, (242, 246, 250), 6),
        "crafting_table_top": gen_crafting_top(),
        "crafting_table_side": gen_planks(),
        "furnace_front": gen_furnace_front(False),
        "furnace_front_on": gen_furnace_front(True),
        "furnace_side": gen_cobblestone(),
        "furnace_top": gen_stone(None, 205),
        "water_still": gen_fluid((54, 118, 232), 210, 701),
        "water_flow": gen_fluid((64, 128, 240), 210, 702),
        "water_overlay": gen_fluid((54, 118, 232), 140, 705),
        "lava_still": gen_fluid((238, 108, 28), 255, 703),
        "lava_flow": gen_fluid((246, 124, 34), 255, 704),
    }
    for name, grid in block_textures.items():
        write_png(block / f"{name}.png", 16, 16, grid)

    for fluid_tex in ("water_still", "water_flow", "lava_still", "lava_flow"):
        write_json(block / f"{fluid_tex}.png.mcmeta", {"animation": {"frametime": 2}})

    for stage in range(10):
        grid = gen_destroy_stage(stage)
        write_png(block / f"destroy_stage_{stage}.png", 16, 16, grid)
        write_png(block / f"destroy_oit_stage_{stage}.png", 16, 16, grid)

    item_textures = {
        "apple": gen_item_oval((212, 42, 42), (96, 62, 32)),
        "bread": gen_item_oval((198, 148, 72)),
        "coal": gen_item_oval((42, 42, 46)),
        "iron_ingot": gen_item_oval((216, 220, 226)),
        "stick": gen_item_tool((132, 94, 52)),
        "wooden_pickaxe": gen_item_tool((168, 128, 74)),
        "stone_pickaxe": gen_item_tool((138, 138, 142)),
        "iron_pickaxe": gen_item_tool((214, 218, 224)),
        "torch": gen_torch(),
        "short_grass": gen_short_grass(),
    }
    for name, grid in item_textures.items():
        write_png(item / f"{name}.png", 16, 16, grid)

    # Colormaps
    write_png(cm / "grass.png", 256, 256, gen_colormap(lambda x, y: 108 + (x // 4), lambda x, y: 184 - (y // 6), lambda x, y: 72))
    write_png(cm / "foliage.png", 256, 256, gen_colormap(lambda x, y: 84 + (x // 5), lambda x, y: 162 - (y // 6), lambda x, y: 54))
    write_png(cm / "dry_foliage.png", 256, 256, gen_colormap(lambda x, y: 148, lambda x, y: 132, lambda x, y: 68))

    # Panorama
    for face in range(6):
        write_png(gui_bg / f"panorama_{face}.png", 64, 64, gen_panorama_face(face, 64))
    write_png(gui_bg / "panorama_overlay.png", 16, 16, make_grid(16, 16, (0, 0, 0, 0)))

    generate_font_and_gui(root)


# Compact 5x7 font bitmaps (5 bits wide, 7 rows top-to-bottom) for ASCII 32..126.
_FONT_5X7: dict[str, tuple[int, ...]] = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "!": (4, 4, 4, 4, 4, 0, 4),
    '"': (10, 10, 10, 0, 0, 0, 0),
    "#": (10, 31, 10, 10, 31, 10, 0),
    "$": (4, 15, 20, 14, 5, 30, 4),
    "%": (24, 25, 2, 4, 8, 19, 3),
    "&": (12, 18, 20, 8, 21, 18, 13),
    "'": (4, 4, 8, 0, 0, 0, 0),
    "(": (2, 4, 8, 8, 8, 4, 2),
    ")": (8, 4, 2, 2, 2, 4, 8),
    "*": (0, 4, 21, 14, 21, 4, 0),
    "+": (0, 4, 4, 31, 4, 4, 0),
    ",": (0, 0, 0, 0, 4, 4, 8),
    "-": (0, 0, 0, 31, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 12, 12),
    "/": (1, 2, 2, 4, 8, 8, 16),
    "0": (14, 17, 19, 21, 25, 17, 14),
    "1": (4, 12, 4, 4, 4, 4, 14),
    "2": (14, 17, 1, 6, 8, 16, 31),
    "3": (31, 2, 4, 6, 1, 17, 14),
    "4": (2, 6, 10, 18, 31, 2, 2),
    "5": (31, 16, 30, 1, 1, 17, 14),
    "6": (6, 8, 16, 30, 17, 17, 14),
    "7": (31, 1, 2, 4, 8, 8, 8),
    "8": (14, 17, 17, 14, 17, 17, 14),
    "9": (14, 17, 17, 15, 1, 2, 12),
    ":": (0, 12, 12, 0, 12, 12, 0),
    ";": (0, 12, 12, 0, 4, 4, 8),
    "<": (2, 4, 8, 16, 8, 4, 2),
    "=": (0, 0, 31, 0, 31, 0, 0),
    ">": (8, 4, 2, 1, 2, 4, 8),
    "?": (14, 17, 1, 6, 4, 0, 4),
    "@": (14, 17, 23, 21, 23, 16, 14),
    "A": (14, 17, 17, 31, 17, 17, 17),
    "B": (30, 17, 17, 30, 17, 17, 30),
    "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (28, 18, 17, 17, 17, 18, 28),
    "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16),
    "G": (14, 17, 16, 23, 17, 17, 15),
    "H": (17, 17, 17, 31, 17, 17, 17),
    "I": (14, 4, 4, 4, 4, 4, 14),
    "J": (7, 2, 2, 2, 18, 18, 12),
    "K": (17, 18, 20, 24, 20, 18, 17),
    "L": (16, 16, 16, 16, 16, 16, 31),
    "M": (17, 27, 21, 21, 17, 17, 17),
    "N": (17, 25, 21, 19, 17, 17, 17),
    "O": (14, 17, 17, 17, 17, 17, 14),
    "P": (30, 17, 17, 30, 16, 16, 16),
    "Q": (14, 17, 17, 17, 21, 18, 13),
    "R": (30, 17, 17, 30, 20, 18, 17),
    "S": (15, 16, 16, 14, 1, 1, 30),
    "T": (31, 4, 4, 4, 4, 4, 4),
    "U": (17, 17, 17, 17, 17, 17, 14),
    "V": (17, 17, 17, 17, 17, 10, 4),
    "W": (17, 17, 17, 21, 21, 27, 17),
    "X": (17, 17, 10, 4, 10, 17, 17),
    "Y": (17, 17, 10, 4, 4, 4, 4),
    "Z": (31, 1, 2, 4, 8, 16, 31),
    "[": (14, 8, 8, 8, 8, 8, 14),
    "\\": (16, 8, 8, 4, 2, 2, 1),
    "]": (14, 2, 2, 2, 2, 2, 14),
    "^": (4, 10, 17, 0, 0, 0, 0),
    "_": (0, 0, 0, 0, 0, 0, 31),
    "`": (8, 4, 2, 0, 0, 0, 0),
    "a": (0, 0, 14, 1, 15, 17, 15),
    "b": (16, 16, 22, 25, 17, 17, 30),
    "c": (0, 0, 14, 16, 16, 17, 14),
    "d": (1, 1, 13, 19, 17, 17, 15),
    "e": (0, 0, 14, 17, 31, 16, 14),
    "f": (6, 9, 8, 28, 8, 8, 8),
    "g": (0, 15, 17, 17, 15, 1, 14),
    "h": (16, 16, 22, 25, 17, 17, 17),
    "i": (4, 0, 12, 4, 4, 4, 14),
    "j": (2, 0, 6, 2, 2, 18, 12),
    "k": (16, 16, 18, 20, 24, 20, 18),
    "l": (12, 4, 4, 4, 4, 4, 14),
    "m": (0, 0, 26, 21, 21, 17, 17),
    "n": (0, 0, 22, 25, 17, 17, 17),
    "o": (0, 0, 14, 17, 17, 17, 14),
    "p": (0, 0, 30, 17, 30, 16, 16),
    "q": (0, 0, 13, 19, 15, 1, 1),
    "r": (0, 0, 22, 25, 16, 16, 16),
    "s": (0, 0, 14, 16, 14, 1, 30),
    "t": (8, 8, 28, 8, 8, 9, 6),
    "u": (0, 0, 17, 17, 17, 19, 13),
    "v": (0, 0, 17, 17, 17, 10, 4),
    "w": (0, 0, 17, 17, 21, 21, 10),
    "x": (0, 0, 17, 10, 4, 10, 17),
    "y": (0, 0, 17, 17, 15, 1, 14),
    "z": (0, 0, 31, 2, 4, 8, 31),
    "{": (6, 8, 8, 16, 8, 8, 6),
    "|": (4, 4, 4, 4, 4, 4, 4),
    "}": (12, 2, 2, 1, 2, 2, 12),
    "~": (0, 0, 8, 21, 2, 0, 0),
}


def generate_font_and_gui(root: pathlib.Path) -> None:
    # 128x48 ASCII bitmap font sheet (16x6 cells of 8x8)
    w, h = 128, 48
    sheet = make_grid(w, h, (0, 0, 0, 0))
    rows: list[str] = []
    for row_idx in range(6):
        chars = []
        for col_idx in range(16):
            code = 32 + row_idx * 16 + col_idx
            ch = chr(code) if code < 127 else " "
            chars.append(ch)
            glyph = _FONT_5X7.get(ch, _FONT_5X7[" "])
            for gy, bits in enumerate(glyph):
                for gx in range(5):
                    if bits & (1 << (4 - gx)):
                        px = col_idx * 8 + gx
                        py = row_idx * 8 + gy
                        sheet[py * w + px] = (255, 255, 255, 255)
        rows.append("".join(chars))
    write_png(root / "assets/minecraft/textures/font/ascii.png", w, h, sheet)
    write_json(
        root / "assets/minecraft/font/default.json",
        {
            "providers": [
                {"type": "space", "advances": {" ": 4}},
                {"type": "bitmap", "file": "minecraft:font/ascii.png", "height": 8, "ascent": 7, "chars": rows},
            ]
        },
    )

    sprites = root / "assets/minecraft/textures/gui/sprites"

    # Crosshair (15x15)
    ch = make_grid(15, 15, (0, 0, 0, 0))
    for i in range(3, 12):
        ch[7 * 15 + i] = (255, 255, 255, 220)
        ch[i * 15 + 7] = (255, 255, 255, 220)
    write_png(sprites / "hud/crosshair.png", 15, 15, ch)

    # Hotbar (182x22) & selection (24x24)
    hb = make_grid(182, 22, (28, 28, 32, 185))
    for y in range(22):
        for x in range(182):
            if y in (0, 21) or x in (0, 181) or (x - 1) % 20 == 0:
                hb[y * 182 + x] = (140, 144, 154, 230)
    write_png(sprites / "hud/hotbar.png", 182, 22, hb)

    sel = make_grid(24, 24, (0, 0, 0, 0))
    for y in range(24):
        for x in range(24):
            if x < 2 or x >= 22 or y < 2 or y >= 22:
                sel[y * 24 + x] = (240, 244, 255, 245)
    write_png(sprites / "hud/hotbar_selection.png", 24, 24, sel)

    # Experience bar
    write_png(sprites / "hud/experience_bar_background.png", 182, 5, make_grid(182, 5, (30, 34, 30, 210)))
    write_png(sprites / "hud/experience_bar_progress.png", 182, 5, make_grid(182, 5, (116, 224, 68, 245)))

    # 9x9 HUD icons (heart, food, armor, air)
    def icon_heart(fill: tuple[int, int, int, int], half: bool = False) -> list[tuple[int, int, int, int]]:
        mask = [
            " 00   00 ",
            "0110 0110",
            "011101110",
            "011111110",
            "011111110",
            " 0111110 ",
            "  01110  ",
            "   010   ",
            "         ",
        ]
        out = []
        for y, row in enumerate(mask):
            for x, c in enumerate(row):
                if c == "0":
                    out.append((24, 24, 24, 255))
                elif c == "1":
                    out.append((30, 30, 30, 180) if (half and x > 4) else fill)
                else:
                    out.append((0, 0, 0, 0))
        return out

    write_png(sprites / "hud/heart/container.png", 9, 9, icon_heart((40, 40, 44, 175)))
    write_png(sprites / "hud/heart/full.png", 9, 9, icon_heart((224, 38, 46, 255)))
    write_png(sprites / "hud/heart/half.png", 9, 9, icon_heart((224, 38, 46, 255), half=True))
    write_png(sprites / "hud/heart/absorbing_full.png", 9, 9, icon_heart((238, 198, 42, 255)))
    write_png(sprites / "hud/heart/absorbing_half.png", 9, 9, icon_heart((238, 198, 42, 255), half=True))
    write_png(sprites / "hud/food_empty.png", 9, 9, make_grid(9, 9, (52, 42, 34, 195)))
    write_png(sprites / "hud/food_full.png", 9, 9, make_grid(9, 9, (196, 128, 56, 255)))
    write_png(sprites / "hud/food_half.png", 9, 9, make_grid(9, 9, (150, 96, 44, 255)))
    write_png(sprites / "hud/armor_empty.png", 9, 9, make_grid(9, 9, (56, 60, 68, 185)))
    write_png(sprites / "hud/armor_full.png", 9, 9, make_grid(9, 9, (196, 206, 224, 255)))
    write_png(sprites / "hud/armor_half.png", 9, 9, make_grid(9, 9, (140, 150, 168, 255)))
    write_png(sprites / "hud/air.png", 9, 9, make_grid(9, 9, (116, 198, 255, 220)))

    # Buttons & sliders (200x20, 8x20)
    def box(bw: int, bh: int, fill: tuple[int, int, int, int], edge: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
        out = []
        for y in range(bh):
            for x in range(bw):
                out.append(edge if (x in (0, bw - 1) or y in (0, bh - 1)) else fill)
        return out

    write_png(sprites / "widget/button.png", 200, 20, box(200, 20, (112, 114, 122, 240), (36, 38, 42, 255)))
    write_png(sprites / "widget/button_highlighted.png", 200, 20, box(200, 20, (124, 146, 188, 245), (240, 244, 255, 255)))
    write_png(sprites / "widget/button_disabled.png", 200, 20, box(200, 20, (56, 56, 60, 220), (32, 32, 36, 255)))
    write_png(sprites / "widget/slider.png", 200, 20, box(200, 20, (68, 70, 76, 230), (24, 24, 28, 255)))
    write_png(sprites / "widget/slider_handle.png", 8, 20, box(8, 20, (152, 156, 168, 255), (36, 38, 42, 255)))
    write_png(sprites / "widget/slider_highlighted.png", 8, 20, box(8, 20, (164, 186, 224, 255), (240, 244, 255, 255)))


def _cube_all_model(tex: str) -> dict[str, Any]:
    return {
        "textures": {"all": tex, "particle": tex},
        "elements": [
            {
                "from": [0, 0, 0],
                "to": [16, 16, 16],
                "faces": {
                    d: {"uv": [0, 0, 16, 16], "texture": "#all", "cullface": d}
                    for d in ("down", "up", "north", "south", "west", "east")
                },
            }
        ],
    }


def _cube_sided_model(top: str, bottom: str, north: str, south: str, east: str, west: str) -> dict[str, Any]:
    return {
        "textures": {"top": top, "bottom": bottom, "north": north, "south": south, "east": east, "west": west, "particle": north},
        "elements": [
            {
                "from": [0, 0, 0],
                "to": [16, 16, 16],
                "faces": {
                    "up": {"uv": [0, 0, 16, 16], "texture": "#top", "cullface": "up"},
                    "down": {"uv": [0, 0, 16, 16], "texture": "#bottom", "cullface": "down"},
                    "north": {"uv": [0, 0, 16, 16], "texture": "#north", "cullface": "north"},
                    "south": {"uv": [0, 0, 16, 16], "texture": "#south", "cullface": "south"},
                    "east": {"uv": [0, 0, 16, 16], "texture": "#east", "cullface": "east"},
                    "west": {"uv": [0, 0, 16, 16], "texture": "#west", "cullface": "west"},
                },
            }
        ],
    }


def generate_models_and_blockstates(root: pathlib.Path) -> None:
    bs = root / "assets/minecraft/blockstates"
    mb = root / "assets/minecraft/models/block"
    mi = root / "assets/minecraft/models/item"
    it = root / "assets/minecraft/items"

    simple_blocks = [
        "bedrock", "stone", "cobblestone", "dirt", "sand", "gravel", "oak_planks",
        "oak_leaves", "bricks", "glass", "coal_ore", "iron_ore",
    ]
    for name in simple_blocks:
        write_json(mb / f"{name}.json", _cube_all_model(f"minecraft:block/{name}"))
        write_json(bs / f"{name}.json", {"variants": {"": {"model": f"minecraft:block/{name}"}}})

    write_json(mb / "snow_block.json", _cube_all_model("minecraft:block/snow"))
    write_json(bs / "snow_block.json", {"variants": {"": {"model": "minecraft:block/snow_block"}}})

    # Grass block
    write_json(
        mb / "grass_block.json",
        _cube_sided_model(
            "minecraft:block/grass_block_top", "minecraft:block/dirt",
            "minecraft:block/grass_block_side", "minecraft:block/grass_block_side",
            "minecraft:block/grass_block_side", "minecraft:block/grass_block_side",
        ),
    )
    write_json(
        mb / "grass_block_snow.json",
        _cube_sided_model(
            "minecraft:block/snow", "minecraft:block/dirt",
            "minecraft:block/grass_block_snow", "minecraft:block/grass_block_snow",
            "minecraft:block/grass_block_snow", "minecraft:block/grass_block_snow",
        ),
    )
    write_json(
        bs / "grass_block.json",
        {
            "variants": {
                "snowy=false": {"model": "minecraft:block/grass_block"},
                "snowy=true": {"model": "minecraft:block/grass_block_snow"},
            }
        },
    )

    # Oak log
    write_json(
        mb / "oak_log.json",
        _cube_sided_model(
            "minecraft:block/oak_log_top", "minecraft:block/oak_log_top",
            "minecraft:block/oak_log", "minecraft:block/oak_log",
            "minecraft:block/oak_log", "minecraft:block/oak_log",
        ),
    )
    write_json(
        bs / "oak_log.json",
        {
            "variants": {
                "axis=y": {"model": "minecraft:block/oak_log"},
                "axis=z": {"model": "minecraft:block/oak_log", "x": 90},
                "axis=x": {"model": "minecraft:block/oak_log", "x": 90, "y": 90},
            }
        },
    )

    # Crafting table
    write_json(
        mb / "crafting_table.json",
        _cube_sided_model(
            "minecraft:block/crafting_table_top", "minecraft:block/oak_planks",
            "minecraft:block/crafting_table_side", "minecraft:block/crafting_table_side",
            "minecraft:block/crafting_table_side", "minecraft:block/crafting_table_side",
        ),
    )
    write_json(bs / "crafting_table.json", {"variants": {"": {"model": "minecraft:block/crafting_table"}}})

    # Furnace
    write_json(
        mb / "furnace.json",
        _cube_sided_model(
            "minecraft:block/furnace_top", "minecraft:block/furnace_top",
            "minecraft:block/furnace_front", "minecraft:block/furnace_side",
            "minecraft:block/furnace_side", "minecraft:block/furnace_side",
        ),
    )
    write_json(
        mb / "furnace_on.json",
        _cube_sided_model(
            "minecraft:block/furnace_top", "minecraft:block/furnace_top",
            "minecraft:block/furnace_front_on", "minecraft:block/furnace_side",
            "minecraft:block/furnace_side", "minecraft:block/furnace_side",
        ),
    )
    fvars: dict[str, Any] = {}
    for rot, d in ((0, "north"), (90, "east"), (180, "south"), (270, "west")):
        fvars[f"facing={d},lit=false"] = {"model": "minecraft:block/furnace", "y": rot}
        fvars[f"facing={d},lit=true"] = {"model": "minecraft:block/furnace_on", "y": rot}
    write_json(bs / "furnace.json", {"variants": fvars})

    # Torch & short grass (minimal cuboids)
    write_json(
        mb / "torch.json",
        {
            "textures": {"torch": "minecraft:block/torch", "particle": "minecraft:block/torch"},
            "elements": [
                {
                    "from": [7, 0, 7],
                    "to": [9, 10, 9],
                    "faces": {
                        d: {"uv": [7, 6, 9, 16], "texture": "#torch"}
                        for d in ("down", "up", "north", "south", "west", "east")
                    },
                }
            ],
        },
    )
    write_json(bs / "torch.json", {"variants": {"": {"model": "minecraft:block/torch"}}})

    write_json(
        mb / "short_grass.json",
        {
            "textures": {"cross": "minecraft:block/short_grass", "particle": "minecraft:block/short_grass"},
            "elements": [
                {
                    "from": [0.8, 0, 8],
                    "to": [15.2, 16, 8],
                    "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True},
                    "faces": {
                        "north": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                        "south": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                    },
                },
                {
                    "from": [8, 0, 0.8],
                    "to": [8, 16, 15.2],
                    "rotation": {"origin": [8, 8, 8], "axis": "y", "angle": 45, "rescale": True},
                    "faces": {
                        "west": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                        "east": {"uv": [0, 0, 16, 16], "texture": "#cross"},
                    },
                },
            ],
        },
    )
    write_json(bs / "short_grass.json", {"variants": {"": {"model": "minecraft:block/short_grass"}}})

    # Fluids & air
    for empty_bs in ("air", "water", "lava"):
        write_json(bs / f"{empty_bs}.json", {"variants": {"": {"model": f"minecraft:block/{empty_bs}"}}})
        write_json(mb / f"{empty_bs}.json", {"textures": {"particle": f"minecraft:block/{'stone' if empty_bs == 'air' else empty_bs + '_still'}"}, "elements": []})

    # Item definitions
    flat_items = ("apple", "bread", "coal", "iron_ingot", "stick", "wooden_pickaxe", "stone_pickaxe", "iron_pickaxe", "torch", "short_grass")
    for name in flat_items:
        write_json(mi / f"{name}.json", {"textures": {"layer0": f"minecraft:item/{name}"}})
        write_json(it / f"{name}.json", {"model": {"type": "minecraft:model", "model": f"minecraft:item/{name}"}})

    for spec in BLOCKS_SPEC:
        if not spec.get("has_item", True):
            continue
        short = spec["name"].split(":", 1)[1]
        if short in flat_items:
            continue
        write_json(it / f"{short}.json", {"model": {"type": "minecraft:model", "model": f"minecraft:block/{short}"}})


def generate_tables(root: pathlib.Path) -> None:
    defaults, expanded = expand_states()

    # 1. facts.json
    facts_states = []
    for entry in expanded:
        spec = entry["spec"]
        props = entry["props"]
        name = spec["name"]
        if not props:
            state_desc = name
            nbt_val: Any = name
        else:
            p_str = ",".join(f"{k}={v}" for k, v in props.items())
            state_desc = f"{name}[{p_str}]"
            nbt_val = {"id": name, "properties": props}
        facts_states.append([name, spec.get("air", False), spec.get("fluid", False), state_desc, nbt_val])
    write_json(root / "facts.json", {"defaults": defaults, "states": facts_states})

    # 2. NBT tables: cached-collision.nbt, occlusion.nbt, movement-properties.nbt
    nbt_states = []
    coll_indices = []
    occ_indices = []
    for entry in expanded:
        spec = entry["spec"]
        props = entry["props"]
        if not props:
            nbt_states.append({"id": (TAG_STRING, spec["name"])})
        else:
            nbt_states.append({
                "id": (TAG_STRING, spec["name"]),
                "properties": (TAG_COMPOUND, {k: (TAG_STRING, v) for k, v in props.items()}),
            })
        is_solid = spec.get("solid", True)
        is_occ = spec.get("occlude", True) and is_solid
        coll_indices.append(1 if is_solid else 0)
        occ_indices.append(1 if is_occ else 0)

    one_fp = 0x3FF0000000000000
    empty_shape = {
        "canonical": (TAG_BYTE, 1),
        "cube": (TAG_BYTE, 0),
        "cube_axes": (TAG_BYTE, 0),
        "x": (TAG_LONG_ARRAY, [0]),
        "y": (TAG_LONG_ARRAY, [0]),
        "z": (TAG_LONG_ARRAY, [0]),
        "occupied": (TAG_BYTE_ARRAY, []),
        "discrete_min": (TAG_INT_ARRAY, [0, 0, 0]),
        "discrete_max": (TAG_INT_ARRAY, [0, 0, 0]),
    }
    full_shape = {
        "canonical": (TAG_BYTE, 2),
        "cube": (TAG_BYTE, 1),
        "cube_axes": (TAG_BYTE, 7),
        "x": (TAG_LONG_ARRAY, [0, one_fp]),
        "y": (TAG_LONG_ARRAY, [0, one_fp]),
        "z": (TAG_LONG_ARRAY, [0, one_fp]),
        "occupied": (TAG_BYTE_ARRAY, [1]),
        "discrete_min": (TAG_INT_ARRAY, [0, 0, 0]),
        "discrete_max": (TAG_INT_ARRAY, [1, 1, 1]),
    }

    write_nbt_root(root / "cached-collision.nbt", {
        "DataVersion": (TAG_INT, DATA_VERSION),
        "states": (TAG_LIST, (TAG_COMPOUND, nbt_states)),
        "shapes": (TAG_LIST, (TAG_COMPOUND, [empty_shape, full_shape])),
        "cached_shapes": (TAG_INT_ARRAY, coll_indices),
    })
    write_nbt_root(root / "occlusion.nbt", {
        "DataVersion": (TAG_INT, DATA_VERSION),
        "states": (TAG_LIST, (TAG_COMPOUND, nbt_states)),
        "shapes": (TAG_LIST, (TAG_COMPOUND, [empty_shape, full_shape])),
        "cached_shapes": (TAG_INT_ARRAY, occ_indices),
    })

    mv_blocks = {}
    for spec in BLOCKS_SPEC:
        mv_blocks[spec["name"]] = (TAG_COMPOUND, {
            "friction": (TAG_FLOAT, 0.6),
            "speedFactor": (TAG_FLOAT, 1.0),
            "jumpFactor": (TAG_FLOAT, 1.0),
            "bounceRestitution": (TAG_FLOAT, 0.0),
            "fallDistanceReduction": (TAG_FLOAT, 0.0),
            "fenceGate": (TAG_BYTE, 0),
        })
    write_nbt_root(root / "movement-properties.nbt", {
        "DataVersion": (TAG_INT, DATA_VERSION),
        "states": (TAG_LIST, (TAG_COMPOUND, nbt_states)),
        "blocks": (TAG_COMPOUND, mv_blocks),
    })

    # 3. block-behaviours.json
    bb_blocks = []
    bb_items = {}
    for spec in BLOCKS_SPEC:
        bb_blocks.append({
            "name": spec["name"],
            "class": ["Block"],
            "interfaces": [],
            "fields": {},
            "dynamic_shape": False,
            "item": spec["name"] if spec.get("has_item", True) else "minecraft:air",
        })
        if spec.get("has_item", True):
            bb_items[spec["name"]] = {"class": ["BlockItem"], "fields": {"block": spec["name"]}}

    bb_states = []
    for entry in expanded:
        spec = entry["spec"]
        props = entry["props"]
        is_air = spec.get("air", False)
        is_fluid = spec.get("fluid", False)
        is_solid = spec.get("solid", True)
        sturdy = 0x3FFFF if is_solid else 0
        flags = 0
        if is_solid:
            flags |= 1 | 4 | 64
        if is_air:
            flags |= 2
        if not is_solid:
            flags |= 32
        fluid_id = 0
        fluid_amount = 0
        falling = False
        if is_fluid:
            lvl = int(props["level"])
            if spec["name"] == "minecraft:water":
                fluid_id = 2 if lvl == 0 else 1
            else:
                fluid_id = 4 if lvl == 0 else 3
            fluid_amount = max(1, 8 - min(lvl, 7))
            falling = lvl >= 8
        bb_states.append([sturdy, flags, fluid_id, fluid_amount, falling, 0, 0, False, "HARP"])

    write_json(root / "block-behaviours.json", {
        "blocks": bb_blocks,
        "states": bb_states,
        "items": bb_items,
        "fluids": ["minecraft:empty", "minecraft:flowing_water", "minecraft:water", "minecraft:flowing_lava", "minecraft:lava"],
        "fire": {},
    })

    # 4. gameplay-facts.json
    full_box = [[0.0, 0.0, 0.0, 1.0, 1.0, 1.0]]
    full_edges = [
        [0.0, 0.0, 0.0, 1.0, 0.0, 0.0], [1.0, 0.0, 0.0, 1.0, 0.0, 1.0],
        [1.0, 0.0, 1.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 1.0, 1.0, 0.0], [1.0, 1.0, 0.0, 1.0, 1.0, 1.0],
        [1.0, 1.0, 1.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 0.0, 1.0, 0.0], [1.0, 0.0, 0.0, 1.0, 1.0, 0.0],
        [1.0, 0.0, 1.0, 1.0, 1.0, 1.0], [0.0, 0.0, 1.0, 0.0, 1.0, 1.0],
    ]
    gp_states = []
    for entry in expanded:
        spec = entry["spec"]
        props = entry["props"]
        is_air = spec.get("air", False)
        is_fluid = spec.get("fluid", False)
        is_solid = spec.get("solid", True)
        is_occ = spec.get("occlude", True) and is_solid
        emission = spec.get("emission", 0)
        if spec["name"] == "minecraft:furnace" and props.get("lit") == "true":
            emission = 13
        gp_states.append({
            "id": entry["sid"],
            "emission": emission,
            "dampening": 15 if is_occ else (1 if is_fluid else 0),
            "skylight_down": not is_occ,
            "shape_occlusion": False,
            "can_occlude": is_occ,
            "solid_render": is_occ,
            "hardness": spec.get("hardness", 1.0),
            "requires_tool": spec.get("requires_tool", False),
            "replaceable": spec.get("replaceable", False),
            "random_ticks": spec.get("random_ticks", False),
            "block_entity": spec.get("block_entity", False),
            "render_shape": "INVISIBLE" if (is_air or is_fluid) else "MODEL",
            "liquid": is_fluid,
            "ignited_by_lava": spec["name"] in ("minecraft:oak_planks", "minecraft:oak_log", "minecraft:oak_leaves", "minecraft:short_grass"),
            "push": "NORMAL" if is_solid else "DESTROY",
            "offset": False,
            "full_collision": is_solid,
            "map_color": spec.get("map_color", 0),
            "outline_offset": False,
            "outline": [] if (is_air or is_fluid) else full_box,
            "outline_edges": [] if (is_air or is_fluid) else full_edges,
            "friction": 0.6,
            "speed_factor": 1.0,
            "jump_factor": 1.0,
            "explosion_resistance": spec.get("resistance", 1.0),
            "item": spec["name"] if spec.get("has_item", True) else "minecraft:air",
            "sound": {
                "volume": 1.0,
                "pitch": 1.0,
                "break": {"id": "minecraft:block.stone.break"},
                "step": {"id": "minecraft:block.stone.step"},
                "place": {"id": "minecraft:block.stone.place"},
                "hit": {"id": "minecraft:block.stone.hit"},
                "fall": {"id": "minecraft:block.stone.fall"},
            },
        })
    write_json(root / "gameplay-facts.json", {"states": gp_states})

    # 5. model-states.json & render-definitions.json
    model_states: dict[str, Any] = {}
    render_defs: dict[str, Any] = {}
    for spec in BLOCKS_SPEC:
        props = spec["props"]
        schema: dict[str, Any] = {}
        for k, vals in props.items():
            if k == "level":
                schema[k] = {"integer": [0, 15]}
            elif k == "distance":
                schema[k] = {"integer": [1, 7]}
            else:
                schema[k] = {"named": vals}
        combos = [{}] if not props else [
            dict(zip(props.keys(), vals))
            for vals in itertools.product(*(props[k] for k in props))
        ]
        model_states[spec["name"]] = {"schema": schema, "states": combos}

        is_occ = spec.get("occlude", True) and spec.get("solid", True)
        if spec["name"] in ("minecraft:water", "minecraft:lava"):
            rule = "liquid"
        elif spec["name"] == "minecraft:oak_leaves":
            rule = "leaves"
        elif spec["name"] == "minecraft:glass":
            rule = "same_block"
        elif is_occ:
            rule = "never"
        else:
            rule = "never"
        state_ids = [e["sid"] for e in expanded if e["spec"]["name"] == spec["name"]]
        render_defs[spec["name"]] = {
            "rule": rule,
            "can_occlude": is_occ,
            "bars_tag": False,
            "default": defaults[spec["name"]],
            "states": state_ids,
        }
    write_json(root / "model-states.json", model_states)
    write_json(root / "render-definitions.json", render_defs)

    # 6. block-tags.json (BTreeMap<String, String> where each value is JSON '{"values":[...]}')
    solid_names = [s["name"] for s in BLOCKS_SPEC if s.get("solid", True)]
    raw_block_tags = {
        "minecraft:blocks_motion_in_heightmap": solid_names,
        "minecraft:blocks_motion_in_heightmap_no_leaves": [n for n in solid_names if n != "minecraft:oak_leaves"],
        "minecraft:blocks_fluid_flow": solid_names,
        "minecraft:trapdoors": [],
        "minecraft:climbable": [],
        "minecraft:can_glide_through": [],
        "minecraft:fences": [],
        "minecraft:walls": [],
        "minecraft:suppresses_bounce": [],
        "minecraft:causes_suffocation": [n for n in solid_names if n not in ("minecraft:glass", "minecraft:oak_leaves")],
        "minecraft:soul_speed_blocks": [],
        "minecraft:fall_damage_resetting": [],
        "minecraft:inside_step_sound_blocks": [],
        "minecraft:combination_step_sound_blocks": [],
        "minecraft:crystal_sound_blocks": [],
        "minecraft:impermeable": ["minecraft:glass"],
        "minecraft:enchantment_power_provider": [],
        "minecraft:enchantment_power_transmitter": [],
        "minecraft:triggers_ambient_dried_ghast_block_sounds": [],
        "minecraft:triggers_ambient_desert_sand_block_sounds": ["minecraft:sand"],
        "minecraft:required_for_poplar_leaf_ambience": [],
        "minecraft:triggers_ambient_desert_dry_vegetation_block_sounds": [],
        "minecraft:terracotta": [],
        "minecraft:pale_oak_logs": [],
        "minecraft:infiniburn_overworld": [],
        "minecraft:infiniburn_nether": [],
        "minecraft:infiniburn_end": [],
        "minecraft:mineable/pickaxe": ["minecraft:stone", "minecraft:cobblestone", "minecraft:bricks", "minecraft:coal_ore", "minecraft:iron_ore", "minecraft:furnace"],
        "minecraft:mineable/axe": ["minecraft:oak_planks", "minecraft:oak_log", "minecraft:crafting_table"],
        "minecraft:mineable/shovel": ["minecraft:dirt", "minecraft:grass_block", "minecraft:sand", "minecraft:gravel", "minecraft:snow_block"],
        "minecraft:leaves": ["minecraft:oak_leaves"],
        "minecraft:logs": ["minecraft:oak_log"],
        "minecraft:planks": ["minecraft:oak_planks"],
    }
    write_json(
        root / "block-tags.json",
        {k: json.dumps({"values": v}, separators=(",", ":")) for k, v in raw_block_tags.items()},
    )

    # 7. items.json + creative-inventory.json + creative-tabs.json
    pick_rules = [{"blocks": ["minecraft:stone", "minecraft:cobblestone", "minecraft:coal_ore", "minecraft:iron_ore", "minecraft:bricks", "minecraft:furnace"], "correct_for_drops": True}]
    items_json: dict[str, Any] = {}
    for spec in BLOCKS_SPEC:
        if spec.get("has_item", True):
            items_json[spec["name"]] = {"minecraft:max_stack_size": 64, "minecraft:rarity": "common"}
    items_json.update({
        "minecraft:apple": {"minecraft:max_stack_size": 64, "minecraft:food": {"nutrition": 4, "saturation": 2.4, "can_always_eat": False}},
        "minecraft:bread": {"minecraft:max_stack_size": 64, "minecraft:food": {"nutrition": 5, "saturation": 6.0, "can_always_eat": False}},
        "minecraft:coal": {"minecraft:max_stack_size": 64},
        "minecraft:iron_ingot": {"minecraft:max_stack_size": 64},
        "minecraft:stick": {"minecraft:max_stack_size": 64},
        "minecraft:wooden_pickaxe": {"minecraft:max_stack_size": 1, "minecraft:max_damage": 59, "minecraft:tool": {"rules": [{**pick_rules[0], "speed": 2.0}], "damage_per_block": 1}},
        "minecraft:stone_pickaxe": {"minecraft:max_stack_size": 1, "minecraft:max_damage": 131, "minecraft:tool": {"rules": [{**pick_rules[0], "speed": 4.0}], "damage_per_block": 1}},
        "minecraft:iron_pickaxe": {"minecraft:max_stack_size": 1, "minecraft:max_damage": 250, "minecraft:tool": {"rules": [{**pick_rules[0], "speed": 6.0}], "damage_per_block": 1}},
    })
    write_json(root / "items.json", items_json)

    all_item_ids = list(items_json.keys())
    building_items = ["minecraft:stone", "minecraft:cobblestone", "minecraft:oak_planks", "minecraft:oak_log", "minecraft:bricks", "minecraft:glass", "minecraft:snow_block"]
    natural_items = ["minecraft:grass_block", "minecraft:dirt", "minecraft:sand", "minecraft:gravel", "minecraft:oak_leaves", "minecraft:coal_ore", "minecraft:iron_ore", "minecraft:short_grass", "minecraft:bedrock"]
    func_items = ["minecraft:crafting_table", "minecraft:furnace", "minecraft:torch"]
    tools_items = ["minecraft:wooden_pickaxe", "minecraft:stone_pickaxe", "minecraft:iron_pickaxe", "minecraft:apple", "minecraft:bread", "minecraft:stick", "minecraft:coal", "minecraft:iron_ingot"]

    def tab_obj(tid: str, ttype: str, row: str, col: int, title: str, icon: str, stacks: list[str], is_search: bool = False) -> dict[str, Any]:
        obj: dict[str, Any] = {
            "id": tid,
            "type": ttype,
            "row": row,
            "column": col,
            "title": title,
            "icon": f"{{id:\"{icon}\"}}",
            "visible": True,
            "items": [f"{{id:\"{s}\"}}" for s in stacks],
        }
        if is_search:
            obj["lines"] = [[s.split(":", 1)[1].replace("_", " ")] for s in stacks]
            obj["tags"] = [[] for _ in stacks]
        return obj

    write_json(root / "creative-inventory.json", {
        "schema": 3,
        "tabs": [
            tab_obj("minecraft:building_blocks", "CATEGORY", "TOP", 0, "Building Blocks", "minecraft:bricks", building_items),
            tab_obj("minecraft:natural_blocks", "CATEGORY", "TOP", 1, "Natural Blocks", "minecraft:grass_block", natural_items),
            tab_obj("minecraft:functional_blocks", "CATEGORY", "TOP", 2, "Functional Blocks", "minecraft:crafting_table", func_items),
            tab_obj("minecraft:tools_and_utilities", "CATEGORY", "BOTTOM", 0, "Tools & Utilities", "minecraft:iron_pickaxe", tools_items),
            tab_obj("minecraft:search", "SEARCH", "TOP", 5, "Search Items", "minecraft:iron_pickaxe", all_item_ids, is_search=True),
        ],
    })
    write_json(root / "creative-tabs.json", {
        "building_blocks": building_items,
        "natural_blocks": natural_items,
        "functional_blocks": func_items,
        "tools_and_utilities": tools_items,
    })

    # 8. Player / entity / damage / attribute tables
    attrs = [
        ("minecraft:armor", 0.0, 0.0, 30.0),
        ("minecraft:armor_toughness", 0.0, 0.0, 20.0),
        ("minecraft:attack_damage", 2.0, 0.0, 2048.0),
        ("minecraft:attack_knockback", 0.0, 0.0, 5.0),
        ("minecraft:attack_speed", 4.0, 0.0, 1024.0),
        ("minecraft:block_break_speed", 1.0, 0.0, 1024.0),
        ("minecraft:block_interaction_range", 4.5, 0.0, 64.0),
        ("minecraft:entity_interaction_range", 3.0, 0.0, 64.0),
        ("minecraft:fall_damage_multiplier", 1.0, 0.0, 100.0),
        ("minecraft:flying_speed", 0.4, 0.0, 1024.0),
        ("minecraft:follow_range", 32.0, 0.0, 2048.0),
        ("minecraft:gravity", 0.08, -1.0, 1.0),
        ("minecraft:jump_strength", 0.42, 0.0, 32.0),
        ("minecraft:knockback_resistance", 0.0, 0.0, 1.0),
        ("minecraft:max_absorption", 0.0, 0.0, 2048.0),
        ("minecraft:max_health", 20.0, 1.0, 1024.0),
        ("minecraft:mining_efficiency", 0.0, 0.0, 1024.0),
        ("minecraft:movement_efficiency", 0.0, 0.0, 1.0),
        ("minecraft:movement_speed", 0.7, 0.0, 1024.0),
        ("minecraft:oxygen_bonus", 0.0, 0.0, 1024.0),
        ("minecraft:safe_fall_distance", 3.0, -1024.0, 1024.0),
        ("minecraft:scale", 1.0, 0.0625, 16.0),
        ("minecraft:sneaking_speed", 0.3, 0.0, 1.0),
        ("minecraft:step_height", 0.6, 0.0, 10.0),
        ("minecraft:submerged_mining_speed", 0.2, 0.0, 20.0),
        ("minecraft:water_movement_efficiency", 0.0, 0.0, 1.0),
    ]
    player_attr_bases = {aid: f64_hex(d) for aid, d, _, _ in attrs}
    write_json(root / "attributes.json", {
        "data_version": DATA_VERSION,
        "attributes": [
            {"id": aid, "default": f64_hex(d), "syncable": True, "min": f64_hex(mn), "max": f64_hex(mx)}
            for aid, d, mn, mx in attrs
        ],
        "entities": {"minecraft:player": player_attr_bases},
    })
    write_json(root / "player-float-ids.json", {"health": 9, "absorption": 15})
    damage_entries = [
        ("minecraft:fall", "fall", "when_caused_by_living_non_player", 0.0, "hurt", "fall_variants"),
        ("minecraft:stalagmite", "stalagmite", "when_caused_by_living_non_player", 0.0, "hurt", "default"),
        ("minecraft:starve", "starve", "when_caused_by_living_non_player", 0.0, "hurt", "default"),
        ("minecraft:generic", "generic", "when_caused_by_living_non_player", 0.0, "hurt", "default"),
        ("minecraft:in_wall", "inWall", "when_caused_by_living_non_player", 0.0, "hurt", "default"),
        ("minecraft:drown", "drown", "when_caused_by_living_non_player", 0.0, "drowning", "default"),
        ("minecraft:lava", "lava", "when_caused_by_living_non_player", 0.1, "burning", "default"),
        ("minecraft:out_of_world", "outOfWorld", "never", 0.0, "hurt", "default"),
    ]
    write_json(root / "damage-catalog.json", {
        "data_version": DATA_VERSION,
        "types": [
            {
                "id": did,
                "message_id": msg,
                "exhaustion": f32_hex(exh),
                "scaling": scaling,
                "effects": eff,
                "death_message_type": dmsg,
            }
            for did, msg, scaling, exh, eff, dmsg in damage_entries
        ],
    })
    damage_types_map = {}
    for did, msg, scaling, exh, eff, dmsg in damage_entries:
        body = {
            "message_id": msg,
            "scaling": scaling,
            "exhaustion": exh,
            "effects": eff,
            "death_message_type": dmsg,
        }
        damage_types_map[did] = json.dumps(body, separators=(",", ":"))
        write_json(root / "data/minecraft/damage_type" / f"{did.split(':', 1)[1]}.json", body)
    write_json(root / "damage-types.json", damage_types_map)
    write_json(root / "damage-tags.json", {
        "minecraft:bypasses_armor": json.dumps({"values": ["minecraft:fall", "minecraft:starve", "minecraft:out_of_world", "minecraft:drown"]}, separators=(",", ":")),
    })
    write_json(root / "landing-definitions.json", {
        spec["name"]: {"fall": "Block", "bounce": False} for spec in BLOCKS_SPEC
    })
    write_json(root / "entity-types.json", {
        "minecraft:player": {
            "width": 0.6,
            "height": 1.8,
            "eye_height": 1.62,
            "category": "misc",
            "fire_immune": False,
            "attributes": {aid: d for aid, d, _, _ in attrs},
        }
    })
    write_json(root / "entity-models.json", {})

    def reg_entries(names: list[str]) -> dict[str, Any]:
        return {"entries": {n: {"protocol_id": idx} for idx, n in enumerate(names)}}

    write_json(root / "registries.json", {
        "minecraft:block": reg_entries([s["name"] for s in BLOCKS_SPEC]),
        "minecraft:item": reg_entries(["minecraft:air"] + all_item_ids),
        "minecraft:fluid": reg_entries(["minecraft:empty", "minecraft:flowing_water", "minecraft:water", "minecraft:flowing_lava", "minecraft:lava"]),
        "minecraft:entity_type": reg_entries(["minecraft:player"]),
        "minecraft:attribute": reg_entries([aid for aid, _, _, _ in attrs]),
        "minecraft:block_entity_type": reg_entries(["minecraft:furnace"]),
        "minecraft:command_argument_type": reg_entries(["brigadier:bool", "brigadier:float", "brigadier:double", "brigadier:integer", "brigadier:long", "brigadier:string"]),
        "minecraft:map_decoration_type": reg_entries(["minecraft:player"]),
        "minecraft:mob_effect": reg_entries(["minecraft:speed"]),
        "minecraft:particle_type": reg_entries(["minecraft:flame"]),
        "minecraft:potion": reg_entries(["minecraft:water"]),
        "minecraft:sound_event": reg_entries(["minecraft:block.stone.break", "minecraft:block.stone.step", "minecraft:block.stone.place", "minecraft:block.stone.hit", "minecraft:block.stone.fall"]),
        "minecraft:menu": reg_entries(["minecraft:crafting", "minecraft:furnace"]),
        "minecraft:data_component_type": reg_entries(["minecraft:max_stack_size", "minecraft:max_damage", "minecraft:damage", "minecraft:tool", "minecraft:food", "minecraft:rarity"]),
    })
    write_json(root / "commands.json", {"type": "root", "children": {}})
    splashes = root / "assets/minecraft/texts/splashes.txt"
    splashes.parent.mkdir(parents=True, exist_ok=True)
    splashes.write_text("RuCraft in Rust!\nMojang-free assets!\nOpen Source Engine!\n", encoding="utf-8")
    write_json(root / "assets/minecraft/lang/en_us.json", {})

    # 9. Assets metadata + Data packs (dimensions, biomes, fluid tags, starter recipes)
    write_json(root / "assets/pack.mcmeta", {"pack": {"pack_format": 64, "description": "RuCraft Built-in Resources"}})
    write_json(root / "assets/minecraft/sounds.json", {})
    write_json(root / "data/minecraft/tags/fluid/water.json", {"values": ["minecraft:water", "minecraft:flowing_water"]})
    write_json(root / "data/minecraft/tags/fluid/lava.json", {"values": ["minecraft:lava", "minecraft:flowing_lava"]})
    (root / "data/minecraft/tags/entity_type").mkdir(parents=True, exist_ok=True)

    dim_base = {
        "has_skylight": True,
        "has_ceiling": False,
        "ultrawarm": False,
        "natural": True,
        "coordinate_scale": 1.0,
        "bed_works": True,
        "respawn_anchor_works": False,
        "min_y": -64,
        "height": 384,
        "logical_height": 384,
        "infiniburn": "#minecraft:infiniburn_overworld",
        "ambient_light": 0.0,
        "piglin_safe": False,
        "has_raids": True,
        "monster_spawn_light_level": 0,
        "monster_spawn_block_light_limit": 0,
        "skybox": "overworld",
        "cardinal_light": "default",
        "attributes": {},
        "timelines": [],
    }
    write_json(root / "data/minecraft/dimension_type/overworld.json", dim_base)
    write_json(root / "data/minecraft/dimension_type/the_nether.json", {**dim_base, "has_skylight": False, "has_ceiling": True, "ultrawarm": True, "natural": False, "coordinate_scale": 8.0, "min_y": 0, "height": 256, "logical_height": 128, "ambient_light": 0.1, "skybox": "none", "cardinal_light": "nether"})
    write_json(root / "data/minecraft/dimension_type/the_end.json", {**dim_base, "has_skylight": True, "natural": False, "min_y": 0, "height": 256, "logical_height": 256, "skybox": "end"})

    write_json(root / "data/minecraft/worldgen/biome/plains.json", {
        "has_precipitation": True,
        "temperature": 0.8,
        "downfall": 0.4,
        "effects": {
            "sky_color": 7907327,
            "fog_color": 12638463,
            "water_color": 4159204,
            "water_fog_color": 329011,
        },
        "attributes": {},
        "spawners": {},
        "spawn_costs": {},
    })

    recipes = {
        "oak_planks.json": {"type": "minecraft:crafting_shapeless", "ingredients": ["minecraft:oak_log"], "result": {"id": "minecraft:oak_planks", "count": 4}},
        "stick.json": {"type": "minecraft:crafting_shaped", "pattern": ["#", "#"], "key": {"#": "minecraft:oak_planks"}, "result": {"id": "minecraft:stick", "count": 4}},
        "crafting_table.json": {"type": "minecraft:crafting_shaped", "pattern": ["##", "##"], "key": {"#": "minecraft:oak_planks"}, "result": {"id": "minecraft:crafting_table", "count": 1}},
        "furnace.json": {"type": "minecraft:crafting_shaped", "pattern": ["###", "# #", "###"], "key": {"#": "minecraft:cobblestone"}, "result": {"id": "minecraft:furnace", "count": 1}},
        "torch.json": {"type": "minecraft:crafting_shaped", "pattern": ["C", "|"], "key": {"C": "minecraft:coal", "|": "minecraft:stick"}, "result": {"id": "minecraft:torch", "count": 4}},
        "wooden_pickaxe.json": {"type": "minecraft:crafting_shaped", "pattern": ["PPP", " | ", " | "], "key": {"P": "minecraft:oak_planks", "|": "minecraft:stick"}, "result": {"id": "minecraft:wooden_pickaxe", "count": 1}},
        "stone_pickaxe.json": {"type": "minecraft:crafting_shaped", "pattern": ["CCC", " | ", " | "], "key": {"C": "minecraft:cobblestone", "|": "minecraft:stick"}, "result": {"id": "minecraft:stone_pickaxe", "count": 1}},
        "iron_pickaxe.json": {"type": "minecraft:crafting_shaped", "pattern": ["III", " | ", " | "], "key": {"I": "minecraft:iron_ingot", "|": "minecraft:stick"}, "result": {"id": "minecraft:iron_pickaxe", "count": 1}},
        "iron_ingot_from_smelting_iron_ore.json": {"type": "minecraft:smelting", "ingredient": "minecraft:iron_ore", "result": {"id": "minecraft:iron_ingot"}, "experience": 0.7, "cookingtime": 200},
    }
    for fname, body in recipes.items():
        write_json(root / "data/minecraft/recipe" / fname, body)

    # 10. Manifest & prepare stamp
    write_json(root / "horizon-resources.json", {
        "schema": SCHEMA_VERSION,
        "minecraft": "26.3",
        "data_version": DATA_VERSION,
        "generator": "rucraft-procedural",
    })
    write_json(root / "horizon-prepare.json", {"output_version": OUTPUT_VERSION})


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: generate_rucraft_resources.py <output_resources_dir>", file=sys.stderr)
        return 1
    root = pathlib.Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    print(f"[RuCraft] Generating standalone procedural resources into {root}", flush=True)
    generate_textures(root)
    generate_models_and_blockstates(root)
    generate_tables(root)
    print("[RuCraft] Resource generation complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
