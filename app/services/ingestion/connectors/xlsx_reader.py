"""Bounded, dependency-free XLSX reader (stdlib ``zipfile`` + ``xml.etree`` only).

An ``.xlsx`` is an OPC ZIP of XML parts. This reads tabular cells by visible tab
name without ``openpyxl``/``pandas``, matching the connectors' stdlib-only ethos.
Everything is bounded (entry count, uncompressed size, per-part bytes, rows,
columns, cell length, shared-string count) so a hostile or oversized workbook
cannot exhaust memory. XML is matched by element local-name so minor producer
namespace variations do not break parsing.
"""

from __future__ import annotations

import io
import zipfile
from typing import Iterator
from xml.etree import ElementTree as ET


class XlsxError(ValueError):
    """Raised when bytes are not a usable XLSX workbook."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def open_workbook(
    data: bytes,
    *,
    max_total_uncompressed_bytes: int,
    max_entries: int = 64,
) -> zipfile.ZipFile:
    """Open XLSX bytes as a ZIP, rejecting non-zip input and zip bombs."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise XlsxError("content is not a valid XLSX/ZIP workbook") from exc
    infos = archive.infolist()
    if len(infos) > max_entries:
        raise XlsxError(f"workbook has {len(infos)} entries; maximum is {max_entries}")
    total = sum(info.file_size for info in infos)
    if total > max_total_uncompressed_bytes:
        raise XlsxError("workbook uncompressed size exceeds the allowed bound")
    names = set(archive.namelist())
    if "[Content_Types].xml" not in names:
        raise XlsxError("content is a ZIP but not an Office Open XML workbook")
    return archive


def _read_part(zf: zipfile.ZipFile, name: str, *, max_bytes: int) -> bytes | None:
    if name not in zf.namelist():
        return None
    with zf.open(name) as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise XlsxError(f"workbook part {name} exceeds the allowed bound")
    return data


def map_sheets(zf: zipfile.ZipFile, *, max_bytes: int) -> dict[str, str]:
    """Return {visible_tab_name: worksheet_part_path} via workbook.xml + its rels."""
    workbook = _read_part(zf, "xl/workbook.xml", max_bytes=max_bytes)
    rels = _read_part(zf, "xl/_rels/workbook.xml.rels", max_bytes=max_bytes)
    if workbook is None or rels is None:
        raise XlsxError("workbook is missing xl/workbook.xml or its relationships")

    name_to_rid: dict[str, str] = {}
    for element in ET.fromstring(workbook).iter():
        if _local(element.tag) != "sheet":
            continue
        name = element.get("name")
        rid = next(
            (value for key, value in element.attrib.items() if _local(key) == "id"),
            None,
        )
        if name and rid:
            name_to_rid[name] = rid

    rid_to_target: dict[str, str] = {}
    for element in ET.fromstring(rels).iter():
        if _local(element.tag) != "Relationship":
            continue
        rid, target = element.get("Id"), element.get("Target")
        if rid and target:
            rid_to_target[rid] = target

    sheets: dict[str, str] = {}
    for name, rid in name_to_rid.items():
        target = rid_to_target.get(rid)
        if not target:
            continue
        sheets[name] = _normalize_part_path(target)
    return sheets


def _normalize_part_path(target: str) -> str:
    target = target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return "xl/" + target


def read_shared_strings(
    zf: zipfile.ZipFile,
    *,
    max_bytes: int,
    max_strings: int,
    max_cell_chars: int,
) -> list[str]:
    """Parse xl/sharedStrings.xml -> list of plain strings (index == position)."""
    data = _read_part(zf, "xl/sharedStrings.xml", max_bytes=max_bytes)
    if data is None:
        return []
    strings: list[str] = []
    for element in ET.fromstring(data):
        if _local(element.tag) != "si":
            continue
        text = "".join(
            node.text or "" for node in element.iter() if _local(node.tag) == "t"
        )
        strings.append(text[:max_cell_chars])
        if len(strings) > max_strings:
            raise XlsxError("sharedStrings table exceeds the allowed bound")
    return strings


def column_index(cell_ref: str) -> int:
    """'C7' -> 2 ; 'AA1' -> 26. Letters only, 0-based."""
    letters = ""
    for char in cell_ref:
        if char.isalpha():
            letters += char
        else:
            break
    if not letters:
        raise XlsxError(f"invalid cell reference: {cell_ref!r}")
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _cell_text(cell: ET.Element, shared_strings: list[str], *, max_cell_chars: int) -> str | None:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        text = "".join(
            node.text or "" for node in cell.iter() if _local(node.tag) == "t"
        )
        return text[:max_cell_chars] if text else None
    value = next((node for node in cell if _local(node.tag) == "v"), None)
    if value is None or value.text is None:
        return None
    raw = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (ValueError, IndexError) as exc:
            raise XlsxError("shared string index out of range") from exc
    return raw[:max_cell_chars]


def iter_sheet_rows(
    zf: zipfile.ZipFile,
    part_path: str,
    shared_strings: list[str],
    *,
    max_rows: int,
    max_cols: int,
    max_cell_chars: int,
) -> Iterator[list[str | None]]:
    """Yield each worksheet row as a dense list of cell strings (None for blanks)."""
    emitted = 0
    with zf.open(part_path) as stream:
        for _event, element in ET.iterparse(stream, events=("end",)):
            if _local(element.tag) != "row":
                continue
            cells: list[tuple[int, str | None]] = []
            width = 0
            position = 0
            for cell in element:
                if _local(cell.tag) != "c":
                    continue
                ref = cell.get("r")
                col = column_index(ref) if ref else position
                position = col + 1
                if col >= max_cols:
                    element.clear()
                    raise XlsxError(f"row exceeds the maximum of {max_cols} columns")
                cells.append((col, _cell_text(cell, shared_strings, max_cell_chars=max_cell_chars)))
                width = max(width, col + 1)
            row: list[str | None] = [None] * width
            for col, text in cells:
                row[col] = text
            element.clear()
            yield row
            emitted += 1
            if emitted >= max_rows:
                return


def read_tab(
    data: bytes,
    tab_name: str,
    *,
    max_total_uncompressed_bytes: int,
    max_bytes_per_part: int,
    max_rows: int,
    max_cols: int,
    max_cell_chars: int,
    max_strings: int = 2_000_000,
    required: bool = True,
) -> list[list[str | None]]:
    """Open -> map sheets -> shared strings -> all rows of ONE tab (dense lists).

    Tab match is case/whitespace-insensitive. Missing tab raises when required,
    else returns []. Header detection is the caller's responsibility (these
    reports carry banner rows before the real header)."""
    archive = open_workbook(
        data,
        max_total_uncompressed_bytes=max_total_uncompressed_bytes,
    )
    with archive:
        sheets = map_sheets(archive, max_bytes=max_bytes_per_part)
        wanted = _normalize(tab_name)
        part = next(
            (path for name, path in sheets.items() if _normalize(name) == wanted),
            None,
        )
        if part is None:
            if required:
                raise XlsxError(f"workbook has no tab named {tab_name!r}")
            return []
        shared = read_shared_strings(
            archive,
            max_bytes=max_bytes_per_part,
            max_strings=max_strings,
            max_cell_chars=max_cell_chars,
        )
        return list(
            iter_sheet_rows(
                archive,
                part,
                shared,
                max_rows=max_rows,
                max_cols=max_cols,
                max_cell_chars=max_cell_chars,
            )
        )


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()
