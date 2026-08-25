#!/usr/bin/env python3
"""Build strictly validated Korean-capable AMS2 BFONT/DDS resources.

The builder generalizes the data-only KR-007 reference implementation:

* page 0 is always the exact base DDS;
* every base glyph record and the base variable/footer payload are retained;
* missing requested Korean-source records are appended in codepoint order;
* output BFONTs use the version-10 multi-atlas contract;
* Korean12/17/31 is selected by actual line-height/baseline distance and fit;
* Korean31 source sampling honors its source page/index contract;
* DXT3 bases use the runtime-proven KR-007 L8-to-alpha conversion;
* L8 bases retain raw L8/SDF field semantics on generated pages; and
* every build is reconstructed, parsed, coverage-gated, and hashed.

The tool refuses writes under the AMS2 game directory or any Golden tree.
It never installs resources or launches the game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA = "ams2-kr-008-generated-korean-font-v1"
CORPUS_SCHEMA = "ams2-kr-008-korean-glyph-corpus-v1"
SENTINEL = 0x1234ABCD
NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
SIZE_RE = re.compile(r"^(\d+)[xX](\d+)$")
DEFAULT_SDF_LOW = 120.0
DEFAULT_SDF_HIGH = 136.0
DEFAULT_MAX_ATLAS = 2048
ROOT = Path(__file__).resolve().parent
DEFAULT_CORPUS_DIR = ROOT / "corpora"
DEFAULT_FORBIDDEN_ROOTS = (
    Path(r"E:\SteamLibrary\steamapps\common\Automobilista 2"),
    Path(r"E:\AMS2_Korean_Work\Golden"),
    Path(r"E:\AMS2_Korean_Work\GOLDEN"),
)


class FontBuildError(RuntimeError):
    """Rejected input, unsafe output, unsupported contract, or failed gate."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def unpack_from(fmt: str, data: bytes, offset: int, label: str):
    try:
        return struct.unpack_from(fmt, data, offset)
    except struct.error as exc:
        raise FontBuildError(f"{label}: truncated at 0x{offset:X}") from exc


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def path_is_under(path: Path, root: Path) -> bool:
    candidate = os.path.normcase(str(path.resolve()))
    parent = os.path.normcase(str(root.resolve()))
    try:
        return os.path.commonpath((candidate, parent)) == parent
    except ValueError:
        return False


def ensure_safe_output(path: Path) -> Path:
    resolved = path.resolve()
    for forbidden in DEFAULT_FORBIDDEN_ROOTS:
        if path_is_under(resolved, forbidden):
            raise FontBuildError(f"refusing output under protected root {forbidden}: {resolved}")
    return resolved


