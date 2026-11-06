from src.ranking import select_diverse_candidates, temporal_overlap_ratio


def item(cid, ep, start, end, score):
    return {"candidate_id": cid, "episode": ep, "start_seconds": start,
            "end_seconds": end, "duration_seconds": end-start,
            "final_score": score, "evaluation_mode": "gemini"}

# Same-episode overlap is suppressed; different episodes are independent.
items = [item("a", "Episode 1", 0, 30, 90),
         item("b", "Episode 1", 10, 35, 80),
         item("c", "Episode 2", 10, 35, 80)]
kept, dropped = select_diverse_candidates(items, .5, 3)
assert {x["candidate_id"] for x in kept} == {"a", "c"}
assert dropped[0]["suppression"]["reason"] == "temporal_overlap"

# Per-episode cap works even for non-overlapping candidates.
items = [item(str(i), "Episode 1", i*40, i*40+25, 90-i) for i in range(4)]
kept, dropped = select_diverse_candidates(items, .5, 2)
assert len(kept) == 2 and len(dropped) == 2
assert all(x["suppression"]["reason"] == "episode_limit" for x in dropped)
print("All ranking unit tests passed")
