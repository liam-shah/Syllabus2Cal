from pathlib import Path

import pytest

from app.errors import InvalidInputError
from app.integrations import pdf_extraction
from app.integrations.pdf_extraction import PDFExtractionError, extract

FIXTURES_DIR = Path(__file__).parent / "fixtures"
NO_LIMIT = 1_000_000


def test_extract_finds_known_text():
    pdf_bytes = (FIXTURES_DIR / "EOSC211_2026_Schedule.pdf").read_bytes()
    text, _ = extract(pdf_bytes, NO_LIMIT)
    assert "Midterm" in text
    assert "Sep 10" in text


def test_extract_returns_table_rows():
    pdf_bytes = (FIXTURES_DIR / "cpsc213_schedule_current.pdf").read_bytes()
    _, tables = extract(pdf_bytes, NO_LIMIT)
    assert len(tables) >= 1
    assert any("Sep 14-18" in str(cell) for row in tables[0] for cell in row)


def test_text_exactly_at_the_limit_still_gets_its_tables():
    pdf_bytes = (FIXTURES_DIR / "cpsc213_schedule_current.pdf").read_bytes()
    text, _ = extract(pdf_bytes, NO_LIMIT)
    _, tables = extract(pdf_bytes, len(text))
    assert len(tables) >= 1


class FakePage:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self) -> str:
        if self.text is None:
            raise AssertionError("read a page after the text was already over the limit")
        return self.text

    def extract_tables(self):
        return [[[self.text[:5]]]]


class FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_reading_stops_once_the_text_is_over_the_limit(monkeypatch):
    # A huge PDF that will be refused anyway mustn't be parsed to the end.
    pages = [FakePage("a" * 600), FakePage("b" * 600), FakePage(None)]
    monkeypatch.setattr(pdf_extraction.pdfplumber, "open", lambda _: FakePdf(pages))

    text, tables = extract(b"%PDF", max_text_chars=1000)

    assert len(text) > 1000  # over the limit, so the upload is refused
    assert tables == [[["aaaaa"]]]  # the over-limit page's tables weren't read either


def test_non_pdf_raises_pdf_extraction_error():
    with pytest.raises(PDFExtractionError):
        extract(b"this is not a pdf", NO_LIMIT)


def test_pdf_extraction_error_is_an_invalid_input_error():
    # main.py turns every InvalidInputError into a 400 - this pins the hierarchy.
    assert issubclass(PDFExtractionError, InvalidInputError)