def atomic_write(path: Path, data: bytes, force: bool) -> None:
    path = ensure_safe_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FontBuildError(f"refusing to replace without --force: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class BFont:
    label: str
    raw: bytes
    version: int
    scale_bits: int
    scale: float
    field_08: int
    field_0c: int
    name: str
    name_bytes: bytes
    field_after_name_1: int
    field_after_name_2: int
    glyph_count: int
    codepoints: tuple[int, ...]
    uvs: tuple[tuple[float, float, float, float], ...]
    metrics: tuple[tuple[int, int, int], ...]
    codepoint_bytes: bytes
    uv_bytes: bytes
    metric_bytes: bytes
    footer: bytes
    line_height: int
    baseline: int
    atlas_count: int
    glyphs_per_atlas: int
    variable_count: int
    variable_bytes: int


def parse_bfont(data: bytes, label: str) -> BFont:
    if len(data) < 40:
        raise FontBuildError(f"{label}: BFONT too short")
    version = unpack_from("<I", data, 0, label)[0]
    scale_bits = unpack_from("<I", data, 4, label)[0]
    scale = unpack_from("<f", data, 4, label)[0]
    field_08, field_0c, name_length = unpack_from("<III", data, 8, label)
    if version not in (9, 10):
        raise FontBuildError(f"{label}: unsupported BFONT version {version}")
    if not math.isfinite(scale) or scale <= 0:
        raise FontBuildError(f"{label}: invalid scale {scale!r}")
    if not 1 <= name_length <= 255:
        raise FontBuildError(f"{label}: invalid embedded name length {name_length}")
    name_start, name_end = 20, 20 + name_length
    if name_end + 12 > len(data):
        raise FontBuildError(f"{label}: embedded name exceeds file")
    name_bytes = data[name_start:name_end]
    try:
        name = name_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FontBuildError(f"{label}: embedded name is not UTF-8") from exc
    if not NAME_RE.fullmatch(name):
        raise FontBuildError(f"{label}: unsafe embedded name {name!r}")
    after_1, after_2, glyph_count = unpack_from("<III", data, name_end, label)
    if not 1 <= glyph_count <= 65535:
        raise FontBuildError(f"{label}: invalid glyph count {glyph_count}")
    cp_start = name_end + 12
    uv_start = cp_start + glyph_count * 2
    metric_start = uv_start + glyph_count * 16
    footer_start = metric_start + glyph_count * 12
    if footer_start + 20 > len(data):
        raise FontBuildError(f"{label}: glyph arrays exceed file")
    cp_bytes = data[cp_start:uv_start]
    uv_bytes = data[uv_start:metric_start]
    metric_bytes = data[metric_start:footer_start]
    codepoints = tuple(unpack_from(f"<{glyph_count}H", cp_bytes, 0, label))
    if len(set(codepoints)) != glyph_count:
        raise FontBuildError(f"{label}: duplicate codepoint records")
    uvs = tuple(unpack_from("<4f", uv_bytes, index * 16, label) for index in range(glyph_count))
    for index, uv in enumerate(uvs):
        if not all(math.isfinite(value) for value in uv):
            raise FontBuildError(f"{label}: non-finite UV at index {index}")
        if not (-1e-6 <= uv[0] <= uv[2] <= 1.000001 and -1e-6 <= uv[1] <= uv[3] <= 1.000001):
            raise FontBuildError(f"{label}: invalid UV at index {index}: {uv}")
    metrics = tuple(
        unpack_from("<3i", metric_bytes, index * 12, label) for index in range(glyph_count)
    )
    footer = data[footer_start:]
    line_height, baseline = unpack_from("<II", footer, 0, label)
    if not 1 <= line_height <= 4096 or baseline > line_height * 2:
        raise FontBuildError(f"{label}: implausible line/baseline {line_height}/{baseline}")
    if version == 10:
        if len(footer) < 28:
            raise FontBuildError(f"{label}: truncated v10 footer")
        atlas_count, glyphs_per_atlas, variable_count, variable_bytes = unpack_from(
            "<4I", footer, 8, label
        )
        expected_footer = 24 + variable_bytes + 4
        if atlas_count < 1 or glyphs_per_atlas < 1:
            raise FontBuildError(f"{label}: invalid v10 atlas contract")
    else:
        atlas_count, glyphs_per_atlas = 1, 0
        variable_count, variable_bytes = unpack_from("<II", footer, 8, label)
        expected_footer = 16 + variable_bytes + 4
    if len(footer) != expected_footer:
        raise FontBuildError(
            f"{label}: footer length {len(footer)} != declared {expected_footer}"
        )
    if unpack_from("<I", footer, len(footer) - 4, label)[0] != SENTINEL:
        raise FontBuildError(f"{label}: footer sentinel mismatch")
    return BFont(
        label,
        data,
        version,
        scale_bits,
        scale,
        field_08,
        field_0c,
        name,
        name_bytes,
        after_1,
        after_2,
        glyph_count,
        codepoints,
        uvs,
        metrics,
        cp_bytes,
        uv_bytes,
        metric_bytes,
        footer,
        line_height,
        baseline,
        atlas_count,
        glyphs_per_atlas,
        variable_count,
        variable_bytes,
    )


@dataclass(frozen=True)
class DDS:
    label: str
    raw: bytes
    header: bytes
    payload: bytes
    width: int
    height: int
    flags: int
    pitch_or_linear_size: int
    mipmap_count: int
    pixel_format_flags: int
    fourcc: bytes
    rgb_bits: int
    red_mask: int
    green_mask: int
    blue_mask: int
    alpha_mask: int
    kind: str


def parse_dds(data: bytes, label: str) -> DDS:
    if len(data) < 128 or data[:4] != b"DDS ":
        raise FontBuildError(f"{label}: not a classic DDS")
    if unpack_from("<I", data, 4, label)[0] != 124:
        raise FontBuildError(f"{label}: unsupported DDS header")
    flags, height, width, pitch, _depth, mipmaps = unpack_from("<6I", data, 8, label)
    if width < 1 or height < 1:
        raise FontBuildError(f"{label}: invalid dimensions {width}x{height}")
    if unpack_from("<I", data, 76, label)[0] != 32:
        raise FontBuildError(f"{label}: unsupported pixel format header")
    pf_flags = unpack_from("<I", data, 80, label)[0]
    fourcc = data[84:88]
    rgb_bits, rmask, gmask, bmask, amask = unpack_from("<5I", data, 88, label)
    if fourcc == b"DX10":
        raise FontBuildError(f"{label}: DX10 DDS unsupported")
    if fourcc == b"DXT3":
        kind = "DXT3"
        expected = ((width + 3) // 4) * ((height + 3) // 4) * 16
    elif (pf_flags & 0x20000) and rgb_bits == 8 and rmask == 0xFF:
        kind = "L8"
        expected = width * height
    else:
        raise FontBuildError(
            f"{label}: unsupported DDS format flags=0x{pf_flags:X} fourcc={fourcc!r} "
            f"bpp={rgb_bits} masks=0x{rmask:X}/0x{gmask:X}/0x{bmask:X}/0x{amask:X}"
        )
    payload = data[128:]
    if len(payload) != expected:
        raise FontBuildError(f"{label}: payload {len(payload)} != expected {expected}")
    if mipmaps not in (0, 1):
        raise FontBuildError(f"{label}: mip chains unsupported")
    return DDS(
        label,
        data,
        data[:128],
        payload,
        width,
        height,
        flags,
        pitch,
        mipmaps,
        pf_flags,
        fourcc,
        rgb_bits,
        rmask,
        gmask,
        bmask,
        amask,
        kind,
    )


def make_dds(template: DDS, width: int, height: int, payload: bytes) -> bytes:
    if width % 4 or height % 4:
        raise FontBuildError(f"generated DDS dimensions must be multiples of four: {width}x{height}")
    expected = (
        ((width + 3) // 4) * ((height + 3) // 4) * 16
        if template.kind == "DXT3"
        else width * height
    )
    if len(payload) != expected:
        raise FontBuildError(f"generated DDS payload {len(payload)} != {expected}")
    header = bytearray(template.header)
    if (width, height) != (template.width, template.height):
        struct.pack_into("<II", header, 12, height, width)
        struct.pack_into("<I", header, 20, expected if template.kind == "DXT3" else width)
    # Shipped AMS2 DDS headers often leave pitch/linear-size at zero even when
    # the corresponding flag is present. KR-007 proved pages whose complete
    # 128-byte headers equal the stock standard22 header. Preserve every
    # header byte whenever dimensions do not change; only the payload is new.
    result = bytes(header) + payload
    parsed = parse_dds(result, "generated DDS")
    if parsed.kind != template.kind or (parsed.width, parsed.height) != (width, height):
        raise FontBuildError("generated DDS failed structural round trip")
    return result


def dxt3_alpha_block(payload: bytes | bytearray, block_index: int) -> tuple[int, ...]:
    offset = block_index * 16
    if offset + 16 > len(payload):
        raise FontBuildError(f"DXT3 block {block_index} outside payload")
    values: list[int] = []
    for row in range(4):
        packed = struct.unpack_from("<H", payload, offset + row * 2)[0]
        values.extend(((packed >> (column * 4)) & 0xF) * 17 for column in range(4))
    return tuple(values)


def encode_dxt3_white_block(alpha: Sequence[int]) -> bytes:
    if len(alpha) != 16:
        raise FontBuildError("DXT3 block needs 16 alpha samples")
    alpha_bytes = bytearray()
    for row in range(4):
        packed = 0
        for column in range(4):
            value = int(alpha[row * 4 + column])
            if not 0 <= value <= 255:
                raise FontBuildError(f"alpha outside 0..255: {value}")
            packed |= ((value * 15 + 127) // 255) << (column * 4)
        alpha_bytes += struct.pack("<H", packed)
    color_indices = 0
    for index, value in enumerate(alpha):
        if value == 0:
            color_indices |= 1 << (index * 2)
    return bytes(alpha_bytes + struct.pack("<HHI", 0xFFFF, 0x0000, color_indices))


def source_l8_bilinear(
    dds: DDS,
    sx: float,
    sy: float,
    bounds: tuple[int, int, int, int],
) -> float:
    if dds.kind != "L8":
        raise FontBuildError("source sampler requires L8")
    min_x, min_y, max_x, max_y = bounds
    floor_x, floor_y = math.floor(sx), math.floor(sy)
    x0 = max(min_x, min(max_x, floor_x))
    y0 = max(min_y, min(max_y, floor_y))
    x1 = min(max_x, x0 + 1)
    y1 = min(max_y, y0 + 1)
    fx = max(0.0, min(1.0, sx - floor_x))
    fy = max(0.0, min(1.0, sy - floor_y))
    p00 = dds.payload[y0 * dds.width + x0]
    p10 = dds.payload[y0 * dds.width + x1]
    p01 = dds.payload[y1 * dds.width + x0]
    p11 = dds.payload[y1 * dds.width + x1]
    top = p00 * (1.0 - fx) + p10 * fx
    bottom = p01 * (1.0 - fx) + p11 * fx
    return top * (1.0 - fy) + bottom * fy


def sdf_to_coverage(value: float, low: float, high: float) -> int:
    if not low < high:
        raise FontBuildError("SDF low must be below high")
    if value <= low:
        return 0
    if value >= high:
        return 255
    return int(math.floor((value - low) * 255.0 / (high - low) + 0.5))


@dataclass(frozen=True)
class KoreanSource:
    nominal_size: int
    bfont_path: Path
    bfont_data: bytes
    bfont: BFont
    dds_paths: tuple[Path, ...]
    dds_data: tuple[bytes, ...]
    pages: tuple[DDS, ...]

    def page_for_index(self, index: int) -> tuple[int, DDS]:
        page = 0 if self.bfont.version == 9 else index // self.bfont.glyphs_per_atlas
        if not 0 <= page < len(self.pages):
            raise FontBuildError(f"source index {index} resolves outside source pages")
        return page, self.pages[page]


def load_korean_sources(source_dir: Path) -> dict[int, KoreanSource]:
    source_dir = source_dir.resolve()
    sources: dict[int, KoreanSource] = {}
    for nominal in (12, 17, 31):
        stem = f"font_phoenix_asian_{nominal}_ko"
        bfont_path = source_dir / f"{stem}.bfont"
        if not bfont_path.is_file():
            raise FontBuildError(f"missing Korean{nominal} BFONT: {bfont_path}")
        bfont_data = bfont_path.read_bytes()
        font = parse_bfont(bfont_data, str(bfont_path))
        if font.name != stem or font.glyph_count != 1020:
            raise FontBuildError(f"Korean{nominal} source contract mismatch")
        if font.version == 9:
            paths = (source_dir / f"{stem}.dds",)
        else:
            paths = tuple(source_dir / f"{stem}_{page:02d}.dds" for page in range(font.atlas_count))
        if any(not path.is_file() for path in paths):
            raise FontBuildError(f"Korean{nominal}: one or more source DDS pages missing")
        page_data = tuple(path.read_bytes() for path in paths)
        pages = tuple(parse_dds(data, str(path)) for data, path in zip(page_data, paths))
        if any(page.kind != "L8" for page in pages):
            raise FontBuildError(f"Korean{nominal}: source DDS must be L8")
        if font.version == 10 and not (
            (font.atlas_count - 1) * font.glyphs_per_atlas < font.glyph_count
            <= font.atlas_count * font.glyphs_per_atlas
        ):
            raise FontBuildError(f"Korean{nominal}: invalid source page capacity")
        sources[nominal] = KoreanSource(
            nominal, bfont_path, bfont_data, font, paths, page_data, pages
        )
    codepoint_sets = {tuple(sorted(source.bfont.codepoints)) for source in sources.values()}
    if len(codepoint_sets) != 1:
        raise FontBuildError("Korean12/17/31 codepoint sets differ")
    return sources


def resolve_base_dds(base: BFont, explicit: Path | None, root: Path | None) -> Path:
    if explicit is not None:
        path = explicit.resolve()
    else:
        if root is None:
            raise FontBuildError("--base-dds or --base-dds-root is required")
        root = root.resolve()
        candidates = (
            (root / f"{base.name}.dds", root / f"{base.name}_00.dds")
            if base.version == 9
            else (root / f"{base.name}_00.dds", root / f"{base.name}.dds")
        )
        path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        raise FontBuildError(
            f"base page 0 not found for embedded name {base.name!r}: {path}"
        )
    return path


def uv_integer_ratio(font: BFont, dds: DDS) -> float:
    total = 0
    integer = 0
    for u0, v0, u1, v1 in font.uvs:
        for value, dimension in ((u0, dds.width), (u1, dds.width), (v0, dds.height), (v1, dds.height)):
            total += 1
            scaled = value * dimension
            integer += abs(scaled - round(scaled)) <= 0.002
    return integer / total if total else 0.0


def uv_bounds_ratio(font: BFont) -> float:
    """Return the fraction of UV rectangles that are ordered and normalized.

    Some shipped uncompressed AMS2 atlases use sub-texel UV grids (quarters or
    eighths of a DDS texel), so integer texel boundaries are useful diagnostic
    evidence but are not a universal compatibility requirement.  Bounds plus
    decoded glyph occupancy are the format-independent structural checks.
    """
    if not font.uvs:
        return 0.0
    valid = sum(
        0.0 <= u0 <= u1 <= 1.0 and 0.0 <= v0 <= v1 <= 1.0
        for u0, v0, u1, v1 in font.uvs
    )
    return valid / len(font.uvs)


def uv_signal_ratio(font: BFont, dds: DDS) -> float:
    tested = 0
    signaled = 0
    for uv in font.uvs:
        x0, y0 = round(uv[0] * dds.width), round(uv[1] * dds.height)
        x1, y1 = round(uv[2] * dds.width), round(uv[3] * dds.height)
        if x1 <= x0 or y1 <= y0:
            continue
        if not (0 <= x0 < x1 <= dds.width and 0 <= y0 < y1 <= dds.height):
            continue
        tested += 1
        signaled += pixel_signal(dds, (x0, y0, x1, y1))
    return signaled / tested if tested else 0.0


def filename_family_score(base_name: str, dds_stem: str) -> dict[str, Any]:
    base_fold, dds_fold = base_name.casefold(), dds_stem.casefold()
    base_match = re.match(r"^(.*?)(\d+)$", base_fold)
    dds_match = re.match(r"^(.*?)(\d+)$", dds_fold)
    same_numeric_family = bool(
        base_match and dds_match and base_match.group(1) == dds_match.group(1)
    )
    numeric_delta = (
        abs(int(base_match.group(2)) - int(dds_match.group(2)))
        if same_numeric_family
        else None
    )
    shared_prefix = os.path.commonprefix((base_fold, dds_fold))
    return {
        "same_numeric_family": same_numeric_family,
        "numeric_delta": numeric_delta,
        "shared_prefix_chars": len(shared_prefix),
        "score": (
            10.0 / (1 + numeric_delta)
            if same_numeric_family and numeric_delta is not None
            else min(5.0, len(shared_prefix) / 8.0)
        ),
    }


def score_dds_candidate(font: BFont, path: Path) -> dict[str, Any] | None:
    try:
        data = path.read_bytes()
        dds = parse_dds(data, str(path))
    except (OSError, FontBuildError):
        return None
    bounds_ratio = uv_bounds_ratio(font)
    integer_ratio = uv_integer_ratio(font, dds)
    signal_ratio = uv_signal_ratio(font, dds) if bounds_ratio >= 0.95 else 0.0
    family = filename_family_score(font.name, path.stem)
    score = bounds_ratio * 20.0 + integer_ratio * 30.0 + signal_ratio * 40.0 + family["score"]
    return {
        "path": str(path.resolve()),
        "filename": path.name,
        "sha256": sha256_bytes(data),
        "bytes": len(data),
        "pixel_format": dds.kind,
        "dimensions": [dds.width, dds.height],
        "uv_normalized_ordered_ratio": round(bounds_ratio, 9),
        "uv_integer_boundary_ratio": round(integer_ratio, 9),
        "nonblank_glyph_rect_ratio": round(signal_ratio, 9),
        "filename_family": family,
        "heuristic_score": round(score, 6),
    }


def scored_dds_is_structurally_compatible(score: dict[str, Any] | None) -> bool:
    """Gate explicit/exact/peer DDS choices without assuming an integer UV grid."""
    return bool(
        score is not None
        and score["uv_normalized_ordered_ratio"] >= 0.95
        and score["nonblank_glyph_rect_ratio"] >= 0.90
    )


def normalize_dds_roots(root: Path | Sequence[Path] | None) -> tuple[Path, ...]:
    if root is None:
        return ()
    raw = (root,) if isinstance(root, Path) else tuple(root)
    roots: list[Path] = []
    for item in raw:
        resolved = Path(item).resolve()
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def dds_root_provenance(path: Path, root: Path) -> dict[str, Any]:
    """Record which extracted BFF tree supplied a selected DDS."""
    archive = next(
        (
            part
            for part in reversed(root.parts)
            if part.upper().endswith("_BFF")
        ),
        None,
    )
    return {
        "source_root": str(root),
        "source_archive_tree": archive,
        "relative_path": str(path.resolve().relative_to(root)),
    }


def exact_dds_candidates(base: BFont, roots: Sequence[Path]) -> list[tuple[Path, Path]]:
    filenames = (
        (f"{base.name}.dds", f"{base.name}_00.dds")
        if base.version == 9
        else (f"{base.name}_00.dds", f"{base.name}.dds")
    )
    found: list[tuple[Path, Path]] = []
    for root in roots:
        for filename in filenames:
            path = root / filename
            if path.is_file():
                found.append((path.resolve(), root))
                break
    return found


def resolve_base_dds_evidence(
    base_bfont_path: Path,
    base: BFont,
    explicit: Path | None,
    root: Path | Sequence[Path] | None,
) -> tuple[Path | None, dict[str, Any]]:
    if explicit is not None:
        path = explicit.resolve()
        if not path.is_file():
            raise FontBuildError(f"explicit base DDS missing: {path}")
        score = score_dds_candidate(base, path)
        if not scored_dds_is_structurally_compatible(score):
            raise FontBuildError("explicit base DDS is structurally incompatible with BFONT UVs")
        score.update(
            {
                "source_root": str(path.parent),
                "source_archive_tree": None,
                "relative_path": path.name,
            }
        )
        return path, {
            "status": "RESOLVED",
            "method": "explicit_user_path",
            "confidence": "EXPLICIT",
            "selected": score,
            "fail_closed": False,
        }
    roots = normalize_dds_roots(root)
    if not roots:
        raise FontBuildError("--base-dds or --base-dds-root is required")
    exact_found = exact_dds_candidates(base, roots)
    if exact_found:
        exact_scores: list[dict[str, Any]] = []
        for exact, exact_root in exact_found:
            score = score_dds_candidate(base, exact)
            if score is not None:
                score.update(dds_root_provenance(exact, exact_root))
                exact_scores.append(score)
        compatible = [item for item in exact_scores if scored_dds_is_structurally_compatible(item)]
        hashes = {item["sha256"] for item in compatible}
        if len(compatible) != len(exact_found) or not compatible:
            return None, {
                "status": "UNRESOLVED_FAIL_CLOSED",
                "method": "embedded_name_exact_incompatible",
                "confidence": "NONE",
                "selected": None,
                "exact_candidates": exact_scores,
                "fail_closed": True,
                "reason": "One or more embedded-name exact DDS candidates failed decoded structural compatibility.",
            }
        if len(hashes) != 1:
            return None, {
                "status": "UNRESOLVED_FAIL_CLOSED",
                "method": "embedded_name_exact_conflict",
                "confidence": "NONE",
                "selected": None,
                "exact_candidates": exact_scores,
                "fail_closed": True,
                "reason": "Multiple embedded-name exact DDS candidates have different bytes; explicit selection is required.",
            }
        selected = compatible[0]
        return Path(selected["path"]), {
            "status": "RESOLVED",
            "method": "embedded_name_exact",
            "confidence": "HIGH",
            "selected": selected,
            "exact_candidates": exact_scores,
            "fail_closed": False,
        }

    peer_candidates: list[dict[str, Any]] = []
    for peer_path in base_bfont_path.parent.glob("*.bfont"):
        if peer_path.resolve() == base_bfont_path.resolve():
            continue
        try:
            peer = parse_bfont(peer_path.read_bytes(), str(peer_path))
        except (OSError, FontBuildError):
            continue
        if peer.uv_bytes != base.uv_bytes or peer.glyph_count != base.glyph_count:
            continue
        for peer_dds, peer_root in exact_dds_candidates(peer, roots):
            score = score_dds_candidate(base, peer_dds)
            if scored_dds_is_structurally_compatible(score):
                score.update(dds_root_provenance(peer_dds, peer_root))
                score["peer_bfont"] = str(peer_path.resolve())
                score["peer_embedded_name"] = peer.name
                peer_candidates.append(score)
    peer_hashes = {item["sha256"] for item in peer_candidates}
    if peer_candidates and len(peer_hashes) == 1:
        selected = sorted(peer_candidates, key=lambda item: item["filename"].casefold())[0]
        return Path(selected["path"]), {
            "status": "RESOLVED",
            "method": "uv_identical_peer_with_byte_identical_dds",
            "confidence": "HIGH",
            "selected": selected,
            "peer_candidates": peer_candidates,
            "fail_closed": False,
        }

    scored: list[dict[str, Any]] = []
    for candidate_root in roots:
        for path in candidate_root.glob("*.dds"):
            if "font" not in path.name.casefold():
                continue
            candidate = score_dds_candidate(base, path)
            if candidate is not None:
                candidate.update(dds_root_provenance(path, candidate_root))
                scored.append(candidate)
    scored.sort(key=lambda item: (-item["heuristic_score"], item["filename"].casefold()))
    return None, {
        "status": "UNRESOLVED_FAIL_CLOSED",
        "method": "heuristic_rank_only",
        "confidence": "LOW",
        "selected": None,
        "uv_identical_peer_candidates": peer_candidates,
        "top_candidates": scored[:10],
        "fail_closed": True,
        "reason": (
            "No embedded-name exact DDS or unique byte-identical DDS from a UV-identical "
            "BFONT peer. Dimension/integer-UV, decoded occupancy, and filename-family scores "
            "are diagnostic only and do not authorize a build."
        ),
    }


def source_selection(base: BFont, sources: dict[int, KoreanSource], requested: str) -> tuple[KoreanSource, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    for nominal in (12, 17, 31):
        source = sources[nominal]
        offset = base.baseline - source.bfont.baseline
        fits = offset >= 0 and offset + source.bfont.line_height <= base.line_height
        line_delta = base.line_height - source.bfont.line_height
        baseline_delta = base.baseline - source.bfont.baseline
        distance_sq = line_delta * line_delta + 2 * baseline_delta * baseline_delta
        candidates.append(
            {
                "nominal_size": nominal,
                "source_name": source.bfont.name,
                "line_height": source.bfont.line_height,
                "baseline": source.bfont.baseline,
                "vertical_offset": offset,
                "fits_base_line_box": fits,
                "distance_formula": "line_height_delta^2 + 2*baseline_delta^2",
                "distance_squared": distance_sq,
            }
        )
    if requested == "auto":
        viable = [item for item in candidates if item["fits_base_line_box"]]
        if not viable:
            raise FontBuildError(
                f"no Korean12/17/31 source baseline-aligns inside base {base.line_height}/{base.baseline}"
            )
        selected_item = min(viable, key=lambda item: (item["distance_squared"], item["nominal_size"]))
        nominal = int(selected_item["nominal_size"])
    else:
        nominal = int(requested)
        selected_item = next(item for item in candidates if item["nominal_size"] == nominal)
        if not selected_item["fits_base_line_box"]:
            raise FontBuildError(
                f"forced Korean{nominal} does not fit base line/baseline {base.line_height}/{base.baseline}"
            )
    for item in candidates:
        item["selected"] = item["nominal_size"] == nominal
    return sources[nominal], candidates


def parse_glyph_file(path: Path) -> tuple[int, ...]:
    if not path.is_file():
        raise FontBuildError(f"glyph set missing: {path}")
    codepoints: list[int] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0]
        try:
            if token.upper().startswith("U+"):
                codepoint = int(token[2:], 16)
            elif token.lower().startswith("0x"):
                codepoint = int(token, 16)
            elif len(token) == 1:
                codepoint = ord(token)
            else:
                raise ValueError
        except ValueError as exc:
            raise FontBuildError(f"{path}:{line_number}: invalid glyph token {token!r}") from exc
        if not 0 <= codepoint <= 0xFFFF:
            raise FontBuildError(f"{path}:{line_number}: BFONT codepoint exceeds uint16")
        codepoints.append(codepoint)
    if not codepoints:
        raise FontBuildError(f"glyph set is empty: {path}")
    if len(codepoints) != len(set(codepoints)):
        raise FontBuildError(f"glyph set has duplicate codepoints: {path}")
    return tuple(sorted(codepoints))


def resolve_glyph_spec(spec: str, corpus_dir: Path) -> Path:
    if spec == "stock1020":
        return (corpus_dir / "korean-stock-1020.txt").resolve()
    if spec == "current-used":
        return (corpus_dir / "korean-current-used.txt").resolve()
    return Path(spec).resolve()


class ByteReader:
    def __init__(self, data: bytes, label: str):
        self.data = data
        self.label = label
        self.offset = 0

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if end > len(self.data):
            raise FontBuildError(f"{self.label}: unexpected EOF at 0x{self.offset:X}")
        result = self.data[self.offset:end]
        self.offset = end
        return result

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.take(8))[0]

    def lp_utf8(self) -> str:
        return self.take(self.u32()).decode("utf-8")


def korean_values_from_tdb(path: Path) -> tuple[str, ...]:
    data = path.read_bytes()
    reader = ByteReader(data, str(path))
    _version = reader.u32()
    _database = reader.lp_utf8()
    language_count = reader.u32()
    group_count = reader.u32()
    key_count = reader.u32()
    _unknown = reader.u32()
    key_bytes = reader.u32()
    _value_bytes = reader.u32()
    for _ in range(group_count):
        reader.lp_utf8()
    observed_key_bytes = 0
    for _ in range(key_count):
        key = reader.lp_utf8()
        observed_key_bytes += len(key.encode("utf-8")) + 1
    if observed_key_bytes != key_bytes:
        raise FontBuildError(f"{path}: key byte total mismatch")
    korean: tuple[str, ...] | None = None
    for _ in range(language_count):
        language = reader.lp_utf8()
        block_size = reader.u32()
        block_end = reader.offset + block_size
        values: list[str] = []
        for _record in range(key_count):
            reader.u64()
            char_count = reader.u32()
            raw = reader.take(char_count * 2)
            if language == "Korean":
                values.append(raw.decode("utf-16-le"))
        if reader.offset != block_end:
            raise FontBuildError(f"{path}/{language}: block boundary mismatch")
        if language == "Korean":
            korean = tuple(values)
    if reader.offset != len(data):
        raise FontBuildError(f"{path}: trailing bytes after TDB")
    if korean is None:
        raise FontBuildError(f"{path}: Korean language block missing")
    return korean


def corpus_text(title: str, codepoints: Sequence[int]) -> bytes:
    lines = [
        f"# {title}",
        f"# count={len(codepoints)}",
        "# format: U+XXXX<TAB>literal character",
    ]
    lines.extend(f"U+{codepoint:04X}\t{chr(codepoint)}" for codepoint in codepoints)
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_corpora(
    tdb_dirs: Sequence[Path], source_dir: Path, output_dir: Path, force: bool
) -> dict[str, Any]:
    sources = load_korean_sources(source_dir)
    stock = tuple(sorted(sources[17].bfont.codepoints))
    paths = sorted(
        {path.resolve() for directory in tdb_dirs for path in directory.resolve().glob("*.tdb")},
        key=lambda path: (path.name.casefold(), str(path).casefold()),
    )
    if not paths:
        raise FontBuildError("no TDB inputs for corpus")
    current: set[int] = set()
    value_count = 0
    values_with_hangul = 0
    for path in paths:
        values = korean_values_from_tdb(path)
        value_count += len(values)
        for value in values:
            used = {ord(char) for char in value if 0xAC00 <= ord(char) <= 0xD7A3}
            values_with_hangul += bool(used)
            current.update(used)
    current_sorted = tuple(sorted(current))
    missing = tuple(sorted(set(current_sorted) - set(stock)))
    if missing:
        raise FontBuildError(
            "current Korean TDB corpus is not covered by stock source: "
            + ", ".join(f"U+{cp:04X}" for cp in missing[:32])
        )
    output_dir = ensure_safe_output(output_dir)
    stock_data = corpus_text("AMS2 stock Korean source records", stock)
    current_data = corpus_text("AMS2 current Korean TDB Hangul syllables", current_sorted)
    report = {
        "schema": CORPUS_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "tdb": {
            "files": [
                {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_path(path)}
                for path in paths
            ],
            "file_count": len(paths),
            "korean_values": value_count,
            "values_with_hangul": values_with_hangul,
        },
        "stock": {
            "records": len(stock),
            "hangul_syllables": sum(0xAC00 <= cp <= 0xD7A3 for cp in stock),
            "u16le_sha256": sha256_bytes(struct.pack(f"<{len(stock)}H", *stock)),
            "text_sha256": sha256_bytes(stock_data),
            "filename": "korean-stock-1020.txt",
        },
        "current_used": {
            "hangul_syllables": len(current_sorted),
            "coverage_by_stock_percent": 100.0,
            "missing": [],
            "u16le_sha256": sha256_bytes(
                struct.pack(f"<{len(current_sorted)}H", *current_sorted)
            ),
            "text_sha256": sha256_bytes(current_data),
            "filename": "korean-current-used.txt",
        },
        "source_fonts": [
            {
                "nominal_size": nominal,
                "path": str(source.bfont_path),
                "sha256": sha256_bytes(source.bfont_data),
                "codepoint_set_equal": tuple(sorted(source.bfont.codepoints)) == stock,
            }
            for nominal, source in sorted(sources.items())
        ],
    }
    report_data = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write(output_dir / "korean-stock-1020.txt", stock_data, force)
    atomic_write(output_dir / "korean-current-used.txt", current_data, force)
    atomic_write(output_dir / "korean-glyph-corpus.json", report_data, force)
    sums = [
        f"{sha256_bytes(current_data)}  korean-current-used.txt",
        f"{sha256_bytes(report_data)}  korean-glyph-corpus.json",
        f"{sha256_bytes(stock_data)}  korean-stock-1020.txt",
    ]
    atomic_write(output_dir / "SHA256SUMS.txt", ("\n".join(sums) + "\n").encode("ascii"), force)
    return report


@dataclass(frozen=True)
class BuildConfig:
    base_bfont_path: Path
    base_dds_path: Path
    korean_source_dir: Path
    glyph_set_path: Path
    coverage_set_path: Path
    output_name: str
    source_request: str
    page_size: str
    max_atlas_size: int
    sdf_low: float
    sdf_high: float
    base_dds_resolution: dict[str, Any]


@dataclass(frozen=True)
class Inputs:
    config: BuildConfig
    base_bfont_data: bytes
    base_dds_data: bytes
    base: BFont
    base_dds: DDS
    sources: dict[int, KoreanSource]
    source: KoreanSource
    source_candidates: tuple[dict[str, Any], ...]
    requested_codepoints: tuple[int, ...]
    coverage_codepoints: tuple[int, ...]
    appended_codepoints: tuple[int, ...]
    retained_overlaps: tuple[int, ...]
    appended_source_indices: tuple[int, ...]


def load_inputs(config: BuildConfig) -> Inputs:
    base_bfont_data = config.base_bfont_path.read_bytes()
    base = parse_bfont(base_bfont_data, str(config.base_bfont_path))
    if base.version == 10 and base.atlas_count != 1:
        raise FontBuildError("multi-page v10 bases are not yet accepted as page-0-only bases")
    if tuple(sorted(base.codepoints)) != base.codepoints:
        raise FontBuildError("base codepoint table must already be sorted")
    base_dds_data = config.base_dds_path.read_bytes()
    base_dds = parse_dds(base_dds_data, str(config.base_dds_path))
    if base_dds.kind not in ("DXT3", "L8"):
        raise FontBuildError(f"unsupported base DDS strategy: {base_dds.kind}")
    sources = load_korean_sources(config.korean_source_dir)
    source, candidates = source_selection(base, sources, config.source_request)
    requested = parse_glyph_file(config.glyph_set_path)
    coverage = parse_glyph_file(config.coverage_set_path)
    source_set = set(source.bfont.codepoints)
    if not set(requested).issubset(source_set | set(base.codepoints)):
        missing = sorted(set(requested) - source_set - set(base.codepoints))
        raise FontBuildError(
            "requested glyphs absent from base and selected source: "
            + ", ".join(f"U+{cp:04X}" for cp in missing[:32])
        )
    retained = tuple(cp for cp in requested if cp in set(base.codepoints))
    appended = tuple(cp for cp in requested if cp not in set(base.codepoints))
    low_tail = [cp for cp in appended if cp <= base.codepoints[-1]]
    if low_tail:
        raise FontBuildError(
            "append-only sorted table cannot add codepoints below/equal base maximum: "
            + ", ".join(f"U+{cp:04X}" for cp in low_tail[:32])
        )
    combined = set(base.codepoints) | set(appended)
    coverage_missing = sorted(set(coverage) - combined)
    if coverage_missing:
        raise FontBuildError(
            "current-used coverage gate would fail: "
            + ", ".join(f"U+{cp:04X}" for cp in coverage_missing[:32])
        )
    source_index = {cp: index for index, cp in enumerate(source.bfont.codepoints)}
    return Inputs(
        config,
        base_bfont_data,
        base_dds_data,
        base,
        base_dds,
        sources,
        source,
        tuple(candidates),
        requested,
        coverage,
        appended,
        retained,
        tuple(source_index[cp] for cp in appended),
    )


def layout_chunk(
    widths: Sequence[int], line_height: int, width: int, height: int
) -> tuple[tuple[int, int, int, int], ...] | None:
    cursor_x = 0
    row_y = 0
    rectangles: list[tuple[int, int, int, int]] = []
    for glyph_width in widths:
        if glyph_width < 0 or glyph_width > width:
            return None
        x0 = align_up(cursor_x, 4)
        if glyph_width and x0 + glyph_width > width:
            row_y = align_up(row_y + line_height, 4)
            cursor_x = 0
            x0 = 0
        if row_y + line_height > height:
            return None
        x1 = x0 + glyph_width
        rectangles.append((x0, row_y, x1, row_y + line_height))
        if glyph_width:
            cursor_x = align_up(x1, 4) + 4
    return tuple(rectangles)


def dimension_candidates(start: int, maximum: int) -> tuple[int, ...]:
    if start > maximum:
        raise FontBuildError(f"base dimension {start} exceeds max atlas {maximum}")
    values = [align_up(start, 4)]
    value = 1 << max(2, (start - 1).bit_length())
    while value <= maximum:
        if value not in values:
            values.append(value)
        value *= 2
    return tuple(sorted(values))


def select_page_dimensions(
    chunks: Sequence[Sequence[int]],
    line_height: int,
    base_dds: DDS,
    page_size: str,
    maximum: int,
) -> tuple[int, int]:
    if page_size == "base":
        candidates = ((base_dds.width, base_dds.height),)
    elif page_size == "auto":
        candidates = tuple(
            (width, height)
            for width in dimension_candidates(base_dds.width, maximum)
            for height in dimension_candidates(base_dds.height, maximum)
        )
    else:
        match = SIZE_RE.fullmatch(page_size)
        if not match:
            raise FontBuildError("--page-size must be auto, base, or WIDTHxHEIGHT")
        candidates = ((int(match.group(1)), int(match.group(2))),)
    viable = [
        (width, height)
        for width, height in candidates
        if width % 4 == 0
        and height % 4 == 0
        and width <= maximum
        and height <= maximum
        and all(layout_chunk(chunk, line_height, width, height) is not None for chunk in chunks)
    ]
    if not viable:
        raise FontBuildError(
            f"Korean page layout does not fit page-size={page_size}, max={maximum}"
        )
    base_ratio = base_dds.width / base_dds.height
    return min(
        viable,
        key=lambda item: (
            item[0] * item[1],
            abs(math.log2((item[0] / item[1]) / base_ratio)),
            max(item),
            item[0],
        ),
    )


@dataclass(frozen=True)
class PackedGlyph:
    codepoint: int
    source_index: int
    source_page: int
    global_index: int
    page: int
    local_index: int
    metrics: tuple[int, int, int]
    source_uv: tuple[float, float, float, float]
    target_rect: tuple[int, int, int, int]
    target_uv: tuple[float, float, float, float]
    nonzero_samples: int
    maximum_sample: int


@dataclass(frozen=True)
class PageBuild:
    page: int
    dds: bytes
    glyphs: tuple[PackedGlyph, ...]
    width: int
    height: int
    changed_units: int


@dataclass(frozen=True)
class BuildResult:
    bfont: bytes
    pages: tuple[PageBuild, ...]
    glyphs: tuple[PackedGlyph, ...]
    page_width: int
    page_height: int


def source_sample_parameters(source: KoreanSource, source_index: int) -> tuple[int, DDS, float, float, float, float, tuple[int, int, int, int]]:
    source_page, dds = source.page_for_index(source_index)
    uv = source.bfont.uvs[source_index]
    left, top = uv[0] * dds.width, uv[1] * dds.height
    right, bottom = uv[2] * dds.width, uv[3] * dds.height
    bounds = (
        max(0, math.floor(left)),
        max(0, math.floor(top)),
        min(dds.width - 1, math.ceil(right) - 1),
        min(dds.height - 1, math.ceil(bottom) - 1),
    )
    return source_page, dds, left, top, right, bottom, bounds


def pack_page(
    inputs: Inputs,
    page: int,
    pairs: Sequence[tuple[int, int]],
    width: int,
    height: int,
) -> PageBuild:
    base, source = inputs.base, inputs.source
    widths = [source.bfont.metrics[index][1] for _cp, index in pairs]
    rectangles = layout_chunk(widths, base.line_height, width, height)
    if rectangles is None:
        raise FontBuildError(f"page {page} unexpectedly overflowed {width}x{height}")
    vertical_offset = base.baseline - source.bfont.baseline
    if vertical_offset < 0 or vertical_offset + source.bfont.line_height > base.line_height:
        raise FontBuildError("selected source no longer fits base line box")
    samples: dict[tuple[int, int], int] = {}
    glyphs: list[PackedGlyph] = []
    for ordinal, ((codepoint, source_index), rect) in enumerate(zip(pairs, rectangles)):
        global_index = page * base.glyph_count + ordinal
        expected_global = base.glyph_count + (page - 1) * base.glyph_count + ordinal
        if global_index != expected_global:
            raise FontBuildError("page/global index formula failed")
        metrics = source.bfont.metrics[source_index]
        glyph_width = metrics[1]
        if glyph_width < 0 or metrics[2] <= 0:
            raise FontBuildError(f"U+{codepoint:04X}: unsupported metrics {metrics}")
        x0, y0, x1, y1 = rect
        target_uv = (x0 / width, y0 / height, x1 / width, y1 / height)
        source_uv = source.bfont.uvs[source_index]
        nonzero = 0
        maximum = 0
        source_page = 0 if source.bfont.version == 9 else source_index // source.bfont.glyphs_per_atlas
        if glyph_width == 0:
            if source_uv[0] != source_uv[2]:
                raise FontBuildError(f"U+{codepoint:04X}: zero metric width but nonzero UV")
        else:
            source_page, source_dds, left, top, right, bottom, bounds = source_sample_parameters(
                source, source_index
            )
            if right <= left or bottom <= top:
                raise FontBuildError(f"U+{codepoint:04X}: non-positive source UV")
            for dy in range(source.bfont.line_height):
                sy = top + (dy + 0.5) * ((bottom - top) / source.bfont.line_height) - 0.5
                target_y = y0 + vertical_offset + dy
                for dx in range(glyph_width):
                    sx = left + (dx + 0.5) * ((right - left) / glyph_width) - 0.5
                    field = source_l8_bilinear(source_dds, sx, sy, bounds)
                    value = (
                        sdf_to_coverage(field, inputs.config.sdf_low, inputs.config.sdf_high)
                        if inputs.base_dds.kind == "DXT3"
                        else int(math.floor(field + 0.5))
                    )
                    if value:
                        key = (x0 + dx, target_y)
                        samples[key] = max(samples.get(key, 0), value)
                        nonzero += 1
                        maximum = max(maximum, value)
            if nonzero == 0 or maximum < 128:
                raise FontBuildError(f"U+{codepoint:04X}: raster conversion has no usable signal")
        glyphs.append(
            PackedGlyph(
                codepoint,
                source_index,
                source_page,
                global_index,
                page,
                ordinal,
                metrics,
                source_uv,
                rect,
                target_uv,
                nonzero,
                maximum,
            )
        )
    if inputs.base_dds.kind == "DXT3":
        payload = bytearray(((width + 3) // 4) * ((height + 3) // 4) * 16)
        blocks: dict[tuple[int, int], list[int]] = {}
        for (x, y), value in samples.items():
            values = blocks.setdefault((x // 4, y // 4), [0] * 16)
            values[(y % 4) * 4 + x % 4] = value
        for (bx, by), values in blocks.items():
            index = by * (width // 4) + bx
            payload[index * 16 : index * 16 + 16] = encode_dxt3_white_block(values)
        changed_units = sum(any(values) for values in blocks.values())
    else:
        payload = bytearray(width * height)
        for (x, y), value in samples.items():
            payload[y * width + x] = value
        changed_units = sum(value != 0 for value in payload)
    dds = make_dds(inputs.base_dds, width, height, bytes(payload))
    return PageBuild(page, dds, tuple(glyphs), width, height, changed_units)


def build_result(inputs: Inputs) -> BuildResult:
    base = inputs.base
    glyphs_per_atlas = base.glyph_count
    if glyphs_per_atlas < 1:
        raise FontBuildError("base has no page capacity")
    pairs = tuple(zip(inputs.appended_codepoints, inputs.appended_source_indices))
    pair_chunks = tuple(
        pairs[start : start + glyphs_per_atlas]
        for start in range(0, len(pairs), glyphs_per_atlas)
    )
    if not pair_chunks:
        raise FontBuildError("glyph set adds no records; refusing a meaningless conversion")
    width_chunks = tuple(
        tuple(inputs.source.bfont.metrics[index][1] for _cp, index in chunk)
        for chunk in pair_chunks
    )
    page_width, page_height = select_page_dimensions(
        width_chunks,
        base.line_height,
        inputs.base_dds,
        inputs.config.page_size,
        inputs.config.max_atlas_size,
    )
    generated_pages = tuple(
        pack_page(inputs, page, chunk, page_width, page_height)
        for page, chunk in enumerate(pair_chunks, 1)
    )
    all_glyphs = tuple(glyph for page in generated_pages for glyph in page.glyphs)
    atlas_count = 1 + len(generated_pages)
    output_name = inputs.config.output_name
    if not NAME_RE.fullmatch(output_name) or output_name.lower().endswith((".bfont", ".dds")):
        raise FontBuildError(f"unsafe output name {output_name!r}")
    name = output_name.encode("ascii")
    header = (
        struct.pack(
            "<IIIII",
            10,
            base.scale_bits,
            base.field_08,
            base.field_0c,
            len(name),
        )
        + name
        + struct.pack(
            "<III",
            base.field_after_name_1,
            base.field_after_name_2,
            base.glyph_count + len(all_glyphs),
        )
    )
    tail_codepoints = struct.pack(f"<{len(all_glyphs)}H", *(g.codepoint for g in all_glyphs))
    tail_uvs = b"".join(struct.pack("<4f", *glyph.target_uv) for glyph in all_glyphs)
    tail_metrics = b"".join(struct.pack("<3i", *glyph.metrics) for glyph in all_glyphs)
    if base.version == 9:
        footer = base.footer[:8] + struct.pack("<II", atlas_count, glyphs_per_atlas) + base.footer[8:]
    else:
        footer = base.footer[:8] + struct.pack("<II", atlas_count, glyphs_per_atlas) + base.footer[16:]
    bfont = (
        header
        + base.codepoint_bytes
        + tail_codepoints
        + base.uv_bytes
        + tail_uvs
        + base.metric_bytes
        + tail_metrics
        + footer
    )
    page_zero = PageBuild(
        0,
        inputs.base_dds_data,
        tuple(),
        inputs.base_dds.width,
        inputs.base_dds.height,
        0,
    )
    return BuildResult(bfont, (page_zero, *generated_pages), all_glyphs, page_width, page_height)


def pixel_signal(dds: DDS, rect: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = rect
    if x0 == x1:
        return True
    if dds.kind == "L8":
        return any(
            dds.payload[y * dds.width + x]
            for y in range(y0, y1)
            for x in range(x0, x1)
        )
    blocks_wide = dds.width // 4
    for y in range(y0, y1):
        for x in range(x0, x1):
            block = (y // 4) * blocks_wide + x // 4
            alpha = dxt3_alpha_block(dds.payload, block)[(y % 4) * 4 + x % 4]
            if alpha:
                return True
    return False


def source_metric_tail(inputs: Inputs) -> bytes:
    return b"".join(
        struct.pack("<3i", *inputs.source.bfont.metrics[index])
        for index in inputs.appended_source_indices
    )


def validate_result(
    inputs: Inputs,
    expected: BuildResult,
    disk_dir: Path | None = None,
) -> tuple[dict[str, bool], list[dict[str, Any]], bytes, list[bytes]]:
    stem = inputs.config.output_name
    if disk_dir is None:
        bfont_data = expected.bfont
        page_data = [page.dds for page in expected.pages]
    else:
        bfont_path = disk_dir / f"{stem}.bfont"
        page_paths = [disk_dir / f"{stem}_{page:02d}.dds" for page in range(len(expected.pages))]
        if not bfont_path.is_file() or any(not path.is_file() for path in page_paths):
            raise FontBuildError("one or more generated font resources are missing")
        bfont_data = bfont_path.read_bytes()
        page_data = [path.read_bytes() for path in page_paths]
    font = parse_bfont(bfont_data, "generated BFONT")
    parsed_pages = [parse_dds(data, f"generated page {page}") for page, data in enumerate(page_data)]
    base = inputs.base
    appended_count = len(inputs.appended_codepoints)
    combined = set(font.codepoints)
    expected_footer_suffix = base.footer[8:] if base.version == 9 else base.footer[16:]
    checks: dict[str, bool] = {
        "strict_bfont_parse": True,
        "reconstructed_bfont_byte_exact": bfont_data == expected.bfont,
        "reconstructed_pages_byte_exact": page_data == [page.dds for page in expected.pages],
        "embedded_name_exact": font.name == stem,
        "version_10": font.version == 10,
        "glyph_count_exact": font.glyph_count == base.glyph_count + appended_count,
        "duplicate_codepoints_zero": len(set(font.codepoints)) == font.glyph_count,
        "codepoints_sorted": tuple(sorted(font.codepoints)) == font.codepoints,
        "requested_glyph_coverage_100_percent": set(inputs.requested_codepoints).issubset(combined),
        "current_tdb_coverage_100_percent": set(inputs.coverage_codepoints).issubset(combined),
        "current_tdb_missing_zero": len(set(inputs.coverage_codepoints) - combined) == 0,
        "all_base_codepoints_byte_exact": font.codepoint_bytes[: len(base.codepoint_bytes)] == base.codepoint_bytes,
        "all_base_uvs_byte_exact": font.uv_bytes[: len(base.uv_bytes)] == base.uv_bytes,
        "all_base_metrics_byte_exact": font.metric_bytes[: len(base.metric_bytes)] == base.metric_bytes,
        "appended_codepoints_exact": font.codepoints[base.glyph_count :] == inputs.appended_codepoints,
        "appended_metrics_source_exact": font.metric_bytes[len(base.metric_bytes) :] == source_metric_tail(inputs),
        "base_typography_exact": (
            font.scale_bits == base.scale_bits
            and font.field_08 == base.field_08
            and font.field_0c == base.field_0c
            and font.field_after_name_1 == base.field_after_name_1
            and font.field_after_name_2 == base.field_after_name_2
            and font.line_height == base.line_height
            and font.baseline == base.baseline
        ),
        "base_variable_count_exact": font.variable_count == base.variable_count,
        "base_variable_bytes_exact": font.variable_bytes == base.variable_bytes,
        "base_footer_variable_suffix_exact": font.footer[16:] == expected_footer_suffix,
        "atlas_count_exact": font.atlas_count == len(expected.pages),
        "glyphs_per_atlas_equals_base_record_count": font.glyphs_per_atlas == base.glyph_count,
        "all_dds_present_and_strictly_parsed": len(parsed_pages) == len(expected.pages),
        "page_00_entire_dds_byte_exact": page_data[0] == inputs.base_dds_data,
        "all_pages_same_pixel_format_as_base": all(page.kind == inputs.base_dds.kind for page in parsed_pages),
        "generated_page_headers_exact_when_dimensions_match_base": all(
            (page.width, page.height) != (inputs.base_dds.width, inputs.base_dds.height)
            or raw[:128] == inputs.base_dds_data[:128]
            for page, raw in zip(parsed_pages[1:], page_data[1:])
        ),
        "all_uv_bounds_valid": all(
            0.0 <= value <= 1.0 for glyph in expected.glyphs for value in glyph.target_uv
        ),
        "page_assignment_formula_exact": all(
            glyph.page == glyph.global_index // base.glyph_count
            and glyph.local_index == glyph.global_index % base.glyph_count
            for glyph in expected.glyphs
        ),
        "every_nonempty_glyph_has_raster_signal": all(
            pixel_signal(parsed_pages[glyph.page], glyph.target_rect)
            for glyph in expected.glyphs
        ),
        "rectangles_nonoverlapping_per_page": all(
            not rectangles_overlap(left.target_rect, right.target_rect)
            for page in expected.pages[1:]
            for index, left in enumerate(page.glyphs)
            if left.metrics[1] > 0
            for right in page.glyphs[index + 1 :]
            if right.metrics[1] > 0
        ),
        "source_page_assignment_exact": all(
            glyph.source_page
            == (
                0
                if inputs.source.bfont.version == 9
                else glyph.source_index // inputs.source.bfont.glyphs_per_atlas
            )
            for glyph in expected.glyphs
        ),
    }
    if inputs.base_dds.kind == "DXT3":
        checks["dxt3_runtime_reference_conversion_explicit"] = (
            inputs.config.sdf_low == DEFAULT_SDF_LOW and inputs.config.sdf_high == DEFAULT_SDF_HIGH
        )
    else:
        checks["l8_sdf_field_semantics_preserved"] = all(
            page.kind == "L8" for page in parsed_pages
        )
    page_reports: list[dict[str, Any]] = []
    for page_build, parsed, raw in zip(expected.pages, parsed_pages, page_data):
        page_reports.append(
            {
                "page": page_build.page,
                "filename": f"{stem}_{page_build.page:02d}.dds",
                "records": base.glyph_count if page_build.page == 0 else len(page_build.glyphs),
                "global_index_first": page_build.page * base.glyph_count,
                "global_index_last": (
                    base.glyph_count - 1
                    if page_build.page == 0
                    else page_build.glyphs[-1].global_index
                ),
                "dimensions": [parsed.width, parsed.height],
                "pixel_format": parsed.kind,
                "changed_units": page_build.changed_units,
                "bytes": len(raw),
                "sha256": sha256_bytes(raw),
            }
        )
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise FontBuildError("font validation failed: " + ", ".join(failed))
    return checks, page_reports, bfont_data, page_data


def rectangles_overlap(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> bool:
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def input_manifest(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": str(path), "bytes": len(data), "sha256": sha256_bytes(data)}


def make_manifest(
    inputs: Inputs,
    result: BuildResult,
    checks: dict[str, bool],
    pages: list[dict[str, Any]],
    bfont_data: bytes,
) -> dict[str, Any]:
    source = inputs.source
    base = inputs.base
    format_strategy = (
        "KR007_PROVEN_L8_120_136_TO_WHITE_DXT3_EXPLICIT_ALPHA"
        if inputs.base_dds.kind == "DXT3"
        else "RAW_L8_SDF_FIELD_PRESERVING"
    )
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "runtime_status": "OFFLINE_STRICT_VALIDATION_PASS_RUNTIME_PENDING",
        "safety": {
            "game_files_written": False,
            "golden_files_written": False,
            "game_started": False,
            "install_supported_by_this_command": False,
        },
        "base_font": {
            **input_manifest(inputs.config.base_bfont_path, inputs.base_bfont_data),
            "embedded_name": base.name,
            "version": base.version,
            "glyph_count": base.glyph_count,
            "line_height": base.line_height,
            "baseline": base.baseline,
            "variable_count": base.variable_count,
            "variable_bytes": base.variable_bytes,
        },
        "base_dds": {
            **input_manifest(inputs.config.base_dds_path, inputs.base_dds_data),
            "resolved_by_embedded_name": inputs.config.base_dds_path.stem.lower()
            in {base.name.lower(), f"{base.name}_00".lower()},
            "dimensions": [inputs.base_dds.width, inputs.base_dds.height],
            "pixel_format": inputs.base_dds.kind,
        },
        "base_dds_resolution": inputs.config.base_dds_resolution,
        "source_selection": {
            "requested": inputs.config.source_request,
            "selected_nominal_size": source.nominal_size,
            "selected_name": source.bfont.name,
            "selected_bfont": input_manifest(source.bfont_path, source.bfont_data),
            "selected_dds": [
                input_manifest(path, data) for path, data in zip(source.dds_paths, source.dds_data)
            ],
            "candidates": list(inputs.source_candidates),
        },
        "glyph_set": {
            **input_manifest(
                inputs.config.glyph_set_path, inputs.config.glyph_set_path.read_bytes()
            ),
            "requested_records": len(inputs.requested_codepoints),
            "retained_base_overlaps": len(inputs.retained_overlaps),
            "appended_records": len(inputs.appended_codepoints),
            "requested_u16le_sha256": sha256_bytes(
                struct.pack(f"<{len(inputs.requested_codepoints)}H", *inputs.requested_codepoints)
            ),
        },
        "coverage_gate": {
            **input_manifest(
                inputs.config.coverage_set_path, inputs.config.coverage_set_path.read_bytes()
            ),
            "required_records": len(inputs.coverage_codepoints),
            "covered_records": len(inputs.coverage_codepoints),
            "coverage_percent": 100.0,
            "missing_codepoints": [],
        },
        "output_contract": {
            "embedded_name": inputs.config.output_name,
            "bfont_version": 10,
            "glyph_count": base.glyph_count + len(inputs.appended_codepoints),
            "base_records_preserved": base.glyph_count,
            "korean_records_appended": len(inputs.appended_codepoints),
            "atlas_count": len(result.pages),
            "glyphs_per_atlas": base.glyph_count,
            "texture_pattern": f"{inputs.config.output_name}_%02d.dds",
            "page_formula": f"global glyph index // {base.glyph_count}",
            "local_index_formula": f"global glyph index % {base.glyph_count}",
            "page_0_exact_base_dds": True,
            "generated_page_dimensions": [result.page_width, result.page_height],
            "pixel_format_strategy": format_strategy,
            "sdf_low": inputs.config.sdf_low if inputs.base_dds.kind == "DXT3" else None,
            "sdf_high": inputs.config.sdf_high if inputs.base_dds.kind == "DXT3" else None,
        },
        "generated_font": {
            "filename": f"{inputs.config.output_name}.bfont",
            "bytes": len(bfont_data),
            "sha256": sha256_bytes(bfont_data),
            "glyph_count": base.glyph_count + len(inputs.appended_codepoints),
            "korean_coverage": "100%",
            "status": "PASS",
        },
        "dds_files": pages,
        "checks": checks,
        "rebuild": {
            "base_bfont": str(inputs.config.base_bfont_path),
            "base_dds": str(inputs.config.base_dds_path),
            "korean_source_dir": str(inputs.config.korean_source_dir),
            "glyph_set": str(inputs.config.glyph_set_path),
            "coverage_set": str(inputs.config.coverage_set_path),
            "output_name": inputs.config.output_name,
            # Preserve the caller's selector, not merely the selected result.
            # Re-validating an ``auto`` build must reproduce both its choice and
            # the recorded requested-vs-selected provenance exactly.
            "source": inputs.config.source_request,
            "page_size": inputs.config.page_size,
            "max_atlas_size": inputs.config.max_atlas_size,
            "sdf_low": inputs.config.sdf_low,
            "sdf_high": inputs.config.sdf_high,
            "base_dds_resolution": inputs.config.base_dds_resolution,
        },
        "limitations": [
            "Generated resource has not been runtime-tested unless separately recorded outside this manifest.",
            "Mixed page dimensions are structurally valid candidates but only the KR-007 1024x512 DXT3 case has runtime proof.",
            "Version-10 multi-page base fonts are rejected rather than partially preserved.",
        ],
    }


def prepare_config(args: argparse.Namespace) -> BuildConfig:
    base_bfont_path = args.base_bfont.resolve()
    if not base_bfont_path.is_file():
        raise FontBuildError(f"base BFONT missing: {base_bfont_path}")
    base_probe = parse_bfont(base_bfont_path.read_bytes(), str(base_bfont_path))
    base_dds_path, resolution = resolve_base_dds_evidence(
        base_bfont_path, base_probe, args.base_dds, args.base_dds_root
    )
    if base_dds_path is None:
        top = ", ".join(
            f"{item['filename']} score={item['heuristic_score']}"
            for item in resolution.get("top_candidates", [])[:3]
        )
        raise FontBuildError(
            f"base DDS resolution failed closed for {base_probe.name}; diagnostic top: {top}"
        )
    corpus_dir = args.corpus_dir.resolve()
    glyph_path = resolve_glyph_spec(args.glyph_set, corpus_dir)
    coverage_path = resolve_glyph_spec(args.coverage_set, corpus_dir)
    return BuildConfig(
        base_bfont_path,
        base_dds_path,
        args.korean_source_dir.resolve(),
        glyph_path,
        coverage_path,
        args.output_name,
        args.source,
        args.page_size,
        args.max_atlas_size,
        args.sdf_low,
        args.sdf_high,
        resolution,
    )


def run_plan(config: BuildConfig) -> tuple[Inputs, BuildResult, dict[str, Any]]:
    inputs = load_inputs(config)
    result = build_result(inputs)
    checks, pages, bfont_data, _page_data = validate_result(inputs, result)
    manifest = make_manifest(inputs, result, checks, pages, bfont_data)
    return inputs, result, manifest


def write_build(config: BuildConfig, output_dir: Path, force: bool) -> dict[str, Any]:
    output_dir = ensure_safe_output(output_dir)
    inputs, result, manifest = run_plan(config)
    stem = config.output_name
    atomic_write(output_dir / f"{stem}.bfont", result.bfont, force)
    for page in result.pages:
        atomic_write(output_dir / f"{stem}_{page.page:02d}.dds", page.dds, force)
    manifest_data = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write(output_dir / f"{stem}.font-manifest.json", manifest_data, force)
    sums = []
    for path in sorted(output_dir.iterdir(), key=lambda item: item.name.casefold()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            sums.append(f"{sha256_path(path)}  {path.name}")
    atomic_write(output_dir / "SHA256SUMS.txt", ("\n".join(sums) + "\n").encode("ascii"), force)
    # Re-open and compare every resource after atomic publication.
    validate_result(inputs, result, output_dir)
    return manifest


def strip_generated(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_generated(item) for key, item in value.items() if key != "generated_utc"}
    if isinstance(value, list):
        return [strip_generated(item) for item in value]
    return value


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
    if recorded.get("schema") != SCHEMA or recorded.get("status") != "PASS":
        raise FontBuildError("unexpected or non-PASS font manifest")
    rebuild = recorded["rebuild"]
    config = BuildConfig(
        Path(rebuild["base_bfont"]).resolve(),
        Path(rebuild["base_dds"]).resolve(),
        Path(rebuild["korean_source_dir"]).resolve(),
        Path(rebuild["glyph_set"]).resolve(),
        Path(rebuild["coverage_set"]).resolve(),
        rebuild["output_name"],
        rebuild["source"],
        rebuild["page_size"],
        int(rebuild["max_atlas_size"]),
        float(rebuild["sdf_low"]),
        float(rebuild["sdf_high"]),
        rebuild["base_dds_resolution"],
    )
    inputs, result, regenerated = run_plan(config)
    validate_result(inputs, result, manifest_path.parent)
    if strip_generated(recorded) != strip_generated(regenerated):
        raise FontBuildError("recorded manifest differs from deterministic reconstruction")
    sums_path = manifest_path.parent / "SHA256SUMS.txt"
    if not sums_path.is_file():
        raise FontBuildError("SHA256SUMS.txt missing")
    failures = []
    for line in sums_path.read_text(encoding="ascii").splitlines():
        if not line:
            continue
        try:
            expected_hash, filename = line.split("  ", 1)
        except ValueError:
            failures.append(f"syntax:{line}")
            continue
        target = manifest_path.parent / filename
        if not target.is_file() or sha256_path(target) != expected_hash:
            failures.append(filename)
    if failures:
        raise FontBuildError("SHA256SUMS validation failed: " + ", ".join(failures))
    return recorded


def add_build_arguments(parser: argparse.ArgumentParser, output_required: bool) -> None:
    parser.add_argument("--base-bfont", type=Path, required=True)
    parser.add_argument("--base-dds", type=Path)
    parser.add_argument(
        "--base-dds-root",
        type=Path,
        action="append",
        help="repeatable extracted-BFF GUI directory searched for exact embedded-name DDS",
    )
    parser.add_argument("--korean-source-dir", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--glyph-set", default="stock1020")
    parser.add_argument("--coverage-set", default="current-used")
    parser.add_argument("--output-name", required=True)
    parser.add_argument("--source", choices=("auto", "12", "17", "31"), default="auto")
    parser.add_argument("--page-size", default="auto")
    parser.add_argument("--max-atlas-size", type=int, default=DEFAULT_MAX_ATLAS)
    parser.add_argument("--sdf-low", type=float, default=DEFAULT_SDF_LOW)
    parser.add_argument("--sdf-high", type=float, default=DEFAULT_SDF_HIGH)
    if output_required:
        parser.add_argument("--output-dir", type=Path, required=True)
        parser.add_argument("--force", action="store_true")


def build_dds_resolution_inventory(
    bfont_dir: Path,
    dds_root: Sequence[Path],
    font_names: Sequence[str],
) -> dict[str, Any]:
    bfont_dir = bfont_dir.resolve()
    dds_roots = normalize_dds_roots(dds_root)
    if font_names:
        paths = [
            bfont_dir / (name if name.casefold().endswith(".bfont") else f"{name}.bfont")
            for name in font_names
        ]
    else:
        paths = sorted(bfont_dir.glob("ams2_font_*.bfont"), key=lambda path: path.name.casefold())
    records: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            records.append(
                {
                    "requested": path.name,
                    "status": "MISSING_BFONT",
                    "confidence": "NONE",
                    "fail_closed": True,
                }
            )
            continue
        data = path.read_bytes()
        font = parse_bfont(data, str(path))
        selected, evidence = resolve_base_dds_evidence(path, font, None, dds_roots)
        records.append(
            {
                "bfont": {
                    "path": str(path.resolve()),
                    "filename": path.name,
                    "sha256": sha256_bytes(data),
                    "embedded_name": font.name,
                    "version": font.version,
                    "glyph_count": font.glyph_count,
                    "line_height": font.line_height,
                    "baseline": font.baseline,
                    "uv_sha256": sha256_bytes(font.uv_bytes),
                },
                **evidence,
                "resolved_dds": str(selected) if selected else None,
            }
        )
    return {
        "schema": "ams2-kr-008-base-dds-resolution-inventory-v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "bfont_dir": str(bfont_dir),
        "dds_roots": [str(root) for root in dds_roots],
        "font_count": len(records),
        "resolved_high_or_explicit": sum(
            record.get("status") == "RESOLVED"
            and record.get("confidence") in ("HIGH", "EXPLICIT")
            for record in records
        ),
        "unresolved_fail_closed": sum(record.get("fail_closed", False) for record in records),
        "records": records,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    corpus = commands.add_parser("corpus", help="generate stock1020 and current-used glyph sets")
    corpus.add_argument("--tdb-dir", type=Path, action="append", required=True)
    corpus.add_argument("--korean-source-dir", type=Path, required=True)
    corpus.add_argument("--output-dir", type=Path, required=True)
    corpus.add_argument("--force", action="store_true")
    plan = commands.add_parser("plan", help="select source and build/validate entirely in memory")
    add_build_arguments(plan, False)
    build = commands.add_parser("build", help="build BFONT/DDS and strict manifest")
    add_build_arguments(build, True)
    validate = commands.add_parser("validate", help="rebuild and verify a generated font manifest")
    validate.add_argument("--manifest", type=Path, required=True)
    resolver = commands.add_parser(
        "resolve-dds",
        help="inventory base BFONT to DDS resolution and fail closed on low-confidence aliases",
    )
    resolver.add_argument("--base-bfont-dir", type=Path, required=True)
    resolver.add_argument(
        "--base-dds-root",
        type=Path,
        action="append",
        required=True,
        help="repeat for every extracted-BFF GUI directory to search",
    )
    resolver.add_argument("--font-name", action="append", default=[])
    resolver.add_argument("--output", type=Path)
    resolver.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "corpus":
            payload = build_corpora(args.tdb_dir, args.korean_source_dir, args.output_dir, args.force)
            summary = {
                "passed": True,
                "stock_records": payload["stock"]["records"],
                "current_used": payload["current_used"]["hangul_syllables"],
                "output": str(args.output_dir.resolve()),
            }
        elif args.command == "resolve-dds":
            payload = build_dds_resolution_inventory(
                args.base_bfont_dir, args.base_dds_root, args.font_name
            )
            if args.output:
                output_data = (
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                ).encode("utf-8")
                atomic_write(args.output, output_data, args.force)
            summary = {
                "passed": True,
                "font_count": payload["font_count"],
                "resolved_high_or_explicit": payload["resolved_high_or_explicit"],
                "unresolved_fail_closed": payload["unresolved_fail_closed"],
                "output": str(args.output.resolve()) if args.output else None,
            }
        elif args.command == "validate":
            payload = validate_manifest(args.manifest)
            summary = {
                "passed": True,
                "output_name": payload["output_contract"]["embedded_name"],
                "glyph_count": payload["output_contract"]["glyph_count"],
                "atlas_count": payload["output_contract"]["atlas_count"],
            }
        else:
            config = prepare_config(args)
            if args.command == "plan":
                _inputs, _result, payload = run_plan(config)
            else:
                payload = write_build(config, args.output_dir, args.force)
            summary = {
                "passed": True,
                "output_name": payload["output_contract"]["embedded_name"],
                "source": payload["source_selection"]["selected_nominal_size"],
                "glyph_count": payload["output_contract"]["glyph_count"],
                "atlas_count": payload["output_contract"]["atlas_count"],
                "pixel_format": payload["output_contract"]["pixel_format_strategy"],
                "output": str(args.output_dir.resolve()) if args.command == "build" else None,
            }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except (FontBuildError, OSError, UnicodeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
