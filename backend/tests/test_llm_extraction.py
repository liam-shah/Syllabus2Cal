from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domain import EventDraft
from app.integrations.llm_extraction import (
    ExtractionResult,
    LLMExtractionError,
    extract_events,
    format_tables,
)

MIDTERM = EventDraft(title="Midterm 1", start_date=date(2026, 10, 8), date_is_approximate=False,
                     source_snippet="Oct 08 Midterm 1")
UPLOADED_ON = date(2026, 10, 27)


def mock_stream(mock_client_cls, get_final_message):
    # extract_events does: with client.messages.stream(...) as stream: stream.get_final_message()
    stream = mock_client_cls.return_value.messages.stream.return_value.__enter__.return_value
    stream.get_final_message.side_effect = get_final_message


def test_extract_events_returns_event_drafts():
    fake_response = MagicMock()
    fake_response.parsed_output = ExtractionResult(events=[MIDTERM])

    with patch("app.integrations.llm_extraction.anthropic.Anthropic") as mock_client_cls:
        mock_stream(mock_client_cls, lambda: fake_response)
        events = extract_events("...some raw text...", [], filename="schedule.pdf", uploaded_on=UPLOADED_ON)

    assert events == [MIDTERM]


def test_claude_is_told_the_file_name_and_upload_date():
    # Schedules often never state their year (EOSC 211's says only "Fall" and "Sep 08"); the
    # year can be in the file name, and the upload date tells Claude which term is current.
    fake_response = MagicMock()
    fake_response.parsed_output = ExtractionResult(events=[MIDTERM])

    with patch("app.integrations.llm_extraction.anthropic.Anthropic") as mock_client_cls:
        mock_stream(mock_client_cls, lambda: fake_response)
        extract_events("Sep 08 Imagine UBC Day", [], filename="EOSC211_2026_Schedule.pdf", uploaded_on=UPLOADED_ON)

    request = mock_client_cls.return_value.messages.stream.call_args.kwargs
    message = request["messages"][0]["content"]
    assert "FILE NAME: EOSC211_2026_Schedule.pdf" in message
    assert "UPLOADED ON: 2026-10-27" in message
    assert "FILE NAME" in request["system"] and "UPLOADED ON" in request["system"]  # the prompt says how to use them


def test_extract_events_raises_when_response_unparseable():
    fake_response = MagicMock()
    fake_response.parsed_output = None
    fake_response.stop_reason = "max_tokens"

    with patch("app.integrations.llm_extraction.anthropic.Anthropic") as mock_client_cls:
        mock_stream(mock_client_cls, lambda: fake_response)
        with pytest.raises(LLMExtractionError, match="max_tokens"):
            extract_events("...some raw text...", [], filename="schedule.pdf", uploaded_on=UPLOADED_ON)


def test_extract_events_raises_when_reply_is_cut_off():
    def cut_off_reply():
        # Same failure as a real max_tokens cut-off: JSON that stops mid-string.
        return ExtractionResult.model_validate_json('{"events": [{"title": "2c: Mutex')

    with patch("app.integrations.llm_extraction.anthropic.Anthropic") as mock_client_cls:
        mock_stream(mock_client_cls, cut_off_reply)
        with pytest.raises(LLMExtractionError, match="cut off"):
            extract_events("...some raw text...", [], filename="schedule.pdf", uploaded_on=UPLOADED_ON)


def test_format_tables_joins_cells_and_cleans_them():
    tables = [[["0", "Sep 7-11", None, "1a: Memory &\nNumbers"]]]
    assert format_tables(tables) == "Table 1:\n0 | Sep 7-11 |  | 1a: Memory & Numbers"
