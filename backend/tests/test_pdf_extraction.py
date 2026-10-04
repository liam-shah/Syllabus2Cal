from pathlib import Path

import pytest

from app.errors import InvalidInputError
from app.integrations.pdf_extraction import PDFExtractionError, extract_tables, extract_text

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_extract_text_finds_known_content():
    pdf_bytes = (FIXTURES_DIR / "EOSC211_2026_Schedule.pdf").read_bytes()
    text = extract_text(pdf_bytes)
    assert "Midterm" in text
    assert "Sep 10" in text


def test_extract_tables_returns_rows():
    pdf_bytes = (FIXTURES_DIR / "cpsc213_schedule_current.pdf").read_bytes()
    tables = extract_tables(pdf_bytes)
    assert len(tables) >= 1
    assert any("Sep 14-18" in str(cell) for row in tables[0] for cell in row)


def test_non_pdf_raises_pdf_extraction_error():
    with pytest.raises(PDFExtractionError):
        extract_text(b"this is not a pdf")


def test_pdf_extraction_error_is_an_invalid_input_error():
    # main.py turns every InvalidInputError into a 400 - this pins the hierarchy.
    assert issubclass(PDFExtractionError, InvalidInputError)
