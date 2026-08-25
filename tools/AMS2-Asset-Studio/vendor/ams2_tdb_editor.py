#!/usr/bin/env python3
"""Strict, offline-only AMS2 TDB parser, Korean writer, and validator.

The tool deliberately has no install command.  It reads the 11 loose game TDBs
and the four read-only TEXT.bff extractions, builds files only below an explicit
offline output directory, and fails closed on structural or translation-gate
errors.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import struct
import sys
from typing import Any, Iterable, Sequence


VERSION = "1.0.0"

EXPECTED_LANGUAGES = (
    "English",
    "French",
    "Italian",
    "German",
    "Spanish",
    "Russian",
    "Polish",
    "Japanese",
    "Brazilian-Portuguese",
    "Neutral-Spanish",
    "French-Canadian",
    "Korean",
    "Chinese-Simple",
    "Chinese-Traditional",
)

LOOSE_NAMES = (
    "career.tdb",
    "chatfilter.tdb",
    "drivers.tdb",
    "game.tdb",
    "general.tdb",
    "online.tdb",
    "pit.tdb",
    "platform.tdb",
    "presence.tdb",
    "rac.tdb",
    "vehicledetails.tdb",
)

EXTRACTED_NAMES = ("demo.tdb", "dlc.tdb", "reputation.tdb", "steam.tdb")

DEFAULT_GAME_DIR = Path(r"E:\SteamLibrary\steamapps\common\Automobilista 2")
DEFAULT_EXTRACTED_DIR = Path(
    r"E:\AMS2_Korean_Work\extracted\AMS2-KR-008\TEXT_BFF\text"
)

EXPLICIT_UNTRANSLATED_RE = re.compile(
    r"^UNTRANSLATED(?:\s*\(\d+\))?\s*:\s*.*$", re.IGNORECASE | re.DOTALL
)
EXPLICIT_UNTRANSLATED_CAPTURE_RE = re.compile(
    r"^UNTRANSLATED(?:\s*\((\d+)\))?\s*:\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

APPROVED_STATUSES = frozenset(
    {"APPROVED", "APPROVED_AUTO", "APPROVED_MANUAL", "READY", "TRANSLATED"}
)
IGNORED_STATUSES = frozenset(
    {"REVIEW_REQUIRED", "REVIEW", "EXCLUDED", "TODO", "DEFERRED", "SKIP"}
)


class TDBError(RuntimeError):
    """Base exception for all fail-closed parser/writer errors."""


class TranslationGateError(TDBError):
    """Raised when a requested translation does not pass the edit gate."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le", errors="strict")) // 2


def lp_utf8(value: str) -> bytes:
    encoded = value.encode("utf-8", errors="strict")
    if len(encoded) > 0xFFFFFFFF:
        raise TDBError("UTF-8 string is too large for a uint32 length")
    return struct.pack("<I", len(encoded)) + encoded


