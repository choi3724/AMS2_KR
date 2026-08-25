#!/usr/bin/env python3
"""Lossless, record-aware editor for the AMS2 BGUI Text records used in KR-005.

The tool deliberately does not claim names for fields whose meaning has not
been demonstrated.  It parses the resource header and every structurally
valid GUI Text style record, preserves every unknown byte verbatim, and only
re-serializes the one-byte-length-prefixed font field.

Safety properties:

* no absolute game-file offset is used to select an edit target;
* all Text records must satisfy the same common layout and UTF-8/font checks;
* the four Options records are found by their Layer/Options/state/settings/Text
  relationships and their independently known layout/style invariants;
* a no-op serialization traverses every parsed Text font field and must be
  byte-identical;
* modified output is reparsed and semantically compared before it is written.

The input file is never opened for writing.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Iterable


EXPECTED_ORIGINAL_SHA256 = (
    "10A751842FBDE41D609D7BEFDCBAAF281583C76ABC0FFC4A33EC519081D56E95"
)
TEXT_MARKER = b"\x04Text\x52\x2B\x5D\x5F"
OPTIONS_MARKER = b"\x07Options\x55\x47\x48\xD2"
SELECTED_MARKER = b"\x08Selected\xA4\x3D\x0C\xC4"
UNSELECTED_MARKER = b"\x0AUnselected\xB3\xD2\x3A\x65"
SETTINGS_MARKER = b"\x08settings\x1A\xE5\x12\x5E"
TARGET_OLD_FONT = "GUI\\ams2_font_standard_22.bfont"
TARGET_FLAGS = 0x00000408


class BGUIError(RuntimeError):
    """Raised when a structural or safety invariant fails."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise BGUIError(f"truncated u32 at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def _f32(data: bytes, offset: int) -> float:
    if offset < 0 or offset + 4 > len(data):
        raise BGUIError(f"truncated f32 at 0x{offset:X}")
    return struct.unpack_from("<f", data, offset)[0]


def _iter_find(data: bytes, marker: bytes) -> Iterable[int]:
    cursor = 0
    while True:
        found = data.find(marker, cursor)
        if found < 0:
            return
        yield found
        cursor = found + 1


