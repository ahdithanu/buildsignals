from app.services.ingestion.text_decoding import (
    decode_mixed_utf8_cp1252,
    resolve_hybrid_decoder,
)


def test_clean_utf8_is_unchanged_including_bom():
    assert decode_mixed_utf8_cp1252("café — ok".encode("utf-8")) == "café — ok"
    assert decode_mixed_utf8_cp1252("﻿heading".encode("utf-8")) == "heading"


def test_mixed_archive_reinterprets_only_invalid_utf8_bytes():
    # "City" + cp1252 right single quote (0x92) + "s caf" + UTF-8 "é".
    assert decode_mixed_utf8_cp1252(b"City\x92s caf\xc3\xa9") == "City’s café"


def test_clean_windows_1252_smart_punctuation_round_trips():
    source = "“quote” – dash".encode("cp1252")
    assert decode_mixed_utf8_cp1252(source) == "“quote” – dash"


def test_undefined_cp1252_byte_falls_back_to_latin1_without_raising():
    # 0x90 is undefined in cp1252; Latin-1 keeps it as U+0090 rather than dropping it.
    assert decode_mixed_utf8_cp1252(b"a\x90b") == "a\u0090b"


def test_resolve_hybrid_decoder_only_for_known_names():
    assert resolve_hybrid_decoder("utf-8-sig+cp1252") is decode_mixed_utf8_cp1252
    assert resolve_hybrid_decoder(None) is None
    assert resolve_hybrid_decoder("utf-8") is None
    assert resolve_hybrid_decoder("cp1252") is None
