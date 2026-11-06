import pytest

from src.parser import parse_many, parse_screenplay, timestamp_to_seconds


def test_timestamp_to_seconds_parses_minutes_seconds_and_fraction():
    assert timestamp_to_seconds("01:02.5") == pytest.approx(62.5)


def test_timestamp_to_seconds_rejects_invalid_input():
    with pytest.raises(ValueError, match="Invalid timestamp"):
        timestamp_to_seconds("not-a-time")


def test_parse_screenplay_extracts_episode_scene_and_timed_event():
    screenplay = """EPISODE NUMBER: 7
EPISODE LOGLINE: A secret changes everything.
CONTINUITY NOTES: The truth is not yet known.

SCENE 01
Scene heading: INT. HOUSE - NIGHT
Scene start: 00:00
Scene end: 01:00
**Confrontation:**
Start: (00:05) | End: (00:35)
A character reveals a secret.
"""
    parsed = parse_screenplay(screenplay, "episode_7.txt")
    assert parsed["episode"] == "7"
    assert parsed["logline"] == "A secret changes everything."
    assert parsed["scene_count"] == 1
    assert parsed["event_count"] == 1
    event = parsed["scenes"][0]["events"][0]
    assert event["type"] == "Confrontation"
    assert event["start_seconds"] == 5
    assert event["end_seconds"] == 35


def test_parse_many_returns_parse_errors_for_input_without_scenes():
    parsed, errors = parse_many([("empty.txt", "No scene data here.")])
    assert parsed == []
    assert errors == [{"file": "empty.txt", "error": "No scene headings found"}]
