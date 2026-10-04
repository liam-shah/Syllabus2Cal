"""Sends a PDF's text and tables to Claude and gets back structured events
using structured outputs (a Pydantic model describing the JSON shape)."""

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.domain import EventDraft
from app.errors import ExternalServiceError

SYSTEM_PROMPT = (
    "You extract calendar events from a PDF course schedule or syllabus. "
    "You are given two versions of the same PDF: RAW TEXT (reading order, includes the column headers) "
    "and TABLES (one row per line, cells separated by ' | ', with the headers usually missing). "
    "Use the raw text to understand what each column means, and use the tables to find every item -- "
    "every non-empty cell for a lecture, lab, assignment, quiz, or exam should become its own event. "
    "Dates: only give a specific day when the PDF states it (e.g. 'Oct 08'), or when a column header names "
    "the weekday (e.g. a 'Tuesday' column in the week of Sep 14-18 means Sep 15). "
    "If an item only belongs to a week with no day given, set start_date to the first day of that week, "
    "set date_is_approximate to true, and do not invent a due date. Otherwise set date_is_approximate to false. "
    "For every event, copy the exact source text you used into source_snippet -- do not shorten it with '...'. "
    "If the year is not stated but the term is inferable (e.g. 'Fall 2026'), use that year for the dates."
)

MODEL = "claude-sonnet-5"


class ExtractionResult(BaseModel):
    """The shape of Claude's whole reply: a list of events."""

    events: list[EventDraft]


class LLMExtractionError(ExternalServiceError):
    """Raised when Claude fails to extract events from the given text."""


def format_tables(tables: list[list[list[str | None]]]) -> str:
    formatted_tables = []

    for table_number, table in enumerate(tables, start=1):
        lines = [f"Table {table_number}:"]
        for row in table:
            cells = [(cell or "").replace("\n", " ") for cell in row]
            lines.append(" | ".join(cells))
        formatted_tables.append("\n".join(lines))
    return "\n\n".join(formatted_tables)


def extract_events(raw_text: str, tables: list[list[list[str | None]]]) -> list[EventDraft]:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    tables_text = format_tables(tables) or "(no tables found)"
    user_message = f"RAW TEXT:\n{raw_text}\n\nTABLES:\n{tables_text}"

    # Streaming lets us allow a large max_tokens (thinking + ~60 events) without the
    # SDK's non-streaming timeout limit. max_tokens is a cap, not what you're billed.
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            output_format=ExtractionResult,
            output_config={"effort": "low"},
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIError as e:
        raise LLMExtractionError(f"Claude API call failed: {e}") from e
    except ValidationError as e:
        raise LLMExtractionError(
            f"Claude's reply didn't match the expected format (often because it was cut off by max_tokens): {e}"
        ) from e

    if response.parsed_output is None:
        raise LLMExtractionError(
            f"Claude's response could not be parsed (stop_reason: {response.stop_reason})"
        )

    return response.parsed_output.events
