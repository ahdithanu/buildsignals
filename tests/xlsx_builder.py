"""Minimal, dependency-free .xlsx byte builder for tests (stdlib zipfile only).

Builds just enough valid Office Open XML for app.services.ingestion.connectors
.xlsx_reader to parse: [Content_Types].xml, package + workbook rels, workbook,
per-sheet worksheets, and a shared-strings table. Cells accept str (shared
string), int/float (number), bool, or None (blank/omitted).
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

_SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _col_letter(index0: int) -> str:
    letters = ""
    index = index0 + 1
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def build_xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def intern(text: str) -> int:
        if text not in shared_index:
            shared_index[text] = len(shared)
            shared.append(text)
        return shared_index[text]

    worksheet_parts: list[tuple[str, str]] = []  # (part_path, xml)
    for order, (name, rows) in enumerate(sheets.items(), start=1):
        row_xml: list[str] = []
        for r, row in enumerate(rows, start=1):
            cells: list[str] = []
            for c, value in enumerate(row):
                if value is None:
                    continue
                ref = f"{_col_letter(c)}{r}"
                if isinstance(value, bool):
                    cells.append(f'<c r="{ref}" t="b"><v>{1 if value else 0}</v></c>')
                elif isinstance(value, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="s"><v>{intern(str(value))}</v></c>')
            row_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
        xml = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{_SS_NS}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>'
        )
        worksheet_parts.append((f"xl/worksheets/sheet{order}.xml", xml))

    sheet_tags = "".join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(sheets, start=1)
    )
    workbook_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{_SS_NS}" xmlns:r="{_REL_NS}"><sheets>{sheet_tags}</sheets></workbook>'
    )
    rel_tags = "".join(
        f'<Relationship Id="rId{i}" '
        f'Type="{_REL_NS}/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, len(sheets) + 1)
    )
    workbook_rels = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_REL_NS}">{rel_tags}</Relationships>'
    )
    si = "".join(f"<si><t>{escape(text)}</t></si>" for text in shared)
    shared_strings = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{_SS_NS}" count="{len(shared)}" uniqueCount="{len(shared)}">{si}</sst>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_REL_NS}">'
        f'<Relationship Id="rIdWB" Type="{_REL_NS}/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        for part_path, xml in worksheet_parts:
            archive.writestr(part_path, xml)
    return buffer.getvalue()