class Cursor:
    """Bounds-checked cursor over an immutable byte string."""

    def __init__(self, data: bytes, source: str):
        self.data = data
        self.source = source
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def exact(self, size: int) -> bytes:
        if size < 0 or size > self.remaining():
            raise TDBError(
                f"{self.source}: unexpected EOF at 0x{self.offset:X}; "
                f"wanted {size} bytes, have {self.remaining()}"
            )
        start = self.offset
        self.offset += size
        return self.data[start : self.offset]

    def u32(self) -> int:
        return struct.unpack("<I", self.exact(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.exact(8))[0]

    def lp_utf8(self, label: str) -> str:
        size = self.u32()
        try:
            value = self.exact(size).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TDBError(
                f"{self.source}: invalid UTF-8 in {label} at 0x{self.offset - size:X}"
            ) from exc
        if "\x00" in value:
            raise TDBError(f"{self.source}: embedded NUL in {label}")
        return value


@dataclass
class TDBLanguage:
    name: str
    hashes: list[int]
    values: list[str]
    original_block_size: int


@dataclass
class TDBDocument:
    source: str
    version: int
    database: str
    language_count: int
    group_count: int
    key_count: int
    group_string_bytes_with_nuls: int
    key_string_bytes_with_nuls: int
    max_language_value_bytes_with_nuls: int
    groups: list[str]
    keys: list[str]
    languages: list[TDBLanguage]

    def language(self, name: str) -> TDBLanguage:
        hits = [language for language in self.languages if language.name == name]
        if len(hits) != 1:
            raise TDBError(
                f"{self.source}: expected exactly one {name!r} language, got {len(hits)}"
            )
        return hits[0]


def _nul_counted_utf8(values: Iterable[str]) -> int:
    return sum(len(value.encode("utf-8", errors="strict")) + 1 for value in values)


def _language_value_bytes_with_nuls(language: TDBLanguage) -> int:
    """Exporter header measure: UTF-16LE bytes plus a 2-byte NUL per value."""

    return sum(
        len(value.encode("utf-16-le", errors="strict")) + 2
        for value in language.values
    )


def _max_language_value_bytes_with_nuls(languages: Sequence[TDBLanguage]) -> int:
    if not languages:
        raise TDBError("TDB has no language blocks")
    result = max(_language_value_bytes_with_nuls(language) for language in languages)
    if result > 0xFFFFFFFF:
        raise TDBError("maximum language value-byte total exceeds uint32")
    return result


def validate_document(
    document: TDBDocument, *, require_derived_header_match: bool = True
) -> None:
    """Validate invariants independent of a particular binary serialization."""

    source = document.source
    if document.version != 1:
        raise TDBError(f"{source}: unsupported TDB version {document.version}; expected 1")
    if document.language_count != len(document.languages):
        raise TDBError(f"{source}: language count field/list mismatch")
    if document.group_count != len(document.groups):
        raise TDBError(f"{source}: group count field/list mismatch")
    if document.key_count != len(document.keys):
        raise TDBError(f"{source}: key count field/list mismatch")
    if document.language_count != len(EXPECTED_LANGUAGES):
        raise TDBError(
            f"{source}: language count {document.language_count} != {len(EXPECTED_LANGUAGES)}"
        )
    names = tuple(language.name for language in document.languages)
    if names != EXPECTED_LANGUAGES:
        raise TDBError(f"{source}: language order mismatch: {names!r}")
    observed_group_bytes = _nul_counted_utf8(document.groups)
    if document.group_string_bytes_with_nuls != observed_group_bytes:
        raise TDBError(
            f"{source}: group byte count {document.group_string_bytes_with_nuls} "
            f"!= observed {observed_group_bytes}"
        )
    observed_key_bytes = _nul_counted_utf8(document.keys)
    if document.key_string_bytes_with_nuls != observed_key_bytes:
        raise TDBError(
            f"{source}: key byte count {document.key_string_bytes_with_nuls} "
            f"!= observed {observed_key_bytes}"
        )
    reference_hashes: list[int] | None = None
    for language in document.languages:
        if len(language.hashes) != document.key_count:
            raise TDBError(f"{source}/{language.name}: hash count mismatch")
        if len(language.values) != document.key_count:
            raise TDBError(f"{source}/{language.name}: value count mismatch")
        if reference_hashes is None:
            reference_hashes = language.hashes
        elif language.hashes != reference_hashes:
            raise TDBError(f"{source}/{language.name}: per-key hashes differ")
        for index, value in enumerate(language.values):
            if not isinstance(value, str):
                raise TDBError(f"{source}/{language.name}/{index}: non-string value")
            encoded = value.encode("utf-16-le", errors="strict")
            if len(encoded) // 2 > 0xFFFFFFFF:
                raise TDBError(f"{source}/{language.name}/{index}: value too large")
    if require_derived_header_match:
        observed_max = _max_language_value_bytes_with_nuls(document.languages)
        if document.max_language_value_bytes_with_nuls != observed_max:
            raise TDBError(
                f"{source}: maximum language value-byte header "
                f"{document.max_language_value_bytes_with_nuls} != observed {observed_max}"
            )


def parse_tdb_bytes(data: bytes, source: str = "<bytes>") -> TDBDocument:
    """Strictly parse a complete TDB byte stream and require exact EOF."""

    reader = Cursor(data, source)
    version = reader.u32()
    database = reader.lp_utf8("database")
    language_count = reader.u32()
    group_count = reader.u32()
    key_count = reader.u32()
    group_string_bytes_with_nuls = reader.u32()
    key_string_bytes_with_nuls = reader.u32()
    max_language_value_bytes_with_nuls = reader.u32()

    # Hard ceilings prevent corrupt counts from causing huge allocations or loops.
    if language_count > 64:
        raise TDBError(f"{source}: implausible language count {language_count}")
    if group_count > 1_000_000 or key_count > 10_000_000:
        raise TDBError(
            f"{source}: implausible group/key count {group_count}/{key_count}"
        )

    groups = [reader.lp_utf8(f"group[{index}]") for index in range(group_count)]
    keys = [reader.lp_utf8(f"key[{index}]") for index in range(key_count)]

    languages: list[TDBLanguage] = []
    reference_hashes: list[int] | None = None
    for language_index in range(language_count):
        name = reader.lp_utf8(f"language[{language_index}].name")
        block_size = reader.u32()
        block_start = reader.offset
        block_end = block_start + block_size
        if block_end > len(data):
            raise TDBError(
                f"{source}/{name}: block end 0x{block_end:X} exceeds EOF 0x{len(data):X}"
            )
        hashes: list[int] = []
        values: list[str] = []
        for record_index in range(key_count):
            if reader.offset + 12 > block_end:
                raise TDBError(f"{source}/{name}: truncated record {record_index}")
            record_hash = reader.u64()
            code_units = reader.u32()
            byte_count = code_units * 2
            if reader.offset + byte_count > block_end:
                raise TDBError(
                    f"{source}/{name}: value {record_index} exceeds declared block"
                )
            raw = reader.exact(byte_count)
            try:
                value = raw.decode("utf-16-le", errors="strict")
            except UnicodeDecodeError as exc:
                raise TDBError(
                    f"{source}/{name}: invalid UTF-16LE at record {record_index}"
                ) from exc
            if utf16_units(value) != code_units:
                raise TDBError(
                    f"{source}/{name}: UTF-16 unit mismatch at record {record_index}"
                )
            hashes.append(record_hash)
            values.append(value)
        if reader.offset != block_end:
            raise TDBError(
                f"{source}/{name}: block ended at 0x{reader.offset:X}, expected 0x{block_end:X}"
            )
        if reference_hashes is None:
            reference_hashes = hashes
        elif hashes != reference_hashes:
            raise TDBError(f"{source}/{name}: per-key hashes differ")
        languages.append(TDBLanguage(name, hashes, values, block_size))

    if reader.offset != len(data):
        raise TDBError(
            f"{source}: trailing bytes at 0x{reader.offset:X} ({len(data) - reader.offset})"
        )

    document = TDBDocument(
        source=source,
        version=version,
        database=database,
        language_count=language_count,
        group_count=group_count,
        key_count=key_count,
        group_string_bytes_with_nuls=group_string_bytes_with_nuls,
        key_string_bytes_with_nuls=key_string_bytes_with_nuls,
        max_language_value_bytes_with_nuls=max_language_value_bytes_with_nuls,
        groups=groups,
        keys=keys,
        languages=languages,
    )
    validate_document(document)
    return document


def parse_tdb(path: Path) -> TDBDocument:
    return parse_tdb_bytes(path.read_bytes(), str(path.resolve()))


def _language_block_bytes(language: TDBLanguage) -> bytes:
    output = bytearray()
    for record_hash, value in zip(language.hashes, language.values):
        encoded = value.encode("utf-16-le", errors="strict")
        units = len(encoded) // 2
        if units > 0xFFFFFFFF:
            raise TDBError(f"{language.name}: value exceeds uint32 UTF-16 unit count")
        output += struct.pack("<QI", record_hash, units)
        output += encoded
    if len(output) > 0xFFFFFFFF:
        raise TDBError(f"{language.name}: language block exceeds uint32 size")
    return bytes(output)


def serialize_tdb(document: TDBDocument) -> bytes:
    """Serialize a document, recomputing all known counts and block sizes."""

    # The writer accepts a document whose Korean values were edited in memory;
    # the derived maximum may therefore still contain the parsed source value.
    validate_document(document, require_derived_header_match=False)
    group_bytes = _nul_counted_utf8(document.groups)
    key_bytes = _nul_counted_utf8(document.keys)
    max_language_value_bytes = _max_language_value_bytes_with_nuls(document.languages)
    output = bytearray()
    output += struct.pack("<I", document.version)
    output += lp_utf8(document.database)
    output += struct.pack(
        "<IIIIII",
        len(document.languages),
        len(document.groups),
        len(document.keys),
        group_bytes,
        key_bytes,
        max_language_value_bytes,
    )
    for group in document.groups:
        output += lp_utf8(group)
    for key in document.keys:
        output += lp_utf8(key)
    for language in document.languages:
        block = _language_block_bytes(language)
        output += lp_utf8(language.name)
        output += struct.pack("<I", len(block))
        output += block
    return bytes(output)


def first_difference(before: bytes, after: bytes) -> int | None:
    for index, (left, right) in enumerate(zip(before, after)):
        if left != right:
            return index
    if len(before) != len(after):
        return min(len(before), len(after))
    return None


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    start: int
    end: int

    def compact(self) -> dict[str, Any]:
        return {"kind": self.kind, "text": self.text, "start": self.start, "end": self.end}


# Ordered most-specific-first.  The fallback scanner below also protects bare
# metacharacters so an unfamiliar source construct cannot silently disappear.
TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ESCAPED_PERCENT", re.compile(r"%%")),
    (
        "PRINTF",
        re.compile(
            # Deliberately exclude the legal-but-ambiguous C "space" flag.
            # Without this, ordinary prose such as "75% or higher" is falsely
            # tokenized as the printf sequence "% o".  A bare percent remains
            # protected by PERCENT_LITERAL, so an unfamiliar construct still
            # cannot silently disappear.
            r"%(?:\d+\$)?[-+#0']*\d*(?:\.\d+)?(?:hh|h|ll|l|j|z|t|L)?[diuoxXfFeEgGaAcspn]"
        ),
    ),
    ("PERCENT_NAMED", re.compile(r"%[A-Za-z_][A-Za-z0-9_.:\-]*%")),
    ("PERCENT_POSITIONAL", re.compile(r"%\d+")),
    ("DOLLAR_BRACED", re.compile(r"\$\{[^{}\r\n]+\}")),
    ("DOLLAR_NAMED", re.compile(r"\$[A-Za-z_][A-Za-z0-9_.:\-]*\$")),
    ("BRACED", re.compile(r"\{[^{}\r\n]+\}")),
    ("ANGLE", re.compile(r"<[^<>\r\n]+>")),
    ("SQUARE_TOKEN", re.compile(r"\[[A-Z0-9][A-Z0-9_.:/+\- ]*\]")),
    ("BACKSLASH_ESCAPE", re.compile(r"\\(?:[nrt\\]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8})")),
)

FALLBACK_META = {
    "%": "PERCENT_LITERAL",
    "{": "OPEN_BRACE_LITERAL",
    "}": "CLOSE_BRACE_LITERAL",
    "<": "OPEN_ANGLE_LITERAL",
    ">": "CLOSE_ANGLE_LITERAL",
    "$": "DOLLAR_LITERAL",
    "\\": "BACKSLASH_LITERAL",
}


def extract_tokens(value: str) -> list[Token]:
    """Extract protected format/markup/control tokens in source order."""

    results: list[Token] = []
    index = 0
    while index < len(value):
        if value.startswith("\r\n", index):
            results.append(Token("NEWLINE_CRLF", "\r\n", index, index + 2))
            index += 2
            continue
        if value[index] == "\n":
            results.append(Token("NEWLINE_LF", "\n", index, index + 1))
            index += 1
            continue
        if value[index] == "\r":
            results.append(Token("NEWLINE_CR", "\r", index, index + 1))
            index += 1
            continue
        if value[index] == "\t":
            results.append(Token("TAB", "\t", index, index + 1))
            index += 1
            continue
        matched = False
        for kind, pattern in TOKEN_PATTERNS:
            match = pattern.match(value, index)
            if match is None:
                continue
            results.append(Token(kind, match.group(0), index, match.end()))
            index = match.end()
            matched = True
            break
        if matched:
            continue
        kind = FALLBACK_META.get(value[index])
        if kind is not None:
            results.append(Token(kind, value[index], index, index + 1))
        elif ord(value[index]) < 0x20:
            results.append(Token("CONTROL_CHAR", value[index], index, index + 1))
        index += 1
    return results


