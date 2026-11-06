"""Editorial ranking utilities with deterministic quality gating and diversity selection."""


def temporal_overlap_ratio(a, b):
    """Intersection divided by the shorter clip duration (0.0 to 1.0)."""
    if a.get("episode") != b.get("episode"):
        return 0.0
    a_start, a_end = float(a["start_seconds"]), float(a["end_seconds"])
    b_start, b_end = float(b["start_seconds"]), float(b["end_seconds"])
    intersection = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return intersection / shorter if shorter > 0 else 0.0


def _rank_value(candidate):
    score = candidate.get("final_score")
    if score is not None:
        return float(score)
    if candidate.get("evaluation_mode") == "failed":
        return -1.0
    return float(candidate.get("heuristic_score", 0.0))


def _editorial_exclusion_reason(candidate):
    """Return an exclusion reason unless the evaluator explicitly approved the clip."""
    evaluation = candidate.get("evaluation") or {}
    recommendation = str(evaluation.get("recommendation", "")).strip().lower()

    if recommendation == "reject":
        return "editorial_reject"
    if recommendation not in {"strong", "consider"}:
        return "editorial_approval_missing_or_invalid"
    return None


def select_diverse_candidates(candidates, overlap_threshold=0.5, max_per_episode=3):
    """Apply editorial approval, then greedy NMS and a per-episode diversity cap.

    Only candidates explicitly marked `strong` or `consider` are eligible.
    `reject` and missing/unknown recommendations are retained in the returned
    suppressed/audit list with an editorial exclusion reason.

    A candidate is suppressed for overlap when at least `overlap_threshold` of
    its own duration overlaps an already selected, higher-ranked candidate in
    the same episode. Returns (selected, suppressed) without mutating inputs.
    """
    ordered = sorted(candidates, key=_rank_value, reverse=True)
    selected, suppressed = [], []
    eligible = []

    for candidate in ordered:
        exclusion_reason = _editorial_exclusion_reason(candidate)
        if exclusion_reason:
            item = dict(candidate)
            item["selection_status"] = "excluded"
            item["suppression"] = {
                "reason": exclusion_reason,
                "overlap_ratio": 0.0,
                "suppressed_by": None
            }
            suppressed.append(item)
        else:
            eligible.append(candidate)

    episode_counts = {}
    for candidate in eligible:
        reason = None
        for kept in selected:
            overlap = temporal_overlap_ratio(candidate, kept)
            if overlap >= overlap_threshold:
                reason = {
                    "reason": "temporal_overlap",
                    "overlap_ratio": round(overlap, 4),
                    "suppressed_by": kept.get("candidate_id")
                }
                break

        if reason is None:
            episode = candidate.get("episode", "Unknown")
            if episode_counts.get(episode, 0) >= max_per_episode:
                reason = {
                    "reason": "episode_limit",
                    "overlap_ratio": 0.0,
                    "suppressed_by": None
                }

        if reason:
            item = dict(candidate)
            item["selection_status"] = "suppressed"
            item["suppression"] = reason
            suppressed.append(item)
        else:
            item = dict(candidate)
            item["selection_status"] = "selected"
            item["suppression"] = None
            selected.append(item)
            episode = candidate.get("episode", "Unknown")
            episode_counts[episode] = episode_counts.get(episode, 0) + 1

    selected.sort(key=_rank_value, reverse=True)
    return selected, suppressed
