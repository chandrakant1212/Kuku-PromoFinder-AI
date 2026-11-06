import pytest

from src.scoring import final_score, validate_candidate


def candidate(start=0, end=30):
    return {"start_seconds": start, "end_seconds": end}


def test_final_score_uses_weighted_editorial_scores():
    evaluation = {
        "scores": {
            "hook": 10,
            "cliffhanger": 8,
            "emotional_intensity": 6,
            "standalone_clarity": 9,
        }
    }
    assert final_score(evaluation) == pytest.approx(84.0)


@pytest.mark.parametrize("start,end", [(0, 20), (10, 70)])
def test_valid_candidate_accepts_duration_boundaries(start, end):
    assert validate_candidate(candidate(start, end), episode_duration=70) == []


@pytest.mark.parametrize("start,end", [(0, 19), (0, 61)])
def test_invalid_candidate_rejects_duration_outside_range(start, end):
    assert "Duration must be between 20 and 60 seconds" in validate_candidate(candidate(start, end))


def test_validation_rejects_negative_start():
    assert "Start timestamp is negative" in validate_candidate(candidate(-1, 25))


def test_validation_rejects_candidate_beyond_episode_duration():
    assert "End timestamp exceeds episode duration" in validate_candidate(
        candidate(40, 65), episode_duration=60
    )


def test_validation_reports_missing_timestamps():
    assert validate_candidate({}, episode_duration=100) == ["Missing start/end timestamp"]