def token_signature(value: str) -> list[tuple[str, str]]:
    return [(token.kind, token.text) for token in extract_tokens(value)]


ANGLE_TAG_RE = re.compile(
    r"^<\s*(?P<close>/)?\s*(?P<name>[A-Za-z][A-Za-z0-9_.:\-]*)[^<>]*(?P<self>/)?>$"
)


def markup_balance(tokens: Sequence[Token]) -> dict[str, Any]:
    """Report XML-like tag balance without assuming unpaired angle tokens are tags."""

    parsed: list[tuple[Token, re.Match[str]]] = []
    closing_names: set[str] = set()
    for token in tokens:
        if token.kind != "ANGLE":
            continue
        match = ANGLE_TAG_RE.match(token.text)
        if match is not None:
            parsed.append((token, match))
            if match.group("close"):
                closing_names.add(match.group("name").casefold())
    stack: list[str] = []
    issues: list[dict[str, Any]] = []
    for token, match in parsed:
        name = match.group("name")
        folded = name.casefold()
        # An all-caps singleton such as <BRAKE> is commonly a game variable.
        # Only treat a name as paired markup when a closing form exists.
        if folded not in closing_names:
            continue
        if match.group("self"):
            continue
        if match.group("close"):
            if not stack or stack[-1] != folded:
                issues.append({"kind": "UNEXPECTED_CLOSE", "tag": token.text})
            else:
                stack.pop()
        else:
            stack.append(folded)
    for name in reversed(stack):
        issues.append({"kind": "UNCLOSED_TAG", "name": name})
    return {"balanced": not issues, "issues": issues}


def validate_token_preservation(english: str, korean: str) -> dict[str, Any]:
    """Fail-closed token gate for one proposed English -> Korean translation."""

    source_tokens = extract_tokens(english)
    target_tokens = extract_tokens(korean)
    source_signature = [(item.kind, item.text) for item in source_tokens]
    target_signature = [(item.kind, item.text) for item in target_tokens]
    issues: list[dict[str, Any]] = []
    if source_signature != target_signature:
        issues.append(
            {
                "kind": "TOKEN_SEQUENCE_MISMATCH",
                "expected": source_signature,
                "observed": target_signature,
            }
        )
    source_markup = markup_balance(source_tokens)
    target_markup = markup_balance(target_tokens)
    if source_markup["balanced"] and not target_markup["balanced"]:
        issues.append({"kind": "TARGET_MARKUP_UNBALANCED", "detail": target_markup})
    return {
        "status": "PASS" if not issues else "BLOCK",
        "source_tokens": [item.compact() for item in source_tokens],
        "target_tokens": [item.compact() for item in target_tokens],
        "source_markup": source_markup,
        "target_markup": target_markup,
        "issues": issues,
    }


def source_specs(game_dir: Path, extracted_dir: Path) -> list[dict[str, Any]]:
    game_dir = game_dir.resolve()
    extracted_dir = extracted_dir.resolve()
    if not game_dir.is_dir():
        raise TDBError(f"game directory missing: {game_dir}")
    if not extracted_dir.is_dir():
        raise TDBError(f"extracted TEXT directory missing: {extracted_dir}")
    specs: list[dict[str, Any]] = []
    for name in LOOSE_NAMES:
        path = game_dir / "text" / name
        if not path.is_file():
            raise TDBError(f"loose TDB missing: {path}")
        specs.append({"name": name, "path": path, "source_kind": "LOOSE_GAME_FILE"})
    for name in EXTRACTED_NAMES:
        path = extracted_dir / name
        if not path.is_file():
            raise TDBError(f"extracted TDB missing: {path}")
        specs.append(
            {"name": name, "path": path, "source_kind": "TEXT_BFF_EXTRACTED_READ_ONLY"}
        )
    if len(specs) != 15 or len({row["name"].casefold() for row in specs}) != 15:
        raise TDBError("source set is not exactly 15 unique expected TDB files")
    return specs


def load_documents(game_dir: Path, extracted_dir: Path) -> tuple[list[dict[str, Any]], dict[str, TDBDocument]]:
    specs = source_specs(game_dir, extracted_dir)
    documents: dict[str, TDBDocument] = {}
    for spec in specs:
        document = parse_tdb(spec["path"])
        documents[spec["name"].casefold()] = document
    return specs, documents


def document_summary(document: TDBDocument) -> dict[str, Any]:
    return {
        "version": document.version,
        "database": document.database,
        "language_count": document.language_count,
        "group_count": document.group_count,
        "key_count": document.key_count,
        "group_string_bytes_with_nuls": document.group_string_bytes_with_nuls,
        "key_string_bytes_with_nuls": document.key_string_bytes_with_nuls,
        "max_language_value_bytes_with_nuls": document.max_language_value_bytes_with_nuls,
        "language_order": [language.name for language in document.languages],
        "language_block_sizes": {
            language.name: language.original_block_size for language in document.languages
        },
    }


def resolve_group(document: TDBDocument, key: str) -> dict[str, Any]:
    """Resolve a key against the serialized group names without inventing a group.

    TDB stores the group-name list but no per-key group index.  Current AMS2 keys
    encode the relationship as either ``Database_Group_...`` or ``Group_...``.
    Longest-prefix matching is deterministic and avoids a short group stealing a
    key from a more-specific group.
    """

    candidates: list[dict[str, Any]] = []
    folded_key = key.casefold()
    for group in document.groups:
        for form, prefix in (
            ("DATABASE_GROUP_PREFIX", f"{document.database}_{group}"),
            ("GROUP_PREFIX", group),
        ):
            folded_prefix = prefix.casefold()
            if folded_key == folded_prefix or folded_key.startswith(folded_prefix + "_"):
                candidates.append(
                    {
                        "group": group,
                        "form": form,
                        "prefix": prefix,
                        "prefix_length": len(prefix),
                    }
                )
    if not candidates:
        return {
            "status": "UNRESOLVED",
            "group": None,
            "matched_prefix": None,
            "match_form": None,
            "candidates": [],
        }
    longest = max(row["prefix_length"] for row in candidates)
    winners = [row for row in candidates if row["prefix_length"] == longest]
    unique_groups = {row["group"] for row in winners}
    if len(unique_groups) != 1:
        return {
            "status": "AMBIGUOUS",
            "group": None,
            "matched_prefix": None,
            "match_form": None,
            "candidates": winners,
        }
    winner = winners[0]
    return {
        "status": "RESOLVED_LONGEST_PREFIX",
        "group": winner["group"],
        "matched_prefix": winner["prefix"],
        "match_form": winner["form"],
        "candidates": winners,
    }


def newline_inventory(value: str) -> dict[str, Any]:
    tokens = extract_tokens(value)
    actual = [
        token
        for token in tokens
        if token.kind in {"NEWLINE_CRLF", "NEWLINE_LF", "NEWLINE_CR"}
    ]
    literal = [
        token
        for token in tokens
        if token.kind == "BACKSLASH_ESCAPE" and token.text in {r"\n", r"\r"}
    ]
    counts = Counter(token.kind for token in actual)
    return {
        "actual_sequence": [token.kind for token in actual],
        "actual_count": len(actual),
        "actual_counts": dict(sorted(counts.items())),
        "literal_escape_sequence": [token.text for token in literal],
        "literal_escape_count": len(literal),
        "line_count": len(actual) + 1,
        "starts_with_actual_newline": bool(actual and actual[0].start == 0),
        "ends_with_actual_newline": bool(actual and actual[-1].end == len(value)),
    }


