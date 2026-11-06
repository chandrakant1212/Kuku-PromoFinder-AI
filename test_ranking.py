import pytest

from src.ranking import select_diverse_candidates, temporal_overlap_ratio


def item(cid, ep, start, end, score, recommendation="consider"):
    return {
        "candidate_id": cid,
        "episode": ep,
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": end - start,
        "final_score": score,
        "evaluation_mode": "gemini",
        "evaluation": {"recommendation": recommendation},
    }


def test_temporal_overlap_is_calculated_against_shorter_clip():
    a = item("a", "Episode 1", 0, 30, 90)
    b = item("b", "Episode 1", 10, 35, 80)
    assert temporal_overlap_ratio(a, b) == pytest.approx(20 / 25)


def test_candidates_from_different_episodes_do_not_overlap():
    a = item("a", "Episode 1", 0, 30, 90)
    b = item("b", "Episode 2", 10, 35, 80)
    assert temporal_overlap_ratio(a, b) == 0.0


def test_nms_suppresses_lower_ranked_overlapping_candidate():
    items = [
        item("a", "Episode 1", 0, 30, 90),
        item("b", "Episode 1", 10, 35, 80),
        item("c", "Episode 2", 10, 35, 80),
    ]
    kept, dropped = select_diverse_candidates(items, 0.5, 3)
    assert {x["candidate_id"] for x in kept} == {"a", "c"}
    assert dropped[0]["candidate_id"] == "b"
    assert dropped[0]["suppression"]["reason"] == "temporal_overlap"


def test_per_episode_cap_suppresses_extra_non_overlapping_candidates():
    items = [item(str(i), "Episode 1", i * 40, i * 40 + 25, 90 - i) for i in range(4)]
    kept, dropped = select_diverse_candidates(items, 0.5, 2)
    assert len(kept) == 2
    assert len(dropped) == 2
    assert all(x["suppression"]["reason"] == "episode_limit" for x in dropped)


def test_reject_is_excluded_even_when_its_numeric_score_is_high():
    items = [
        item("approved", "Episode 1", 0, 25, 70, "consider"),
        item("rejected", "Episode 2", 0, 25, 99, "reject"),
    ]
    kept, excluded = select_diverse_candidates(items)
    assert [x["candidate_id"] for x in kept] == ["approved"]
    assert excluded[0]["candidate_id"] == "rejected"
    assert excluded[0]["selection_status"] == "excluded"
    assert excluded[0]["suppression"]["reason"] == "editorial_reject"


@pytest.mark.parametrize("recommendation", ["strong", "consider", " STRONG ", "Consider"])
def test_strong_and_consider_recommendations_are_eligible(recommendation):
    kept, excluded = select_diverse_candidates([
        item("approved", "Episode 1", 0, 25, 80, recommendation)
    ])
    assert [x["candidate_id"] for x in kept] == ["approved"]
    assert excluded == []


@pytest.mark.parametrize("recommendation", [None, "", "unknown", "pending"])
def test_missing_or_invalid_recommendation_is_excluded(recommendation):
    candidate = item("unclear", "Episode 1", 0, 25, 100)
    candidate["evaluation"]["recommendation"] = recommendation
    kept, excluded = select_diverse_candidates([candidate])
    assert kept == []
    assert excluded[0]["suppression"]["reason"] == "editorial_approval_missing_or_invalid"


def test_selection_does_not_mutate_input_candidates():
    original = item("a", "Episode 1", 0, 30, 90)
    select_diverse_candidates([original])
    assert "selection_status" not in original
    assert "suppression" not in original
