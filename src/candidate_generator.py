import re
from collections import defaultdict

DRAMA_TERMS = {
    "betrayal": ["betray", "cheat", "affair", "abandon", "stole", "lied", "deceived"],
    "conflict": ["hate", "kill", "leave", "never", "cannot", "won't", "threat", "enemy", "revenge"],
    "reveal": ["secret", "truth", "identity", "real", "discover", "confess", "revealed", "actually"],
    "emotion": ["tears", "cry", "love", "heart", "desperate", "humiliated", "shocked", "terrified"],
    "power": ["duke", "queen", "king", "heir", "inherit", "wealth", "marry", "wedding", "throne"]
}


def format_mmss(seconds):
    seconds = max(0.0, float(seconds))
    minutes = int(seconds // 60)
    remain = seconds - minutes * 60
    return f"{minutes:02d}:{remain:05.2f}"


def collect_events(ep):
    events = []
    for scene in ep.get("scenes", []):
        for event in scene.get("events", []):
            if event.get("start_seconds") is None or event.get("end_seconds") is None:
                continue
            if event["end_seconds"] <= event["start_seconds"]:
                continue
            events.append({**event, "scene_number": scene["scene_number"], "scene_heading": scene.get("heading")})
    return sorted(events, key=lambda e: (e["start_seconds"], e["end_seconds"]))


def _excerpt_for_range(events, start, end):
    lines = []
    included = []
    for event in events:
        left = max(float(event["start_seconds"]), start)
        right = min(float(event["end_seconds"]), end)
        if right <= left:
            continue
        included.append(event)
        # Clip displayed event boundaries to the candidate interval.
        lines.append(f"[{format_mmss(left)}-{format_mmss(right)}] {event['type']}: {event.get('description', '')}")
    return "\n".join(lines), included


def build_candidate(ep, events, start, end, method="gemini_discovery", rationale=""):
    excerpt, overlapping = _excerpt_for_range(events, start, end)
    episode = ep.get("episode", "Episode")
    digits = re.findall(r"\d+", str(episode))
    ep_id = digits[-1] if digits else re.sub(r"\W+", "", str(episode))[:12]
    return {
        "candidate_id": f"E{ep_id}_{int(round(start*100)):06d}_{int(round(end*100)):06d}",
        "episode": episode,
        "source_file": ep.get("source_file"),
        "start_seconds": round(start, 2),
        "end_seconds": round(end, 2),
        "start_timestamp": format_mmss(start),
        "end_timestamp": format_mmss(end),
        "duration_seconds": round(end-start, 2),
        "scenes": sorted(set(e["scene_number"] for e in overlapping)),
        "scene_headings": sorted(set(e.get("scene_heading") or "" for e in overlapping)),
        "screenplay_excerpt": excerpt,
        "discovery_method": method,
        "discovery_rationale": rationale,
        "heuristic_score": round(_heuristic_score(excerpt), 2)
    }


def _heuristic_score(text):
    lower = text.lower()
    hits = sum(lower.count(term) for terms in DRAMA_TERMS.values() for term in terms)
    dialogue = len(re.findall(r"\]\s+[^:]+:", text))
    categories = sum(any(term in lower for term in terms) for terms in DRAMA_TERMS.values())
    return hits * 1.4 + dialogue * 1.2 + categories * 1.5


def generate_candidates(episodes, max_per_episode=8):
    """Heuristic baseline retained as a fallback and comparison method."""
    all_candidates = []
    for ep in episodes:
        events = collect_events(ep)
        if not events:
            continue
        episode_end = max([s.get("end_seconds") or 0 for s in ep.get("scenes", [])] + [e["end_seconds"] for e in events])
        proposals = {}
        for event in events:
            start = float(event["start_seconds"])
            for duration in (25, 35, 45, 55):
                end = min(start + duration, episode_end)
                if not 20 <= end-start <= 60:
                    continue
                key = (round(start, 2), round(end, 2))
                if key not in proposals:
                    candidate = build_candidate(ep, events, *key, method="heuristic")
                    proposals[key] = candidate
        ranked = sorted(proposals.values(), key=lambda x: x["heuristic_score"], reverse=True)
        selected = []
        for candidate in ranked:
            if all(_overlap_ratio(candidate, old) < 0.65 for old in selected):
                selected.append(candidate)
            if len(selected) >= max_per_episode:
                break
        all_candidates.extend(selected)
    return sorted(all_candidates, key=lambda x: x["heuristic_score"], reverse=True)


def _overlap_ratio(a, b):
    overlap = max(0, min(a["end_seconds"], b["end_seconds"]) - max(a["start_seconds"], b["start_seconds"]))
    return overlap / max(0.01, min(a["duration_seconds"], b["duration_seconds"]))


def deduplicate_candidates(candidates, max_per_episode=8):
    output = []
    by_episode = defaultdict(list)
    for candidate in sorted(candidates, key=lambda x: x.get("heuristic_score", 0), reverse=True):
        selected = by_episode[candidate["episode"]]
        if len(selected) >= max_per_episode:
            continue
        if all(_overlap_ratio(candidate, old) < 0.65 for old in selected):
            selected.append(candidate)
    for group in by_episode.values():
        output.extend(group)
    return sorted(output, key=lambda x: x.get("heuristic_score", 0), reverse=True)
