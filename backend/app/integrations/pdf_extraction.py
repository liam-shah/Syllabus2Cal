# Extracts raw text (and tables) from a PDF file using pdfplumber.

import io

import pdfplumber
from pdfplumber.utils.exceptions import PdfminerException

from app.errors import InvalidInputError


class PDFExtractionError(InvalidInputError):
    """Raised when a file can't be read as a PDF."""


def extract_text(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_texts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text is None:
                    text = ""
                page_texts.append(text)
    except PdfminerException as e:
        raise PDFExtractionError(f"Could not read the file as a PDF: {e}") from e
    return "\n\n".join(page_texts)


def extract_tables(pdf_bytes: bytes) -> list[list[list[str | None]]]:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            tables: list[list[list[str | None]]] = []
            for page in pdf.pages:
                tables.extend(page.extract_tables())
    except PdfminerException as e:
        raise PDFExtractionError(f"Could not read the file as a PDF: {e}") from e
    return tables