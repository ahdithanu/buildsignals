from __future__ import annotations

import hashlib
import io

import pytest

from app.services.planning_documents import (
    DocumentEncryptedError,
    DocumentMalformedError,
    DocumentOversizedError,
    DocumentTypeError,
    extract_document,
)


def test_extracts_html_with_hash_and_section_citations():
    content = b"""
        <html><head><style>hidden</style></head><body>
        <h1>Planning Director Hearing</h1>
        <p>Consider file CP23-008 at 2549 Orchard Parkway.</p>
        <script>also hidden</script>
        </body></html>
    """

    result = extract_document(
        content,
        "text/html; charset=utf-8",
        source_url="https://example.test/hearings/agenda",
    )

    assert result.sha256 == hashlib.sha256(content).hexdigest()
    assert result.content_type == "text/html"
    assert "hidden" not in result.text
    assert "CP23-008" in result.text
    assert result.sections[0].heading == "Planning Director Hearing"
    assert result.sections[1].heading == "Planning Director Hearing"
    assert result.sections[1].citation == "https://example.test/hearings/agenda#section-2"


def test_rejects_oversized_and_invalid_documents_before_parsing():
    with pytest.raises(DocumentOversizedError, match="maximum allowed size"):
        extract_document(b"12345", "text/html", max_bytes=4)

    with pytest.raises(DocumentTypeError, match="unsupported content type"):
        extract_document(b"plain text", "text/plain")

    with pytest.raises(DocumentMalformedError, match="valid UTF-8"):
        extract_document(b"\xff", "text/html")

    with pytest.raises(DocumentMalformedError, match="PDF signature"):
        extract_document(b"not a PDF", "application/pdf")


def test_extracts_text_pdf_by_page_when_pdf_parser_is_installed():
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    contents = pypdf.generic.DecodedStreamObject()
    contents.set_data(
        b"BT /F1 12 Tf 72 720 Td (Planning item CP23-008) Tj ET"
    )
    page[pypdf.generic.NameObject("/Contents")] = contents
    page[pypdf.generic.NameObject("/Resources")] = pypdf.generic.DictionaryObject(
        {
            pypdf.generic.NameObject("/Font"): pypdf.generic.DictionaryObject(
                {
                    pypdf.generic.NameObject("/F1"): pypdf.generic.DictionaryObject(
                        {
                            pypdf.generic.NameObject("/Type"): pypdf.generic.NameObject("/Font"),
                            pypdf.generic.NameObject("/Subtype"): pypdf.generic.NameObject(
                                "/Type1"
                            ),
                            pypdf.generic.NameObject("/BaseFont"): pypdf.generic.NameObject(
                                "/Helvetica"
                            ),
                        }
                    )
                }
            )
        }
    )
    buffer = io.BytesIO()
    writer.write(buffer)

    result = extract_document(
        buffer.getvalue(),
        "application/pdf",
        source_url="https://example.test/agenda.pdf",
    )

    assert result.text == "Planning item CP23-008"
    assert result.sections[0].page_number == 1
    assert result.sections[0].citation == "https://example.test/agenda.pdf#page-1"


def test_rejects_encrypted_pdf_when_pdf_parser_is_installed():
    pypdf = pytest.importorskip("pypdf")
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.encrypt("secret")
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(DocumentEncryptedError, match="encrypted PDFs"):
        extract_document(buffer.getvalue(), "application/pdf")
