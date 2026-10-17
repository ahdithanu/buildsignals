"""Shared, opt-in text decoding helpers for bounded HTML/document ingestion.

Some official archives publish pages that are mostly valid UTF-8 but splice in a
handful of legacy Windows-1252 bytes (typically smart quotes, dashes or an
accented name copied from a desktop document). Strict UTF-8 decoding raises on
those bytes, so the page cannot be crawled at all.

These helpers reinterpret only the bytes that are not valid UTF-8, leaving every
valid UTF-8 (and clean Windows-1252) sequence untouched. They are selected
per source via a connector ``text_encoding`` setting; the default decoding path
stays strict, so enabling tolerant decoding for one reviewed source never
weakens decoding for any other source.
"""

from __future__ import annotations

from typing import Callable

# surrogateescape maps each undecodable byte 0xNN to the lone surrogate
# 0xDC00 + 0xNN. Only bytes with the high bit set (>= 0x80) are ever invalid in a
# UTF-8 stream, so the surrogate range we need to reinterpret is 0xDC80..0xDCFF.
_SURROGATE_BASE = 0xDC00
_SURROGATE_LOW = 0xDC80
_SURROGATE_HIGH = 0xDCFF


def decode_mixed_utf8_cp1252(body: bytes) -> str:
    """Decode bytes that mix valid UTF-8 with legacy Windows-1252 bytes.

    Valid UTF-8 (including a leading BOM) decodes normally. Each byte that is not
    valid UTF-8 is reinterpreted through Windows-1252, falling back to Latin-1 for
    the five positions cp1252 leaves undefined so the decode never raises or drops
    a byte. Clean UTF-8 and clean Windows-1252 inputs are unchanged.
    """
    text = body.decode("utf-8-sig", errors="surrogateescape")
    if not any(_SURROGATE_LOW <= ord(char) <= _SURROGATE_HIGH for char in text):
        return text
    return "".join(_reinterpret_legacy_byte(char) for char in text)


def _reinterpret_legacy_byte(char: str) -> str:
    code = ord(char)
    if not _SURROGATE_LOW <= code <= _SURROGATE_HIGH:
        return char
    legacy_byte = bytes([code - _SURROGATE_BASE])
    try:
        return legacy_byte.decode("cp1252")
    except UnicodeDecodeError:
        # cp1252 leaves 0x81, 0x8D, 0x8F, 0x90 and 0x9D undefined; Latin-1 keeps
        # the byte as a code point rather than discarding evidence.
        return legacy_byte.decode("latin-1")


# JSON-selectable tolerant decoders keyed by the ``text_encoding`` connector
# setting. Anything not listed here is treated as a strict codec name.
_HYBRID_DECODERS: dict[str, Callable[[bytes], str]] = {
    "utf-8-sig+cp1252": decode_mixed_utf8_cp1252,
}


def resolve_hybrid_decoder(name: str | None) -> Callable[[bytes], str] | None:
    """Return a tolerant byte decoder for ``name`` or ``None`` for strict codecs."""
    if name is None:
        return None
    return _HYBRID_DECODERS.get(name)