def value_inventory(value: str) -> dict[str, Any]:
    tokens = extract_tokens(value)
    return {
        "value": value,
        "tokens": [token.compact() for token in tokens],
        "token_signature": [[token.kind, token.text] for token in tokens],
        "newline": newline_inventory(value),
        "length": {
            "characters": len(value),
            "utf8_bytes": len(value.encode("utf-8", errors="strict")),
            "utf16_code_units": utf16_units(value),
            "utf16le_bytes": len(value.encode("utf-16-le", errors="strict")),
        },
    }


def _text_bff_detail(text_bff: Path | None) -> dict[str, Any] | None:
    if text_bff is None:
        return None
    resolved = text_bff.resolve()
    if not resolved.is_file():
        raise TDBError(f"TEXT.bff missing: {resolved}")
    return {
        "path": str(resolved),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
        "access": "READ_ONLY",
    }


def build_untranslated_inventory(
    specs: Sequence[dict[str, Any]],
    documents: dict[str, TDBDocument],
    text_bff: Path | None = None,
) -> dict[str, Any]:
    """Build the explicit-marker-only inventory with all 14 language values."""

    container = _text_bff_detail(text_bff)
    rows: list[dict[str, Any]] = []
    per_tdb: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    resolved_count = 0
    ambiguous_count = 0
    unresolved_count = 0

    for spec in specs:
        name = spec["name"]
        path: Path = spec["path"]
        document = documents[name.casefold()]
        source = {
            "path": str(path.resolve()),
            "source_kind": spec["source_kind"],
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "container": (
                container if spec["source_kind"] == "TEXT_BFF_EXTRACTED_READ_ONLY" else None
            ),
        }
        provenance.append(
            {
                "tdb": name,
                "database": document.database,
                "key_count": document.key_count,
                "language_count": document.language_count,
                "source": source,
            }
        )
        korean = document.language("Korean")
        english = document.language("English")
        file_count = 0
        for index, current_korean in enumerate(korean.values):
            marker = EXPLICIT_UNTRANSLATED_CAPTURE_RE.match(current_korean)
            if marker is None:
                continue
            file_count += 1
            key = document.keys[index]
            group = resolve_group(document, key)
            if group["status"] == "RESOLVED_LONGEST_PREFIX":
                resolved_count += 1
            elif group["status"] == "AMBIGUOUS":
                ambiguous_count += 1
            else:
                unresolved_count += 1
            language_rows: dict[str, Any] = {}
            for language in document.languages:
                language_rows[language.name] = value_inventory(language.values[index])
            english_analysis = language_rows["English"]
            korean_analysis = language_rows["Korean"]
            rows.append(
                {
                    "tdb": name,
                    "database": document.database,
                    "group": group["group"],
                    "group_resolution": group,
                    "index": index,
                    "key": key,
                    "hash": f"0x{english.hashes[index]:016X}",
                    "english": english.values[index],
                    "current_korean": current_korean,
                    "explicit_untranslated": True,
                    "marker_number": int(marker.group(1)) if marker.group(1) else None,
                    "marker_target": marker.group(2),
                    "tokens": {
                        "english": english_analysis["tokens"],
                        "current_korean": korean_analysis["tokens"],
                        "ordered_signature_match": (
                            english_analysis["token_signature"]
                            == korean_analysis["token_signature"]
                        ),
                    },
                    "newline": {
                        "english": english_analysis["newline"],
                        "current_korean": korean_analysis["newline"],
                    },
                    "length": {
                        "english": english_analysis["length"],
                        "current_korean": korean_analysis["length"],
                    },
                    "context": {
                        "label": (
                            f"{document.database}/{group['group']}"
                            if group["group"] is not None
                            else document.database
                        ),
                        "basis": "TDB database plus serialized group-name longest-prefix match",
                        "confidence": (
                            "STRUCTURAL"
                            if group["status"] == "RESOLVED_LONGEST_PREFIX"
                            else "REVIEW"
                        ),
                        "runtime_bgui_location_verified": False,
                    },
                    "languages": language_rows,
                    "source": source,
                }
            )
        per_tdb.append(
            {
                "tdb": name,
                "database": document.database,
                "source_kind": spec["source_kind"],
                "key_count": document.key_count,
                "explicit_untranslated_count": file_count,
                "source_path": source["path"],
                "source_bytes": source["bytes"],
                "source_sha256": source["sha256"],
                "container": source["container"],
            }
        )

    extracted_count = sum(
        row["explicit_untranslated_count"]
        for row in per_tdb
        if row["source_kind"] == "TEXT_BFF_EXTRACTED_READ_ONLY"
    )
    language_slugs = {
        name: re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
        for name in EXPECTED_LANGUAGES
    }
    return {
        "schema": "ams2-kr010-untranslated-inventory-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "PASS",
        "read_only": True,
        "selection_rule": r"case-insensitive ^UNTRANSLATED(?:\s*\((\d+)\))?\s*:\s*(.*)$ on the Korean value",
        "explicit_markers_only": True,
        "tdb_count": len(per_tdb),
        "language_count": len(EXPECTED_LANGUAGES),
        "expected_language_order": list(EXPECTED_LANGUAGES),
        "record_count": len(rows),
        "loose_tdb_marker_count": len(rows) - extracted_count,
        "text_bff_extracted_marker_count": extracted_count,
        "group_resolution": {
            "resolved_longest_prefix": resolved_count,
            "ambiguous": ambiguous_count,
            "unresolved": unresolved_count,
            "policy": "No per-key group index exists in TDB; resolve only against serialized group names by deterministic longest prefix, otherwise retain null and REVIEW.",
        },
        "csv_language_column_slugs": language_slugs,
        "per_tdb": per_tdb,
        "source_provenance": provenance,
        "records": rows,
    }


