from __future__ import annotations

import hashlib
import importlib
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from types import ModuleType

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_PDF_CONTENT_TYPE = "application/pdf"
_SUPPORTED_CONTENT_TYPES = _HTML_CONTENT_TYPES | {_PDF_CONTENT_TYPE}
_WHITESPACE = re.compile(r"\s+")


class DocumentExtractionError(ValueError):
    """Base class for deterministic document extraction failures."""

    code = "document_extraction_failed"


class DocumentOversizedError(DocumentExtractionError):
    code = "document_oversized"


class DocumentTypeError(DocumentExtractionError):
    code = "unsupported_content_type"


class DocumentMalformedError(DocumentExtractionError):
    code = "document_malformed"


class DocumentEncryptedError(DocumentExtractionError):
    code = "document_encrypted"


class PdfExtractionUnavailableError(DocumentExtractionError):
    code = "pdf_extraction_unavailable"


@dataclass(frozen=True)
class DocumentSection:
    text: str
    citation: str
    section_number: int | None = None
    page_number: int | None = None
    heading: str | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    content_type: str
    byte_size: int
    sha256: str
    text: str
    sections: tuple[DocumentSection, ...]


@dataclass(frozen=True)
class _HtmlBlock:
    text: str
    heading: str | None


class _PlanningHtmlParser(HTMLParser):
    _ignored_tags = frozenset({"script", "style", "noscript", "template"})
    _block_tags = frozenset(
        {
            "article",
            "blockquote",
            "br",
            "dd",
            "div",
            "dl",
            "dt",
            "figcaption",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "li",
            "main",
            "nav",
            "p",
            "section",
            "td",
            "th",
            "tr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_HtmlBlock] = []
        self._buffer: list[str] = []
        self._ignored_depth = 0
        self._heading_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self._ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self._block_tags:
            self._flush()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._ignored_tags:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if self._ignored_depth:
            return
        if tag in self._block_tags:
            self._flush(as_heading=tag == self._heading_tag)
        if tag == self._heading_tag:
            self._heading_tag = None

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self, *, as_heading: bool = False) -> None:
        text = _normalize_text(" ".join(self._buffer))
        self._buffer.clear()
        if not text:
            return
        self.blocks.append(_HtmlBlock(text=text, heading=text if as_heading else None))


def extract_document(
    content: bytes,
    content_type: str,
    *,
    source_url: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ExtractedDocument:
    """Extract citation-addressable text from an already-fetched planning document."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")
    if len(content) > max_bytes:
        raise DocumentOversizedError(
            f"document is {len(content)} bytes; maximum allowed size is {max_bytes} bytes"
        )

    normalized_type = content_type.partition(";")[0].strip().lower()
    if normalized_type not in _SUPPORTED_CONTENT_TYPES:
        raise DocumentTypeError(f"unsupported content type: {normalized_type or '<missing>'}")
    if not content:
        raise DocumentMalformedError("document is empty")

    digest = hashlib.sha256(content).hexdigest()
    if normalized_type == _PDF_CONTENT_TYPE:
        sections = _extract_pdf(content, source_url)
    else:
        sections = _extract_html(content, source_url)

    return ExtractedDocument(
        content_type=normalized_type,
        byte_size=len(content),
        sha256=digest,
        text="\n\n".join(section.text for section in sections if section.text),
        sections=sections,
    )


def _extract_html(content: bytes, source_url: str | None) -> tuple[DocumentSection, ...]:
    if content.lstrip().startswith(b"%PDF-"):
        raise DocumentTypeError("content is a PDF but was labeled as HTML")
    try:
        markup = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentMalformedError("HTML document is not valid UTF-8") from exc

    parser = _PlanningHtmlParser()
    try:
        parser.feed(markup)
        parser.close()
    except Exception as exc:
        raise DocumentMalformedError("HTML document could not be parsed") from exc

    sections: list[DocumentSection] = []
    current_heading: str | None = None
    for block in parser.blocks:
        if block.heading:
            current_heading = block.heading
        number = len(sections) + 1
        citation = _citation(source_url, f"section-{number}")
        sections.append(
            DocumentSection(
                text=block.text,
                citation=citation,
                section_number=number,
                heading=current_heading,
            )
        )
    if not sections:
        raise DocumentMalformedError("HTML document contains no extractable text")
    return tuple(sections)


def _extract_pdf(content: bytes, source_url: str | None) -> tuple[DocumentSection, ...]:
    if not content.lstrip().startswith(b"%PDF-"):
        raise DocumentMalformedError("PDF signature is missing")
    pdf_module = _load_pdf_module()
    try:
        reader = pdf_module.PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise DocumentEncryptedError("encrypted PDFs are not supported")
        pages = list(reader.pages)
    except DocumentEncryptedError:
        raise
    except Exception as exc:
        raise DocumentMalformedError("PDF document could not be parsed") from exc

    if not pages:
        raise DocumentMalformedError("PDF document contains no pages")

    sections: list[DocumentSection] = []
    for index, page in enumerate(pages, start=1):
        try:
            text = _normalize_text(page.extract_text() or "", preserve_lines=True)
        except Exception as exc:
            raise DocumentMalformedError(f"PDF page {index} could not be parsed") from exc
        sections.append(
            DocumentSection(
                text=text,
                citation=_citation(source_url, f"page-{index}"),
                page_number=index,
            )
        )
    return tuple(sections)


def _load_pdf_module() -> ModuleType:
    for module_name in ("pypdf", "PyPDF2"):
        try:
            return importlib.import_module(module_name)
        except ImportError:
            continue
    raise PdfExtractionUnavailableError(
        "PDF text extraction requires an installed pypdf or PyPDF2 dependency"
    )


def _citation(source_url: str | None, fragment: str) -> str:
    return f"{source_url}#{fragment}" if source_url else fragment


def _normalize_text(value: str, *, preserve_lines: bool = False) -> str:
    if not preserve_lines:
        return _WHITESPACE.sub(" ", value).strip()
    lines = (_WHITESPACE.sub(" ", line).strip() for line in value.splitlines())
    return "\n".join(line for line in lines if line)
