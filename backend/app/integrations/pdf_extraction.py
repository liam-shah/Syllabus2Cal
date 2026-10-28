# Extracts raw text (and tables) from a PDF file using pdfplumber.

import io

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from app.errors import InvalidInputError

Table = list[list[str | None]]


class PDFExtractionError(InvalidInputError):
    """Raised when a file can't be read as a PDF."""


def extract(pdf_bytes: bytes, max_text_chars: int) -> tuple[str, list[Table]]:
    """The PDF's text (pages joined by blank lines) and its tables, in one pass over the pages.

    Stops reading once the text is longer than max_text_chars, so a huge PDF that's going to be
    refused anyway isn't parsed to the end: the text returned is then just over the limit.
    """
    page_texts: list[str] = []
    tables: list[Table] = []
    length = 0
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                length += len(text) + (2 if page_texts else 0)  # + the "\n\n" before every page but the first
                page_texts.append(text)
                if length > max_text_chars:
                    break
                tables.extend(page.extract_tables())
    except PdfminerException as e:
        raise PDFExtractionError(f"Could not read the file as a PDF: {e}") from e
    return "\n\n".join(page_texts), tables