def untranslated_inventory_csv_text(inventory: dict[str, Any]) -> str:
    base_fields = [
        "tdb",
        "database",
        "group",
        "group_resolution_status",
        "group_match_form",
        "group_matched_prefix",
        "index",
        "key",
        "hash",
        "english",
        "current_korean",
        "explicit_untranslated",
        "marker_number",
        "marker_target",
        "context",
        "context_basis",
        "context_confidence",
        "runtime_bgui_location_verified",
        "english_tokens_json",
        "current_korean_tokens_json",
        "ordered_token_signature_match",
        "english_newline_json",
        "current_korean_newline_json",
        "english_characters",
        "english_utf8_bytes",
        "english_utf16_code_units",
        "current_korean_characters",
        "current_korean_utf8_bytes",
        "current_korean_utf16_code_units",
        "source_kind",
        "source_path",
        "source_bytes",
        "source_sha256",
        "container_path",
        "container_sha256",
    ]
    language_fields: list[str] = []
    slugs = inventory["csv_language_column_slugs"]
    for language in EXPECTED_LANGUAGES:
        prefix = f"language_{slugs[language]}"
        language_fields.extend(
            [
                f"{prefix}_value",
                f"{prefix}_tokens_json",
                f"{prefix}_newline_json",
                f"{prefix}_characters",
                f"{prefix}_utf8_bytes",
                f"{prefix}_utf16_code_units",
            ]
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=base_fields + language_fields,
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for record in inventory["records"]:
        group = record["group_resolution"]
        context = record["context"]
        source = record["source"]
        container = source.get("container") or {}
        english_length = record["length"]["english"]
        korean_length = record["length"]["current_korean"]
        row: dict[str, Any] = {
            "tdb": record["tdb"],
            "database": record["database"],
            "group": record["group"],
            "group_resolution_status": group["status"],
            "group_match_form": group["match_form"],
            "group_matched_prefix": group["matched_prefix"],
            "index": record["index"],
            "key": record["key"],
            "hash": record["hash"],
            "english": record["english"],
            "current_korean": record["current_korean"],
            "explicit_untranslated": str(record["explicit_untranslated"]).lower(),
            "marker_number": record["marker_number"],
            "marker_target": record["marker_target"],
            "context": context["label"],
            "context_basis": context["basis"],
            "context_confidence": context["confidence"],
            "runtime_bgui_location_verified": str(
                context["runtime_bgui_location_verified"]
            ).lower(),
            "english_tokens_json": json.dumps(
                record["tokens"]["english"], ensure_ascii=False, separators=(",", ":")
            ),
            "current_korean_tokens_json": json.dumps(
                record["tokens"]["current_korean"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "ordered_token_signature_match": str(
                record["tokens"]["ordered_signature_match"]
            ).lower(),
            "english_newline_json": json.dumps(
                record["newline"]["english"], ensure_ascii=False, separators=(",", ":")
            ),
            "current_korean_newline_json": json.dumps(
                record["newline"]["current_korean"],
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "english_characters": english_length["characters"],
            "english_utf8_bytes": english_length["utf8_bytes"],
            "english_utf16_code_units": english_length["utf16_code_units"],
            "current_korean_characters": korean_length["characters"],
            "current_korean_utf8_bytes": korean_length["utf8_bytes"],
            "current_korean_utf16_code_units": korean_length["utf16_code_units"],
            "source_kind": source["source_kind"],
            "source_path": source["path"],
            "source_bytes": source["bytes"],
            "source_sha256": source["sha256"],
            "container_path": container.get("path"),
            "container_sha256": container.get("sha256"),
        }
        for language in EXPECTED_LANGUAGES:
            prefix = f"language_{slugs[language]}"
            analysis = record["languages"][language]
            row[f"{prefix}_value"] = analysis["value"]
            row[f"{prefix}_tokens_json"] = json.dumps(
                analysis["tokens"], ensure_ascii=False, separators=(",", ":")
            )
            row[f"{prefix}_newline_json"] = json.dumps(
                analysis["newline"], ensure_ascii=False, separators=(",", ":")
            )
            row[f"{prefix}_characters"] = analysis["length"]["characters"]
            row[f"{prefix}_utf8_bytes"] = analysis["length"]["utf8_bytes"]
            row[f"{prefix}_utf16_code_units"] = analysis["length"][
                "utf16_code_units"
            ]
        writer.writerow(row)
    return stream.getvalue()


def analyze_roundtrip_and_tokens(
    game_dir: Path, extracted_dir: Path, text_bff: Path | None = None
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    specs, documents = load_documents(game_dir, extracted_dir)
    roundtrip_files: list[dict[str, Any]] = []
    kind_counts: Counter[str] = Counter()
    distinct_by_kind: dict[str, set[str]] = defaultdict(set)
    examples_by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    occurrences: list[dict[str, Any]] = []
    per_file_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_language_counts: dict[str, Counter[str]] = defaultdict(Counter)
    baseline_pairs_checked = 0
    baseline_pair_mismatches: list[dict[str, Any]] = []
    total_values_scanned = 0
    total_records = 0

    for spec in specs:
        path: Path = spec["path"]
        name: str = spec["name"]
        original = path.read_bytes()
        document = documents[name.casefold()]
        serialized = serialize_tdb(document)
        reparsed = parse_tdb_bytes(serialized, f"{path}#roundtrip")
        serialized_again = serialize_tdb(reparsed)
        identical = original == serialized == serialized_again
        roundtrip_files.append(
            {
                "tdb": name,
                "path": str(path.resolve()),
                "source_kind": spec["source_kind"],
                "source_bytes": len(original),
                "source_sha256": sha256_bytes(original),
                "serialized_bytes": len(serialized),
                "serialized_sha256": sha256_bytes(serialized),
                "byte_identical": identical,
                "first_difference_offset": first_difference(original, serialized),
                "strict_eof_reparse": "PASS",
                "second_serialize_identical": serialized == serialized_again,
                "metadata": document_summary(document),
            }
        )
        total_records += document.key_count
        english = document.language("English")
        korean = document.language("Korean")
        for language in document.languages:
            for index, value in enumerate(language.values):
                total_values_scanned += 1
                tokens = extract_tokens(value)
                if not tokens:
                    continue
                compact = [token.compact() for token in tokens]
                occurrences.append(
                    {
                        "tdb": name,
                        "database": document.database,
                        "index": index,
                        "key": document.keys[index],
                        "hash": f"0x{language.hashes[index]:016X}",
                        "language": language.name,
                        "tokens": compact,
                    }
                )
                for token in tokens:
                    kind_counts[token.kind] += 1
                    distinct_by_kind[token.kind].add(token.text)
                    per_file_counts[name][token.kind] += 1
                    per_language_counts[language.name][token.kind] += 1
                    examples = examples_by_kind[token.kind]
                    if len(examples) < 20 and not any(
                        row["text"] == token.text for row in examples
                    ):
                        examples.append(
                            {
                                "text": token.text,
                                "tdb": name,
                                "language": language.name,
                                "index": index,
                                "key": document.keys[index],
                            }
                        )
        for index, (english_value, korean_value) in enumerate(
            zip(english.values, korean.values)
        ):
            if not extract_tokens(english_value) and not extract_tokens(korean_value):
                continue
            baseline_pairs_checked += 1
            gate = validate_token_preservation(english_value, korean_value)
            if gate["status"] != "PASS":
                baseline_pair_mismatches.append(
                    {
                        "tdb": name,
                        "database": document.database,
                        "index": index,
                        "key": document.keys[index],
                        "hash": f"0x{english.hashes[index]:016X}",
                        "english": english_value,
                        "current_korean": korean_value,
                        "gate": gate,
                        "classification": "PREEXISTING_BASELINE_ONLY_NOT_A_WRITER_EDIT",
                    }
                )

    all_roundtrips = all(row["byte_identical"] for row in roundtrip_files)
    text_bff_detail: dict[str, Any] | None = None
    if text_bff is not None:
        resolved_bff = text_bff.resolve()
        if not resolved_bff.is_file():
            raise TDBError(f"TEXT.bff missing: {resolved_bff}")
        text_bff_detail = {
            "path": str(resolved_bff),
            "bytes": resolved_bff.stat().st_size,
            "sha256": sha256_file(resolved_bff),
            "note": "container read only; no extraction or repack performed",
        }

    roundtrip = {
        "schema": "ams2-kr010-tdb-roundtrip-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "PASS" if all_roundtrips and len(roundtrip_files) == 15 else "BLOCK",
        "read_only": True,
        "expected_tdb_count": 15,
        "tdb_count": len(roundtrip_files),
        "byte_identical_count": sum(row["byte_identical"] for row in roundtrip_files),
        "strict_eof_reparse_count": sum(
            row["strict_eof_reparse"] == "PASS" for row in roundtrip_files
        ),
        "total_record_count": total_records,
        "text_bff": text_bff_detail,
        "files": roundtrip_files,
        "writer_contract": {
            "editable_field": "Korean language value only",
            "recomputed": [
                "UTF-16 code-unit count",
                "language block byte size",
                "maximum language UTF-16LE value bytes including per-value NULs",
            ],
            "preserved": [
                "version",
                "database",
                "groups",
                "keys",
                "key hashes",
                "language order",
                "all non-Korean values",
            ],
            "derived_header_formula": "max over languages of sum(UTF-16LE value bytes + 2-byte NUL per record)",
        },
    }
    kinds = {}
    for kind in sorted(kind_counts):
        kinds[kind] = {
            "occurrence_count": kind_counts[kind],
            "distinct_count": len(distinct_by_kind[kind]),
            "examples": examples_by_kind[kind],
        }
    inventory = {
        "schema": "ams2-kr010-token-inventory-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "PASS",
        "read_only": True,
        "tdb_count": len(roundtrip_files),
        "total_record_count": total_records,
        "total_language_values_scanned": total_values_scanned,
        "token_bearing_value_count": len(occurrences),
        "token_occurrence_count": sum(kind_counts.values()),
        "kinds": kinds,
        "per_tdb": {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(per_file_counts.items())
        },
        "per_language": {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(per_language_counts.items())
        },
        "occurrences": occurrences,
        "scanner_policy": {
            "ordered_exact_signature": True,
            "fallback_metacharacters_protected": sorted(FALLBACK_META),
            "note": "Bare format-like metacharacters are protected when no known token pattern matches; builds therefore fail closed for unfamiliar constructs.",
        },
    }
    baseline = {
        "schema": "ams2-kr010-placeholder-validation-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "BASELINE_INVENTORY",
        "apply_gate_status": "NOT_APPLICABLE_NO_PROPOSED_TRANSLATIONS",
        "translations_checked": 0,
        "translations_blocked": 0,
        "baseline_english_korean_pairs_with_tokens": baseline_pairs_checked,
        "preexisting_baseline_mismatch_count": len(baseline_pair_mismatches),
        "preexisting_baseline_mismatches": baseline_pair_mismatches,
        "gate": {
            "comparison": "exact ordered (token kind, token text) sequence",
            "protects": [
                "printf placeholders and escaped percent",
                "percent positional/named variables",
                "brace, dollar, angle, and uppercase square constructs",
                "backslash escapes",
                "CRLF/LF/CR and tab controls",
                "unrecognized bare token metacharacters",
            ],
            "failure_action": "BLOCK entire validate/build operation",
            "baseline_note": "Existing mismatches are inventory only; every newly selected translation is independently gated against English.",
        },
        "results": [],
    }
    writer_mutation_files: list[dict[str, Any]] = []
    for spec in specs:
        name = spec["name"]
        document = documents[name.casefold()]
        english = document.language("English")
        korean = document.language("Korean")
        candidate_index: int | None = None
        for index, (english_value, korean_value) in enumerate(
            zip(english.values, korean.values)
        ):
            if (
                not extract_tokens(english_value)
                and not extract_tokens(korean_value)
                and not EXPLICIT_UNTRANSLATED_RE.match(korean_value)
            ):
                candidate_index = index
                break
        if candidate_index is None:
            raise TDBError(f"{name}: no token-free record available for in-memory writer POC")
        index = candidate_index
        synthetic_value = korean.values[index] + "가"
        synthetic_row = {
            "tdb": name,
            "database": document.database,
            "index": index,
            "key": document.keys[index],
            "hash": f"0x{english.hashes[index]:016X}",
            "english": english.values[index],
            "old_korean": korean.values[index],
            "new_korean": synthetic_value,
            "status": "APPROVED_AUTO",
            "tokens": [],
        }
        gate, prepared = validate_translation_rows(
            {name.casefold(): document}, [synthetic_row]
        )
        if gate["status"] != "PASS":
            raise TDBError(f"{name}: in-memory writer POC source/token gate blocked")
        after = copy.deepcopy(document)
        after.language("Korean").values[index] = synthetic_value
        patched = serialize_tdb(after)
        reparsed = parse_tdb_bytes(patched, f"{spec['path']}#synthetic-writer-poc")
        stable = patched == serialize_tdb(reparsed)
        diff = semantic_diff(document, reparsed, prepared[name.casefold()])
        if not stable or diff["status"] != "PASS":
            raise TDBError(f"{name}: in-memory writer POC semantic/reparse gate blocked")
        original = spec["path"].read_bytes()
        writer_mutation_files.append(
            {
                "tdb": name,
                "source_kind": spec["source_kind"],
                "source_path": str(spec["path"].resolve()),
                "source_sha256": sha256_bytes(original),
                "synthetic_output_sha256": sha256_bytes(patched),
                "source_bytes": len(original),
                "synthetic_output_bytes": len(patched),
                "record": {
                    "index": index,
                    "key": document.keys[index],
                    "hash": f"0x{english.hashes[index]:016X}",
                    "old_utf16_units": utf16_units(korean.values[index]),
                    "synthetic_utf16_units": utf16_units(synthetic_value),
                },
                "korean_block_bytes_before": document.language("Korean").original_block_size,
                "korean_block_bytes_after": len(_language_block_bytes(reparsed.language("Korean"))),
                "source_and_token_gate": "PASS",
                "strict_eof_reparse": "PASS",
                "second_serialize_identical": stable,
                "semantic_diff": diff,
                "binary_persisted": False,
            }
        )
    writer_mutation = {
        "schema": "ams2-kr010-tdb-writer-mutation-validation-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": (
            "PASS"
            if len(writer_mutation_files) == 15
            and all(row["semantic_diff"]["status"] == "PASS" for row in writer_mutation_files)
            else "BLOCK"
        ),
        "scope": "one synthetic token-free Korean value length mutation per current TDB, entirely in memory",
        "warning": "Synthetic strings are writer test vectors, not translations and not shipping payloads.",
        "tdb_count": len(writer_mutation_files),
        "strict_eof_reparse_count": sum(
            row["strict_eof_reparse"] == "PASS" for row in writer_mutation_files
        ),
        "semantic_diff_pass_count": sum(
            row["semantic_diff"]["status"] == "PASS" for row in writer_mutation_files
        ),
        "unexpected_change_count": sum(
            row["semantic_diff"]["unexpected_change_count"] for row in writer_mutation_files
        ),
        "persisted_synthetic_binary_count": 0,
        "game_writes": 0,
        "files": writer_mutation_files,
    }
    untranslated = build_untranslated_inventory(specs, documents, text_bff)
    return roundtrip, inventory, baseline, writer_mutation, untranslated


def load_translation_rows(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TranslationGateError(f"cannot read translation JSON {path}: {exc}") from exc
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("translations"), list):
        rows = payload["translations"]
    else:
        raise TranslationGateError(
            "translation JSON must be a list or an object containing a translations list"
        )
    if not all(isinstance(row, dict) for row in rows):
        raise TranslationGateError("every translation row must be an object")
    return rows


def _parse_expected_hash(value: Any) -> int:
    if isinstance(value, int) and 0 <= value <= 0xFFFFFFFFFFFFFFFF:
        return value
    if isinstance(value, str):
        try:
            parsed = int(value, 0)
        except ValueError as exc:
            raise TranslationGateError(f"invalid hash value {value!r}") from exc
        if 0 <= parsed <= 0xFFFFFFFFFFFFFFFF:
            return parsed
    raise TranslationGateError(f"invalid uint64 hash value {value!r}")


def _row_status(row: dict[str, Any]) -> tuple[str, bool]:
    raw = row.get("status", "APPROVED_AUTO")
    if not isinstance(raw, str):
        raise TranslationGateError("translation status must be a string")
    status = raw.strip().upper()
    if status in APPROVED_STATUSES:
        return status, True
    if status in IGNORED_STATUSES:
        return status, False
    raise TranslationGateError(f"unknown translation status {raw!r}")


def validate_translation_rows(
    documents: dict[str, TDBDocument], rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Validate all selected translation rows without changing source documents."""

    results: list[dict[str, Any]] = []
    prepared: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_targets: set[tuple[str, int]] = set()
    blocked = 0
    ignored = 0
    selected = 0

    for row_number, row in enumerate(rows, start=1):
        result: dict[str, Any] = {
            "row": row_number,
            "tdb": row.get("tdb"),
            "key": row.get("key"),
            "issues": [],
        }
        try:
            status, is_selected = _row_status(row)
            result["translation_status"] = status
            if not is_selected:
                ignored += 1
                result["status"] = "IGNORED"
                results.append(result)
                continue
            selected += 1
            required = ("tdb", "key", "english", "old_korean", "new_korean")
            missing = [name for name in required if name not in row]
            if missing:
                raise TranslationGateError(f"missing required fields: {missing}")
            if not all(isinstance(row[name], str) for name in required):
                raise TranslationGateError("tdb/key/english/old_korean/new_korean must be strings")
            tdb_name = Path(row["tdb"]).name.casefold()
            if tdb_name != row["tdb"].casefold():
                raise TranslationGateError("tdb must be a bare filename, not a path")
            document = documents.get(tdb_name)
            if document is None:
                raise TranslationGateError(f"unknown TDB {row['tdb']!r}")
            if "database" in row and row["database"] != document.database:
                raise TranslationGateError(
                    f"database mismatch: expected {document.database!r}, got {row['database']!r}"
                )
            hits = [index for index, key in enumerate(document.keys) if key == row["key"]]
            if "index" in row:
                index = row["index"]
                if not isinstance(index, int) or isinstance(index, bool):
                    raise TranslationGateError("index must be an integer")
                if not 0 <= index < document.key_count:
                    raise TranslationGateError(f"index {index} out of range")
                if document.keys[index] != row["key"]:
                    raise TranslationGateError("index/key mismatch")
            else:
                if len(hits) != 1:
                    raise TranslationGateError(
                        f"key {row['key']!r} resolves to {len(hits)} records; exact index required"
                    )
                index = hits[0]
            target = (tdb_name, index)
            if target in seen_targets:
                raise TranslationGateError("duplicate selected target")
            seen_targets.add(target)
            english = document.language("English")
            korean = document.language("Korean")
            if english.values[index] != row["english"]:
                raise TranslationGateError("English source gate mismatch")
            if korean.values[index] != row["old_korean"]:
                raise TranslationGateError("old Korean source gate mismatch")
            if "hash" in row:
                expected_hash = _parse_expected_hash(row["hash"])
                if english.hashes[index] != expected_hash:
                    raise TranslationGateError("record hash gate mismatch")
            new_korean = row["new_korean"]
            if new_korean == row["old_korean"]:
                raise TranslationGateError("selected translation is a no-op")
            if "\x00" in new_korean:
                raise TranslationGateError("new Korean contains embedded NUL")
            if EXPLICIT_UNTRANSLATED_RE.match(new_korean):
                raise TranslationGateError("new Korean is still an explicit UNTRANSLATED marker")
            # Encoding now catches invalid unpaired surrogates and the uint32 limit.
            units = utf16_units(new_korean)
            if units > 0xFFFFFFFF:
                raise TranslationGateError("new Korean exceeds uint32 UTF-16 unit length")
            token_gate = validate_token_preservation(row["english"], new_korean)
            result["token_gate"] = token_gate
            if token_gate["status"] != "PASS":
                raise TranslationGateError("placeholder/token/newline/markup gate failed")
            if "tokens" in row:
                supplied = row["tokens"]
                expected_token_text = [token.text for token in extract_tokens(row["english"])]
                if supplied != expected_token_text:
                    result["dataset_tokens"] = supplied
                    result["expected_dataset_tokens"] = expected_token_text
                    raise TranslationGateError(
                        "dataset tokens field does not match extracted English token text"
                    )
            prepared_row = {
                "tdb": Path(row["tdb"]).name,
                "database": document.database,
                "index": index,
                "key": row["key"],
                "hash": f"0x{english.hashes[index]:016X}",
                "english": row["english"],
                "old_korean": row["old_korean"],
                "new_korean": new_korean,
                "old_utf16_units": utf16_units(row["old_korean"]),
                "new_utf16_units": units,
                "token_gate": token_gate,
                "source_row": row_number,
                "translation_status": status,
            }
            prepared[tdb_name].append(prepared_row)
            result.update(prepared_row)
            result["status"] = "PASS"
        except (TDBError, UnicodeError, ValueError) as exc:
            blocked += 1
            result["status"] = "BLOCK"
            result["issues"].append({"kind": type(exc).__name__, "message": str(exc)})
        results.append(result)

    report = {
        "schema": "ams2-kr010-placeholder-validation-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "PASS" if blocked == 0 else "BLOCK",
        "failure_action": "no TDB output is allowed when any selected row blocks",
        "rows_total": len(rows),
        "selected": selected,
        "ignored": ignored,
        "passed": sum(row.get("status") == "PASS" for row in results),
        "blocked": blocked,
        "gate_policy": {
            "identity": "filename + exact key, or filename + exact index + key",
            "source_gates": ["database when supplied", "English", "old Korean", "hash when supplied"],
            "token_gate": "exact ordered (kind,text) sequence including newline/tab/escape and fallback metacharacters",
            "write_scope": "Korean value only",
        },
        "results": results,
    }
    return report, dict(prepared)


def semantic_diff(
    before: TDBDocument,
    after: TDBDocument,
    expected_edits: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Prove that only the selected Korean values changed."""

    unexpected: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    scalar_fields = (
        "version",
        "database",
        "language_count",
        "group_count",
        "key_count",
        "group_string_bytes_with_nuls",
        "key_string_bytes_with_nuls",
        "groups",
        "keys",
    )
    for field in scalar_fields:
        if getattr(before, field) != getattr(after, field):
            unexpected.append({"kind": "METADATA_CHANGED", "field": field})
    expected_by_index = {row["index"]: row for row in expected_edits}
    if len(expected_by_index) != len(expected_edits):
        unexpected.append({"kind": "DUPLICATE_EXPECTED_INDEX"})
    if len(before.languages) != len(after.languages):
        unexpected.append({"kind": "LANGUAGE_COUNT_CHANGED"})
    else:
        for left, right in zip(before.languages, after.languages):
            if left.name != right.name:
                unexpected.append(
                    {"kind": "LANGUAGE_NAME_CHANGED", "before": left.name, "after": right.name}
                )
                continue
            if left.hashes != right.hashes:
                unexpected.append({"kind": "HASHES_CHANGED", "language": left.name})
            if len(left.values) != len(right.values):
                unexpected.append({"kind": "VALUE_COUNT_CHANGED", "language": left.name})
                continue
            for index, (old_value, new_value) in enumerate(zip(left.values, right.values)):
                if old_value == new_value:
                    continue
                change = {
                    "language": left.name,
                    "index": index,
                    "key": before.keys[index],
                    "hash": f"0x{left.hashes[index]:016X}",
                    "before": old_value,
                    "after": new_value,
                }
                changes.append(change)
                expected = expected_by_index.get(index)
                if (
                    left.name != "Korean"
                    or expected is None
                    or expected["old_korean"] != old_value
                    or expected["new_korean"] != new_value
                ):
                    unexpected.append({"kind": "UNEXPECTED_VALUE_CHANGE", **change})
    observed_expected_indices = {
        row["index"] for row in changes if row["language"] == "Korean"
    }
    missing = sorted(set(expected_by_index) - observed_expected_indices)
    for index in missing:
        unexpected.append(
            {
                "kind": "EXPECTED_CHANGE_MISSING",
                "index": index,
                "key": before.keys[index],
            }
        )
    return {
        "status": "PASS" if not unexpected else "BLOCK",
        "expected_change_count": len(expected_edits),
        "observed_change_count": len(changes),
        "unexpected_change_count": len(unexpected),
        "changes": changes,
        "unexpected": unexpected,
    }


def build_patched_documents(
    specs: list[dict[str, Any]],
    documents: dict[str, TDBDocument],
    prepared: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, bytes], dict[str, Any]]:
    payloads: dict[str, bytes] = {}
    file_reports: list[dict[str, Any]] = []
    for spec in specs:
        name = spec["name"]
        edits = prepared.get(name.casefold(), [])
        if not edits:
            continue
        before = documents[name.casefold()]
        after = copy.deepcopy(before)
        korean = after.language("Korean")
        for edit in edits:
            korean.values[edit["index"]] = edit["new_korean"]
        serialized = serialize_tdb(after)
        reparsed = parse_tdb_bytes(serialized, f"{name}#patched")
        second = serialize_tdb(reparsed)
        if serialized != second:
            raise TDBError(f"{name}: patched strict reparse/serialize is not stable")
        diff = semantic_diff(before, reparsed, edits)
        if diff["status"] != "PASS":
            raise TDBError(f"{name}: semantic diff blocked")
        original = spec["path"].read_bytes()
        payloads[name] = serialized
        file_reports.append(
            {
                "tdb": name,
                "database": before.database,
                "source_path": str(spec["path"].resolve()),
                "source_bytes": len(original),
                "source_sha256": sha256_bytes(original),
                "output_bytes": len(serialized),
                "output_sha256": sha256_bytes(serialized),
                "strict_eof_reparse": "PASS",
                "patched_roundtrip_stable": True,
                "korean_block_bytes_before": before.language("Korean").original_block_size,
                "korean_block_bytes_after": len(_language_block_bytes(reparsed.language("Korean"))),
                "semantic_diff": diff,
            }
        )
    report = {
        "schema": "ams2-kr010-tdb-semantic-diff-v1",
        "generated_at": utc_now(),
        "tool_version": VERSION,
        "status": "PASS" if payloads else "BLOCK",
        "changed_tdb_count": len(payloads),
        "targeted_korean_value_count": sum(len(rows) for rows in prepared.values()),
        "unexpected_change_count": sum(
            row["semantic_diff"]["unexpected_change_count"] for row in file_reports
        ),
        "files": file_reports,
    }
    return payloads, report


def write_json_new(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise TDBError(f"refusing to overwrite output: {path}") from exc


def write_text_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write(text)
    except FileExistsError as exc:
        raise TDBError(f"refusing to overwrite output: {path}") from exc


def _ensure_offline_destination(destination: Path, game_dir: Path) -> None:
    resolved = destination.resolve()
    game = game_dir.resolve()
    if resolved == game or game in resolved.parents:
        raise TDBError(f"offline output may not be inside the game directory: {resolved}")
    if resolved.exists():
        raise TDBError(f"refusing to overwrite existing output directory: {resolved}")


def write_build_output(
    destination: Path,
    game_dir: Path,
    payloads: dict[str, bytes],
    validation: dict[str, Any],
    semantic: dict[str, Any],
) -> None:
    _ensure_offline_destination(destination, game_dir)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(destination.name + ".staging")
    if staging.exists():
        raise TDBError(f"staging path already exists: {staging}")
    try:
        (staging / "text").mkdir(parents=True)
        for name, payload in sorted(payloads.items()):
            (staging / "text" / name).write_bytes(payload)
        (staging / "placeholder_validation.json").write_text(
            json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        (staging / "tdb_semantic_diff.json").write_text(
            json.dumps(semantic, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        file_rows = []
        for path in sorted(staging.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_file():
                file_rows.append(
                    {
                        "path": path.relative_to(staging).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
        package_validation = {
            "schema": "ams2-kr010-offline-tdb-build-validation-v1",
            "generated_at": utc_now(),
            "status": "PASS",
            "offline_only": True,
            "game_files_written": 0,
            "payload_tdb_count": len(payloads),
            "files": file_rows,
        }
        (staging / "package-validation.json").write_text(
            json.dumps(package_validation, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        staging.rename(destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def generate_hash_manifest(root: Path, output_name: str = "SHA256SUMS.txt") -> Path:
    root = root.resolve()
    if not root.is_dir():
        raise TDBError(f"hash root is not a directory: {root}")
    output = root / output_name
    if output.exists():
        raise TDBError(f"refusing to overwrite hash manifest: {output}")
    rows: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_file() and path != output:
            rows.append(f"{sha256_file(path)}  {path.relative_to(root).as_posix()}")
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(rows) + "\n")
    return output


def add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--game-dir", type=Path, default=DEFAULT_GAME_DIR)
    parser.add_argument("--extracted-text-dir", type=Path, default=DEFAULT_EXTRACTED_DIR)


def build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="strict parse, 15/15 no-op roundtrip, token inventory")
    add_source_arguments(analyze)
    analyze.add_argument("--text-bff", type=Path)
    analyze.add_argument("--output-dir", type=Path, required=True)

    inventory = subparsers.add_parser(
        "inventory", help="create explicit UNTRANSLATED JSON/CSV from all 15 TDBs"
    )
    add_source_arguments(inventory)
    inventory.add_argument("--text-bff", type=Path)
    inventory.add_argument("--output-dir", type=Path, required=True)

    validate = subparsers.add_parser("validate", help="validate a translation dataset without writing TDBs")
    add_source_arguments(validate)
    validate.add_argument("--translations", type=Path, required=True)
    validate.add_argument("--report", type=Path, required=True)

    build = subparsers.add_parser("build", help="build strict offline patched TDB payloads")
    add_source_arguments(build)
    build.add_argument("--translations", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)

    hashes = subparsers.add_parser("hashes", help="create a non-overwriting SHA256SUMS.txt")
    hashes.add_argument("--root", type=Path, required=True)
    hashes.add_argument("--output-name", default="SHA256SUMS.txt")
    return parser


def command_analyze(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    roundtrip, tokens, placeholder, writer_mutation, untranslated = analyze_roundtrip_and_tokens(
        args.game_dir, args.extracted_text_dir, args.text_bff
    )
    if roundtrip["status"] != "PASS":
        raise TDBError("15/15 byte-identical roundtrip gate failed")
    if writer_mutation["status"] != "PASS":
        raise TDBError("15/15 in-memory writer mutation gate failed")
    write_json_new(output / "tdb_roundtrip.json", roundtrip)
    write_json_new(output / "token_inventory.json", tokens)
    write_json_new(output / "placeholder_validation.json", placeholder)
    write_json_new(output / "writer_mutation_validation.json", writer_mutation)
    write_json_new(output / "untranslated_inventory.json", untranslated)
    write_text_new(
        output / "untranslated_inventory.csv",
        untranslated_inventory_csv_text(untranslated),
    )
    return {
        "status": "PASS",
        "command": "analyze",
        "output_dir": str(output),
        "roundtrip": f"{roundtrip['byte_identical_count']}/{roundtrip['tdb_count']}",
        "writer_mutation": f"{writer_mutation['semantic_diff_pass_count']}/{writer_mutation['tdb_count']}",
        "explicit_untranslated": untranslated["record_count"],
        "token_occurrences": tokens["token_occurrence_count"],
        "baseline_token_mismatches": placeholder["preexisting_baseline_mismatch_count"],
    }


def command_inventory(args: argparse.Namespace) -> dict[str, Any]:
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    specs, documents = load_documents(args.game_dir, args.extracted_text_dir)
    inventory = build_untranslated_inventory(specs, documents, args.text_bff)
    write_json_new(output / "untranslated_inventory.json", inventory)
    write_text_new(
        output / "untranslated_inventory.csv",
        untranslated_inventory_csv_text(inventory),
    )
    return {
        "status": "PASS",
        "command": "inventory",
        "read_only": True,
        "output_dir": str(output),
        "tdb_count": inventory["tdb_count"],
        "explicit_untranslated": inventory["record_count"],
        "text_bff_extracted_markers": inventory["text_bff_extracted_marker_count"],
        "group_resolution": inventory["group_resolution"],
    }


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    _specs, documents = load_documents(args.game_dir, args.extracted_text_dir)
    rows = load_translation_rows(args.translations)
    report, _prepared = validate_translation_rows(documents, rows)
    write_json_new(args.report.resolve(), report)
    if report["status"] != "PASS":
        raise TranslationGateError(
            f"translation validation blocked {report['blocked']} selected row(s); see {args.report.resolve()}"
        )
    return {
        "status": "PASS",
        "command": "validate",
        "report": str(args.report.resolve()),
        "selected": report["selected"],
        "ignored": report["ignored"],
    }


def command_build(args: argparse.Namespace) -> dict[str, Any]:
    specs, documents = load_documents(args.game_dir, args.extracted_text_dir)
    rows = load_translation_rows(args.translations)
    validation, prepared = validate_translation_rows(documents, rows)
    if validation["status"] != "PASS":
        raise TranslationGateError(
            f"translation validation blocked {validation['blocked']} selected row(s)"
        )
    if validation["selected"] == 0:
        raise TranslationGateError("translation dataset has no selected rows")
    payloads, semantic = build_patched_documents(specs, documents, prepared)
    if semantic["status"] != "PASS" or semantic["unexpected_change_count"] != 0:
        raise TDBError("semantic diff gate blocked build")
    write_build_output(
        args.output_dir, args.game_dir, payloads, validation, semantic
    )
    return {
        "status": "PASS",
        "command": "build",
        "offline_only": True,
        "output_dir": str(args.output_dir.resolve()),
        "changed_tdb_count": len(payloads),
        "targeted_korean_value_count": semantic["targeted_korean_value_count"],
        "unexpected_changes": semantic["unexpected_change_count"],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_cli_parser().parse_args(argv)
    try:
        if args.command == "analyze":
            result = command_analyze(args)
        elif args.command == "inventory":
            result = command_inventory(args)
        elif args.command == "validate":
            result = command_validate(args)
        elif args.command == "build":
            result = command_build(args)
        elif args.command == "hashes":
            path = generate_hash_manifest(args.root, args.output_name)
            result = {"status": "PASS", "command": "hashes", "path": str(path)}
        else:  # pragma: no cover - argparse prevents this
            raise TDBError(f"unknown command {args.command!r}")
    except TranslationGateError as exc:
        print(
            json.dumps(
                {"status": "BLOCK", "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    except (TDBError, OSError, UnicodeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