def _decode_utf8(data: bytes, start: int, length: int, label: str) -> str:
    end = start + length
    if start < 0 or end > len(data):
        raise BGUIError(f"{label} extends beyond EOF at 0x{start:X}")
    try:
        return data[start:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BGUIError(f"invalid UTF-8 {label} at 0x{start:X}") from exc


@dataclasses.dataclass(frozen=True)
class ResourceHeader:
    scale: float
    count: int
    entries: tuple[str, ...]
    end_offset: int


@dataclasses.dataclass(frozen=True)
class NamedNode:
    start: int
    local_id: int
    name: str
    name_hash: int
    object_id: int
    position: tuple[float, float]
    size: tuple[float, float]


@dataclasses.dataclass(frozen=True)
class TextRecord:
    ordinal: int
    start: int
    local_id: int
    name_hash: int
    object_id: int
    position: tuple[float, float]
    size: tuple[float, float]
    field_f32_2: tuple[float, float]
    clip_rect: tuple[float, float, float, float]
    alignment_style_raw: str
    text_length_offset: int
    text_reference: str
    text_reference_hash: int
    field_after_text_hash: int
    font_length_offset: int
    font_bytes_offset: int
    font: str
    flags_offset: int
    flags: int
    layer: str | None = None
    options_group: int | None = None
    state: str | None = None
    settings_offset: int | None = None

    def semantic(self) -> dict:
        """Offset-free semantic view used to check that only fonts changed."""
        return {
            "local_id": self.local_id,
            "name_hash": self.name_hash,
            "object_id": self.object_id,
            "position": self.position,
            "size": self.size,
            "field_f32_2": self.field_f32_2,
            "clip_rect": self.clip_rect,
            "alignment_style_raw": self.alignment_style_raw,
            "text_reference": self.text_reference,
            "text_reference_hash": self.text_reference_hash,
            "field_after_text_hash": self.field_after_text_hash,
            "font": self.font,
            "flags": self.flags,
            "layer": self.layer,
            "options_group": self.options_group,
            "state": self.state,
        }


@dataclasses.dataclass(frozen=True)
class OptionsTarget:
    group: int
    layer: str
    state: str
    options_start: int
    state_start: int
    settings_start: int
    text_ordinal: int

    @property
    def record_path(self) -> str:
        return f"{self.layer}/Options/{self.state}/settings/Text"


@dataclasses.dataclass
class ParsedBGUI:
    data: bytes
    header: ResourceHeader
    text_records: list[TextRecord]
    targets: list[OptionsTarget]

    @classmethod
    def parse(cls, data: bytes, *, strict_targets: bool = True) -> "ParsedBGUI":
        header = parse_resource_header(data)
        records = parse_text_records(data)
        targets = locate_options_targets(data, records)
        parsed = cls(data=data, header=header, text_records=records, targets=targets)
        parsed._apply_context()
        parsed.validate(strict_targets=strict_targets)
        return parsed

    def _apply_context(self) -> None:
        context = {target.text_ordinal: target for target in self.targets}
        enriched: list[TextRecord] = []
        for record in self.text_records:
            target = context.get(record.ordinal)
            if target is None:
                enriched.append(record)
            else:
                enriched.append(
                    dataclasses.replace(
                        record,
                        layer=target.layer,
                        options_group=target.group,
                        state=target.state,
                        settings_offset=target.settings_start,
                    )
                )
        self.text_records = enriched

    def validate(self, *, strict_targets: bool = True) -> None:
        if not math.isfinite(self.header.scale):
            raise BGUIError("non-finite BGUI header scale")
        if not self.header.entries:
            raise BGUIError("empty BGUI resource table")
        if len(self.text_records) < 1000:
            raise BGUIError(
                f"implausibly few validated Text records: {len(self.text_records)}"
            )
        previous_start = -1
        previous_font_end = -1
        object_ids: set[int] = set()
        for record in self.text_records:
            if record.start <= previous_start:
                raise BGUIError("Text records are not strictly ordered")
            if record.font_length_offset <= record.text_length_offset:
                raise BGUIError(f"invalid Text field order at 0x{record.start:X}")
            if record.font_bytes_offset <= previous_font_end:
                raise BGUIError(f"overlapping font fields at 0x{record.start:X}")
            if not record.font.lower().startswith("gui\\"):
                raise BGUIError(f"non-GUI font path at 0x{record.start:X}")
            if not record.font.lower().endswith(".bfont"):
                raise BGUIError(f"non-BFONT font path at 0x{record.start:X}")
            if not all(
                math.isfinite(value)
                for value in (
                    *record.position,
                    *record.size,
                    *record.field_f32_2,
                    *record.clip_rect,
                )
            ):
                raise BGUIError(f"non-finite geometry at 0x{record.start:X}")
            previous_start = record.start
            previous_font_end = record.font_bytes_offset + len(record.font.encode("utf-8"))
            object_ids.add(record.object_id)
        if len(object_ids) != len(self.text_records):
            raise BGUIError("duplicate Text object identifiers")

        if strict_targets:
            if len(self.targets) != 4:
                raise BGUIError(
                    f"expected exactly four Options Text targets, found {len(self.targets)}"
                )
            expected = {
                ("Layer_MainMenuAMS2", "Selected"),
                ("Layer_MainMenuAMS2", "Unselected"),
                ("Layer_DemoMenuNewLayer", "Selected"),
                ("Layer_DemoMenuNewLayer", "Unselected"),
            }
            actual = {(item.layer, item.state) for item in self.targets}
            if actual != expected:
                raise BGUIError(
                    "Options target topology mismatch: "
                    f"expected {sorted(expected)}, got {sorted(actual)}"
                )
            for target in self.targets:
                record = self.text_records[target.text_ordinal]
                if record.flags != TARGET_FLAGS:
                    raise BGUIError(
                        f"unexpected flags for {target.record_path}: 0x{record.flags:08X}"
                    )
                if record.text_reference:
                    raise BGUIError(
                        f"unexpected inline Text value for {target.record_path}: "
                        f"{record.text_reference!r}"
                    )
                if record.position != (95.0, 10.0):
                    raise BGUIError(
                        f"unexpected position for {target.record_path}: {record.position}"
                    )
                if record.size[0] != 185.0 or record.size[1] not in (42.0, 43.0):
                    raise BGUIError(
                        f"unexpected size for {target.record_path}: {record.size}"
                    )

    def serialize_fonts(self, replacements: dict[int, str]) -> bytes:
        unknown = sorted(set(replacements) - set(range(len(self.text_records))))
        if unknown:
            raise BGUIError(f"unknown Text record ordinals: {unknown}")

        chunks: list[bytes] = []
        cursor = 0
        for record in self.text_records:
            prefix = record.font_length_offset
            old_end = record.font_bytes_offset + len(record.font.encode("utf-8"))
            if prefix < cursor:
                raise BGUIError("font fields overlap during serialization")
            chunks.append(self.data[cursor:prefix])
            new_font = replacements.get(record.ordinal, record.font)
            encoded = new_font.encode("utf-8")
            if not encoded or len(encoded) > 255:
                raise BGUIError(
                    f"font path must be 1..255 UTF-8 bytes, got {len(encoded)}"
                )
            if not new_font.lower().startswith("gui\\") or not new_font.lower().endswith(
                ".bfont"
            ):
                raise BGUIError(f"refusing non-GUI BFONT reference: {new_font!r}")
            chunks.append(bytes((len(encoded),)))
            chunks.append(encoded)
            cursor = old_end
        chunks.append(self.data[cursor:])
        return b"".join(chunks)

    def semantic_diff(
        self, other: "ParsedBGUI", allowed_font_ordinals: set[int]
    ) -> list[dict]:
        if len(self.text_records) != len(other.text_records):
            return [
                {
                    "kind": "text_record_count",
                    "before": len(self.text_records),
                    "after": len(other.text_records),
                }
            ]
        differences: list[dict] = []
        for before, after in zip(self.text_records, other.text_records):
            left = before.semantic()
            right = after.semantic()
            allowed = before.ordinal in allowed_font_ordinals
            if allowed:
                left = dict(left)
                right = dict(right)
                left.pop("font")
                right.pop("font")
            if left != right:
                differences.append(
                    {
                        "kind": "text_semantic",
                        "ordinal": before.ordinal,
                        "before": left,
                        "after": right,
                    }
                )
            elif not allowed and before.font != after.font:
                differences.append(
                    {
                        "kind": "unexpected_font",
                        "ordinal": before.ordinal,
                        "before": before.font,
                        "after": after.font,
                    }
                )
        if self.header != other.header:
            differences.append(
                {
                    "kind": "resource_header",
                    "before": dataclasses.asdict(self.header),
                    "after": dataclasses.asdict(other.header),
                }
            )
        return differences

    def summary(self) -> dict:
        fonts: dict[str, int] = {}
        for record in self.text_records:
            fonts[record.font] = fonts.get(record.font, 0) + 1
        return {
            "schema": "ams2-kr-005-bgui-parse-v1",
            "bytes": len(self.data),
            "sha256": sha256_bytes(self.data),
            "physical_coverage": {
                "resource_header": {
                    "scale": self.header.scale,
                    "resource_count": self.header.count,
                    "end_offset": f"0x{self.header.end_offset:X}",
                },
                "validated_text_style_records": len(self.text_records),
                "unknown_bytes_policy": (
                    "All non-font bytes, including unknown record/container fields and "
                    "trailing data, are retained verbatim by the serializer."
                ),
            },
            "font_inventory": dict(sorted(fonts.items(), key=lambda item: item[0].casefold())),
            "options_targets": [
                target_report(self, target) for target in self.targets
            ],
        }


def parse_resource_header(data: bytes) -> ResourceHeader:
    if len(data) < 8:
        raise BGUIError("BGUI is shorter than its fixed header")
    scale = _f32(data, 0)
    count = _u32(data, 4)
    if count > 4096:
        raise BGUIError(f"implausible resource count: {count}")
    cursor = 8
    entries: list[str] = []
    for index in range(count):
        if cursor >= len(data):
            raise BGUIError(f"truncated resource length for entry {index}")
        length = data[cursor]
        value = _decode_utf8(data, cursor + 1, length, f"resource[{index}]")
        if not value.lower().endswith(".bspr"):
            raise BGUIError(f"unexpected resource[{index}]: {value!r}")
        entries.append(value)
        cursor += 1 + length
    return ResourceHeader(scale=scale, count=count, entries=tuple(entries), end_offset=cursor)


def parse_text_records(data: bytes) -> list[TextRecord]:
    records: list[TextRecord] = []
    # Marker begins at record_start+4 (after the local-id u32).
    for marker_offset in _iter_find(data, TEXT_MARKER):
        start = marker_offset - 4
        if start < 0 or start + 83 > len(data):
            continue
        local_id = _u32(data, start)
        # References elsewhere in BGUI can contain the same name/hash pair.
        # A genuine Text style record has the demonstrated common geometry and
        # two consecutive length-prefixed strings at +0x49 and +0x52+text_len.
        if local_id > 0xFFFF:
            continue
        text_length_offset = start + 73
        text_length = data[text_length_offset]
        text_start = text_length_offset + 1
        text_end = text_start + text_length
        font_length_offset = start + 82 + text_length
        if text_end + 8 != font_length_offset or font_length_offset >= len(data):
            continue
        try:
            text_reference = _decode_utf8(
                data, text_start, text_length, "Text reference"
            )
        except BGUIError:
            continue
        font_length = data[font_length_offset]
        font_bytes_offset = font_length_offset + 1
        flags_offset = font_bytes_offset + font_length
        if flags_offset + 4 > len(data):
            continue
        try:
            font = _decode_utf8(data, font_bytes_offset, font_length, "font path")
        except BGUIError:
            continue
        if not font.lower().startswith("gui\\") or not font.lower().endswith(".bfont"):
            continue
        floats = tuple(_f32(data, start + 17 + 4 * index) for index in range(10))
        if not all(math.isfinite(value) and abs(value) <= 1.0e8 for value in floats):
            continue
        records.append(
            TextRecord(
                ordinal=len(records),
                start=start,
                local_id=local_id,
                name_hash=_u32(data, start + 9),
                object_id=_u32(data, start + 13),
                position=(floats[0], floats[1]),
                size=(floats[2], floats[3]),
                field_f32_2=(floats[4], floats[5]),
                clip_rect=(floats[6], floats[7], floats[8], floats[9]),
                alignment_style_raw=data[start + 57 : start + 69].hex().upper(),
                text_length_offset=text_length_offset,
                text_reference=text_reference,
                text_reference_hash=_u32(data, text_end),
                field_after_text_hash=_u32(data, text_end + 4),
                font_length_offset=font_length_offset,
                font_bytes_offset=font_bytes_offset,
                font=font,
                flags_offset=flags_offset,
                flags=_u32(data, flags_offset),
            )
        )
    return records


def _find_named_nodes(data: bytes, name: str) -> list[NamedNode]:
    encoded = name.encode("utf-8")
    if len(encoded) > 255:
        raise ValueError(name)
    marker = bytes((len(encoded),)) + encoded
    nodes: list[NamedNode] = []
    for name_offset in _iter_find(data, marker):
        start = name_offset - 4
        if start < 0:
            continue
        local_id = _u32(data, start)
        if local_id > 0xFFFF:
            continue
        after_name = name_offset + len(marker)
        if after_name + 24 > len(data):
            continue
        values = tuple(_f32(data, after_name + 8 + 4 * i) for i in range(4))
        if not all(math.isfinite(value) and abs(value) <= 1.0e8 for value in values):
            continue
        object_id = _u32(data, after_name + 4)
        if object_id == 0 or object_id > 1_000_000:
            continue
        nodes.append(
            NamedNode(
                start=start,
                local_id=local_id,
                name=name,
                name_hash=_u32(data, after_name),
                object_id=object_id,
                position=(values[0], values[1]),
                size=(values[2], values[3]),
            )
        )
    return nodes


def _last_at_or_before(values: list[int], offset: int) -> int | None:
    result = None
    for value in values:
        if value > offset:
            break
        result = value
    return result


def locate_options_targets(data: bytes, records: list[TextRecord]) -> list[OptionsTarget]:
    # Use complete named GUI nodes rather than every name/hash reference.  The
    # latter also occurs in per-record lookup tables (for example the adjacent
    # localization-category entry) and is not an Options container start.
    options_starts = sorted(node.start for node in _find_named_nodes(data, "Options"))
    selected_starts = sorted(offset - 4 for offset in _iter_find(data, SELECTED_MARKER))
    unselected_starts = sorted(
        offset - 4 for offset in _iter_find(data, UNSELECTED_MARKER)
    )
    settings_starts = sorted(offset - 4 for offset in _iter_find(data, SETTINGS_MARKER))
    layer_nodes = sorted(
        _find_named_nodes(data, "Layer_MainMenuAMS2")
        + _find_named_nodes(data, "Layer_DemoMenuNewLayer"),
        key=lambda node: node.start,
    )

    candidates: list[tuple[int, int, int, TextRecord]] = []
    for record in records:
        if record.flags != TARGET_FLAGS or record.text_reference:
            continue
        if record.position != (95.0, 10.0):
            continue
        if record.size[0] != 185.0 or record.size[1] not in (42.0, 43.0):
            continue
        settings = _last_at_or_before(settings_starts, record.start)
        if settings is None or not (0 < record.start - settings <= 0x100):
            continue
        states = [
            ("Selected", _last_at_or_before(selected_starts, record.start)),
            ("Unselected", _last_at_or_before(unselected_starts, record.start)),
        ]
        states = [(name, start) for name, start in states if start is not None]
        if not states:
            continue
        state_name, state_start = max(states, key=lambda item: int(item[1]))
        if not (0 < settings - int(state_start) <= 0x500):
            continue
        options = _last_at_or_before(options_starts, int(state_start))
        if options is None or not (0 < int(state_start) - options <= 0x1000):
            continue
        candidates.append((options, int(state_start), settings, record))

    grouped_options = sorted({item[0] for item in candidates})
    targets: list[OptionsTarget] = []
    for group, options_start in enumerate(grouped_options):
        layer = None
        for node in layer_nodes:
            if node.start <= options_start:
                layer = node.name
            else:
                break
        if layer is None:
            continue
        for option, state_start, settings_start, record in candidates:
            if option != options_start:
                continue
            state = (
                "Selected"
                if data[state_start + 4 :].startswith(SELECTED_MARKER)
                else "Unselected"
            )
            targets.append(
                OptionsTarget(
                    group=group,
                    layer=layer,
                    state=state,
                    options_start=options_start,
                    state_start=state_start,
                    settings_start=settings_start,
                    text_ordinal=record.ordinal,
                )
            )
    return sorted(targets, key=lambda item: (item.group, item.state != "Selected"))


def target_report(parsed: ParsedBGUI, target: OptionsTarget) -> dict:
    record = parsed.text_records[target.text_ordinal]
    source_bytes = record.text_reference.encode("utf-8")
    font_bytes = record.font.encode("utf-8")
    return {
        "record_path": target.record_path,
        "group": target.group,
        "layer": target.layer,
        "state": target.state,
        "record_start": f"0x{record.start:X}",
        "record_type": "Text",
        "local_id": record.local_id,
        "object_id": record.object_id,
        "name_hash": f"0x{record.name_hash:08X}",
        "text_reference": record.text_reference,
        "text_reference_length": len(source_bytes),
        "text_reference_hash": f"0x{record.text_reference_hash:08X}",
        "field_after_text_hash": f"0x{record.field_after_text_hash:08X}",
        "font": record.font,
        "font_length": len(font_bytes),
        "font_length_offset": f"0x{record.font_length_offset:X}",
        "font_bytes_offset": f"0x{record.font_bytes_offset:X}",
        "flags": f"0x{record.flags:08X}",
        "flags_offset": f"0x{record.flags_offset:X}",
        "position": record.position,
        "size": record.size,
        "field_f32_2_unknown": record.field_f32_2,
        "clip_rect": record.clip_rect,
        "alignment_style_raw_unknown": record.alignment_style_raw,
        "record_length": "UNKNOWN (no per-record byte-length field established)",
        "parent_container_length": (
            "UNKNOWN (no parent byte-length field established; serialization is "
            "consistent with field/count-delimited records)"
        ),
        "child_count": "UNKNOWN for parent; Text is treated as a leaf",
        "settings_start": f"0x{target.settings_start:X}",
        "state_start": f"0x{target.state_start:X}",
        "options_start": f"0x{target.options_start:X}",
    }


def _select_target_ordinals(parsed: ParsedBGUI, scope: str) -> set[int]:
    if scope == "poc-a":
        matches = [
            target
            for target in parsed.targets
            if target.layer == "Layer_MainMenuAMS2" and target.state == "Unselected"
        ]
        if len(matches) != 1:
            raise BGUIError(f"POC-A selector found {len(matches)} records")
        return {matches[0].text_ordinal}
    if scope == "poc-a-demo":
        matches = [
            target
            for target in parsed.targets
            if target.layer == "Layer_DemoMenuNewLayer"
            and target.state == "Unselected"
        ]
        if len(matches) != 1:
            raise BGUIError(f"POC-A demo selector found {len(matches)} records")
        return {matches[0].text_ordinal}
    if scope == "poc-a-demo-selected":
        matches = [
            target
            for target in parsed.targets
            if target.layer == "Layer_DemoMenuNewLayer"
            and target.state == "Selected"
        ]
        if len(matches) != 1:
            raise BGUIError(f"POC-A demo Selected selector found {len(matches)} records")
        return {matches[0].text_ordinal}
    if scope == "poc-b":
        if len(parsed.targets) != 4:
            raise BGUIError("POC-B requires exactly four structurally matched records")
        return {target.text_ordinal for target in parsed.targets}
    raise BGUIError(f"unsupported scope: {scope}")


def build_edit_report(
    before: ParsedBGUI,
    after: ParsedBGUI,
    target_ordinals: set[int],
    new_font: str,
    scope: str,
    *,
    dry_run: bool,
) -> dict:
    target_by_ordinal = {item.text_ordinal: item for item in before.targets}
    edits = []
    changed_ranges = []
    cumulative_delta = 0
    new_length = len(new_font.encode("utf-8"))
    for ordinal in sorted(target_ordinals):
        old = before.text_records[ordinal]
        new = after.text_records[ordinal]
        target = target_by_ordinal[ordinal]
        delta = new_length - len(old.font.encode("utf-8"))
        edits.append(
            {
                "record_path": target.record_path,
                "text_ordinal": ordinal,
                "object_id": old.object_id,
                "old_font": old.font,
                "new_font": new.font,
                "old_record_start": f"0x{old.start:X}",
                "new_record_start": f"0x{new.start:X}",
                "old_font_offset": f"0x{old.font_bytes_offset:X}",
                "new_font_offset": f"0x{new.font_bytes_offset:X}",
                "font_byte_delta": delta,
                "prior_cumulative_size_delta": cumulative_delta,
                "affected_parent_metadata": (
                    "none established; no record/container byte-size or absolute-offset "
                    "field was found in this validated Text path"
                ),
            }
        )
        old_field_end = old.font_bytes_offset + len(old.font.encode("utf-8"))
        new_field_end = new.font_bytes_offset + len(new.font.encode("utf-8"))
        changed_ranges.append(
            {
                "operation": "replace_length_prefixed_font_field",
                "record_path": target.record_path,
                "before": [
                    f"0x{old.font_length_offset:X}",
                    f"0x{old_field_end:X}",
                ],
                "after": [
                    f"0x{new.font_length_offset:X}",
                    f"0x{new_field_end:X}",
                ],
                "before_bytes": old_field_end - old.font_length_offset,
                "after_bytes": new_field_end - new.font_length_offset,
                "before_hex": before.data[old.font_length_offset:old_field_end]
                .hex()
                .upper(),
                "after_hex": after.data[new.font_length_offset:new_field_end]
                .hex()
                .upper(),
            }
        )
        cumulative_delta += delta
    semantic_differences = before.semantic_diff(after, target_ordinals)
    return {
        "schema": "ams2-kr-005-bgui-edit-v1",
        "scope": scope,
        "dry_run": dry_run,
        "before": {
            "bytes": len(before.data),
            "sha256": sha256_bytes(before.data),
            "text_records": len(before.text_records),
        },
        "after": {
            "bytes": len(after.data),
            "sha256": sha256_bytes(after.data),
            "text_records": len(after.text_records),
        },
        "size_delta": len(after.data) - len(before.data),
        "edits": edits,
        "other_record_semantic_changes": len(semantic_differences),
        "semantic_differences": semantic_differences,
        "changed_byte_ranges": changed_ranges,
        "strict_reparse": "PASS",
    }


def write_json(path: Path | None, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        print(text, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path)


def load_parsed(path: Path, *, require_original_sha: bool = False) -> ParsedBGUI:
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if require_original_sha and digest != EXPECTED_ORIGINAL_SHA256:
        raise BGUIError(
            f"original SHA-256 gate failed: expected {EXPECTED_ORIGINAL_SHA256}, got {digest}"
        )
    return ParsedBGUI.parse(data)


def command_inspect(args: argparse.Namespace) -> int:
    parsed = load_parsed(args.input, require_original_sha=args.require_original_sha)
    write_json(args.report, parsed.summary())
    return 0


def command_roundtrip(args: argparse.Namespace) -> int:
    before = load_parsed(args.input, require_original_sha=args.require_original_sha)
    output_data = before.serialize_fonts({})
    after = ParsedBGUI.parse(output_data)
    semantic = before.semantic_diff(after, set())
    identical = output_data == before.data
    report = {
        "schema": "ams2-kr-005-bgui-noop-v1",
        "input_sha256": sha256_bytes(before.data),
        "output_sha256": sha256_bytes(output_data),
        "input_bytes": len(before.data),
        "output_bytes": len(output_data),
        "byte_identical": identical,
        "semantic_differences": semantic,
        "text_records_before": len(before.text_records),
        "text_records_after": len(after.text_records),
    }
    if not identical or semantic:
        raise BGUIError(f"no-op round-trip failed: {report}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output_data)
    write_json(args.report, report)
    return 0


def _perform_edit(args: argparse.Namespace, *, dry_run: bool) -> int:
    before = load_parsed(args.input, require_original_sha=args.require_original_sha)
    ordinals = _select_target_ordinals(before, args.scope)
    for ordinal in ordinals:
        if before.text_records[ordinal].font != TARGET_OLD_FONT:
            raise BGUIError(
                f"target old-font gate failed at Text ordinal {ordinal}: "
                f"{before.text_records[ordinal].font!r}"
            )
    output_data = before.serialize_fonts({ordinal: args.font for ordinal in ordinals})
    after = ParsedBGUI.parse(output_data, strict_targets=False)
    differences = before.semantic_diff(after, ordinals)
    if differences:
        raise BGUIError(f"semantic diff outside allowed font fields: {differences[:3]}")
    for ordinal in ordinals:
        if after.text_records[ordinal].font != args.font:
            raise BGUIError(f"reparse did not retain new font at ordinal {ordinal}")
    report = build_edit_report(
        before, after, ordinals, args.font, args.scope, dry_run=dry_run
    )
    if not dry_run:
        if args.output is None:
            raise BGUIError("edit requires --output")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(output_data)
    write_json(args.report, report)
    return 0


def command_dry_run(args: argparse.Namespace) -> int:
    return _perform_edit(args, dry_run=True)


def command_edit(args: argparse.Namespace) -> int:
    return _perform_edit(args, dry_run=False)


def command_validate(args: argparse.Namespace) -> int:
    parsed = load_parsed(args.input, require_original_sha=args.require_original_sha)
    payload = parsed.summary()
    payload["validation"] = "PASS"
    write_json(args.report, payload)
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    def common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("input", type=Path)
        subparser.add_argument("--report", type=Path)
        subparser.add_argument("--require-original-sha", action="store_true")

    inspect_parser = subparsers.add_parser("inspect")
    common(inspect_parser)
    inspect_parser.set_defaults(function=command_inspect)

    validate_parser = subparsers.add_parser("validate")
    common(validate_parser)
    validate_parser.set_defaults(function=command_validate)

    roundtrip_parser = subparsers.add_parser("roundtrip")
    common(roundtrip_parser)
    roundtrip_parser.add_argument("output", type=Path)
    roundtrip_parser.set_defaults(function=command_roundtrip)

    for name, function in (("dry-run", command_dry_run), ("edit", command_edit)):
        edit_parser = subparsers.add_parser(name)
        common(edit_parser)
        edit_parser.add_argument(
            "--scope",
            choices=("poc-a", "poc-a-demo", "poc-a-demo-selected", "poc-b"),
            required=True,
        )
        edit_parser.add_argument("--font", required=True)
        if name == "edit":
            edit_parser.add_argument("--output", type=Path, required=True)
        else:
            edit_parser.set_defaults(output=None)
        edit_parser.set_defaults(function=function)
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    try:
        return int(args.function(args))
    except (BGUIError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
