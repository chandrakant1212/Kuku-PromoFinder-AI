import re
from pathlib import Path

TIME_RE = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?(?!\d)")

def timestamp_to_seconds(value: str) -> float:
    match = TIME_RE.search(value)
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")
    minutes, seconds, fraction = match.groups()
    return int(minutes) * 60 + int(seconds) + (float("0." + fraction) if fraction else 0.0)

def _first(pattern, text, default=None, flags=re.I | re.M):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else default

def parse_screenplay(text: str, filename: str = "pasted_screenplay.txt") -> dict:
    """Parse the screenplay's metadata, scenes, and timed screenplay events."""
    episode = _first(r"^EPISODE NUMBER:\s*(.+)$", text)
    logline = _first(r"^EPISODE LOGLINE:\s*(.+)$", text)
    continuity = _first(r"^CONTINUITY NOTES:\s*(.+)$", text)

    # Scene headings in this input pack use SCENE 01, followed by Scene heading/start/end.
    scene_matches = list(re.finditer(r"(?im)^SCENE\s+(\d+)\s*$", text))
    scenes = []
    for index, match in enumerate(scene_matches):
        block_end = scene_matches[index + 1].start() if index + 1 < len(scene_matches) else len(text)
        block = text[match.start():block_end]
        scene_number = int(match.group(1))
        heading = _first(r"^(?:Scene heading|SCENE HEADING):\s*(.+)$", block)
        start_raw = _first(r"^(?:Scene start|SCENE START):\s*([0-9:.]+)", block)
        end_raw = _first(r"^(?:Scene end|SCENE END):\s*([0-9:.]+)", block)

        events = []
        # Each timed block begins with a bold label, followed by Start/End and descriptive text.
        event_pattern = re.compile(
            r"(?ims)^\*\*(.+?):\*\*\s*\n\s*Start:\s*\(?([0-9:.]+)\)?\s*\|\s*End:\s*\(?([0-9:.]+)\)?\s*\n(.*?)(?=^\*\*.+?:\*\*\s*$|^SCENE\s+\d+\s*$|\Z)"
        )
        for event_match in event_pattern.finditer(block):
            label = event_match.group(1).strip()
            start_s, end_s = event_match.group(2), event_match.group(3)
            description = event_match.group(4).strip()
            try:
                start_sec = timestamp_to_seconds(start_s)
                end_sec = timestamp_to_seconds(end_s)
            except ValueError:
                continue
            events.append({
                "type": label,
                "start": start_s,
                "end": end_s,
                "start_seconds": start_sec,
                "end_seconds": end_sec,
                "duration_seconds": round(end_sec - start_sec, 3),
                "description": description
            })

        scenes.append({
            "scene_number": scene_number,
            "heading": heading,
            "start": start_raw,
            "end": end_raw,
            "start_seconds": timestamp_to_seconds(start_raw) if start_raw else None,
            "end_seconds": timestamp_to_seconds(end_raw) if end_raw else None,
            "events": events
        })

    return {
        "source_file": Path(filename).name,
        "episode": episode or Path(filename).stem,
        "logline": logline,
        "continuity_notes": continuity,
        "scene_count": len(scenes),
        "event_count": sum(len(s["events"]) for s in scenes),
        "scenes": scenes,
        "raw_text": text
    }

def parse_many(items):
    """items: iterable of (filename, text)."""
    parsed, errors = [], []
    for filename, text in items:
        try:
            result = parse_screenplay(text, filename)
            if not result["scenes"]:
                errors.append({"file": filename, "error": "No scene headings found"})
            else:
                parsed.append(result)
        except Exception as exc:
            errors.append({"file": filename, "error": str(exc)})
    return parsed, errors
