import json
import os
import re
import time


# Shared process-wide request pacing for BOTH discovery and evaluation.
# 5.5 seconds/request keeps this process below the documented 15 RPM ceiling.
_MIN_REQUEST_INTERVAL = float(os.getenv("GEMINI_MIN_REQUEST_INTERVAL", "5.5"))
_LAST_REQUEST_AT = 0.0

def _retry_delay_seconds(message):
    """Extract Gemini's suggested retry delay from common SDK error formats."""
    patterns = [
        r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*s",
        r"'retryDelay'\s*:\s*'([0-9]+(?:\.[0-9]+)?)s'",
        r'"retryDelay"\s*:\s*"([0-9]+(?:\.[0-9]+)?)s"',
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.I)
        if match:
            return float(match.group(1))
    return None

def _paced_generate_content(client, *, model, contents, config, max_retries=4):
    """Rate-limit all Gemini calls and honor server-provided retry delays."""
    global _LAST_REQUEST_AT
    last_error = None
    for attempt in range(max_retries):
        now = time.monotonic()
        wait_for_slot = _MIN_REQUEST_INTERVAL - (now - _LAST_REQUEST_AT)
        if wait_for_slot > 0:
            time.sleep(wait_for_slot)
        _LAST_REQUEST_AT = time.monotonic()
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:
            last_error = exc
            message = str(exc)
            lowered = message.lower()
            transient = any(term in lowered for term in [
                "429", "resource_exhausted", "503", "500", "502", "504",
                "unavailable", "deadline", "temporarily"
            ])
            if not transient or attempt == max_retries - 1:
                break
            suggested = _retry_delay_seconds(message)
            if "429" in lowered or "resource_exhausted" in lowered:
                # If no explicit server hint exists, wait a full minute.
                time.sleep(max(suggested or 60.0, 5.5))
            else:
                time.sleep(max(suggested or (2 ** (attempt + 1)), 5.5))
    raise RuntimeError(f"Gemini request failed after {max_retries} attempts: {last_error}")

SYSTEM_PROMPT = """You are a promotional editor for vertical microdrama series.
Evaluate screenplay segments as short-form social video promos. A strong promo:
1) has a compelling hook within its first 3 seconds,
2) ends on an unresolved cliffhanger,
3) is understandable to someone who has never watched the show,
4) contains emotionally engaging story material.
Do not invent dialogue, events, timestamps, or visual details. Judge only the supplied screenplay excerpt.
Be candid: weak candidates should receive low scores. Return valid JSON only."""

def _extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end+1]
    return json.loads(text)

def evaluate_with_gemini(candidate, api_key=None, model=None, max_retries=3):
    """Evaluate a candidate using Gemini. Reads key/model from env if not supplied."""
    key = api_key or os.getenv("GEMINI_API_KEY")
    model_name = model or os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    if not key:
        raise RuntimeError(
    "GEMINI_API_KEY is missing. Configure it in your environment, "
    ".env file, or Streamlit Cloud Secrets."
        )
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install google-genai: pip install google-genai") from exc

    client = genai.Client(api_key=key)
    prompt = f"""Evaluate this candidate promo.

Episode: {candidate['episode']}
Time range: {candidate['start_timestamp']} to {candidate['end_timestamp']}
Duration: {candidate['duration_seconds']} seconds
Episode context: {candidate.get('episode_logline', '')}
Continuity notes: {candidate.get('continuity_notes', '')}

Screenplay excerpt:
{candidate['screenplay_excerpt']}

Return exactly this JSON structure:
{{
  "hook": "specific opening hook, or explain if weak",
  "cliffhanger": "specific unresolved ending, or explain if weak",
  "standalone_clarity": "what a new viewer understands and what context is missing",
  "why_it_works": "one concise sentence",
  "scores": {{
    "hook": 0,
    "cliffhanger": 0,
    "emotional_intensity": 0,
    "standalone_clarity": 0
  }},
  "recommendation": "strong|consider|reject",
  "risks": ["specific issue, if any"]
}}
Scores must be integers from 0 to 10. Do not change the supplied timestamps.
Do not award high scores merely because dramatic keywords appear. Evaluate the narrative sequence."""

    last_error = None
    for attempt in range(1):
        try:
            response = _paced_generate_content(
                client,
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                    response_mime_type="application/json"
                ),
                max_retries=max_retries
            )
            result = _extract_json(response.text)
            scores = result.get("scores", {})
            for key_name in ["hook", "cliffhanger", "emotional_intensity", "standalone_clarity"]:
                value = scores.get(key_name)
                if not isinstance(value, (int, float)) or not 0 <= value <= 10:
                    raise ValueError(f"Invalid score for {key_name}: {value}")
            result["evaluation_mode"] = "gemini"
            result["model"] = model_name
            return result
        except Exception as exc:
            last_error = exc
            message = str(exc).lower()
            transient = any(term in message for term in ["503", "429", "500", "502", "504", "unavailable", "resource_exhausted", "deadline"])
            if not transient or attempt == max_retries - 1:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Gemini evaluation failed after retries: {last_error}")

def evaluate_heuristically(candidate):
    """Fallback for pipeline testing only; not a semantic editorial judgment."""
    text = candidate.get("screenplay_excerpt", "").lower()
    hook_hits = sum(term in text[:700] for term in ["why", "what", "you", "never", "cannot", "can't", "look"])
    cliff_hits = sum(term in text[-700:] for term in ["but", "unless", "wait", "secret", "truth", "who", "suddenly"])
    drama_hits = sum(term in text for term in ["betray", "cheat", "abandon", "tears", "cry", "kill", "love", "revenge", "humiliated", "shocked"])
    scores = {
        "hook": min(10, 4 + hook_hits),
        "cliffhanger": min(10, 3 + cliff_hits),
        "emotional_intensity": min(10, 3 + drama_hits),
        "standalone_clarity": 5
    }
    return {
        "hook": "Heuristic estimate only; review the opening manually.",
        "cliffhanger": "Heuristic estimate only; review the ending manually.",
        "standalone_clarity": "Not assessed semantically without an LLM.",
        "why_it_works": "Contains screenplay signals associated with dramatic conflict; this is not an AI editorial judgment.",
        "scores": scores,
        "recommendation": "consider",
        "risks": ["Heuristic fallback: semantic quality has not been verified."],
        "evaluation_mode": "heuristic_fallback"
    }

DISCOVERY_SYSTEM_PROMPT = """You are a senior short-form drama promo editor. Find self-contained 20–60 second promotional moments in the supplied screenplay events. Prefer a strong opening hook, escalating emotional or physical conflict, a reveal/reversal, and an unresolved ending. Use only supplied events. Do not invent dialogue, actions, or timestamps. Return valid JSON only."""


def discover_with_gemini(episode, max_events_per_chunk=70, overlap_events=10, max_candidates_per_chunk=3):
    """Discover promo ranges from screenplay event IDs; Python resolves all timestamps."""
    key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it to your .env file.")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("Install google-genai: pip install google-genai") from exc

    from src.candidate_generator import collect_events, build_candidate
    events = collect_events(episode)
    if not events:
        return []
    client = genai.Client(api_key=key)
    step = max(1, max_events_per_chunk - overlap_events)
    discovered = []
    for chunk_start in range(0, len(events), step):
        chunk = events[chunk_start:chunk_start + max_events_per_chunk]
        if not chunk:
            break
        payload_events = []
        for local_i, event in enumerate(chunk):
            payload_events.append({
                "event_id": f"EV{chunk_start + local_i}",
                "start": event["start"], "end": event["end"],
                "type": event["type"], "text": event.get("description", "")[:700]
            })
        prompt = f"""Discover up to {max_candidates_per_chunk} distinct promo moments for {episode.get('episode','this episode')}.
Return JSON: {{"candidates":[{{"start_event_id":"EVn","end_event_id":"EVm","reason":"brief editorial reason"}}]}}.
Rules:
- start_event_id and end_event_id must exactly match IDs below.
- The clip starts at the start event's start and ends at the end event's end.
- The resulting duration must be 20–60 seconds.
- Events must be in chronological order and from this supplied chunk.
- Select moments with a hook near the beginning and a compelling unresolved beat near the end.
- Prefer distinct moments; do not return multiple tiny variations of one moment.
- If no good moment exists, return an empty candidates array.

Events:
{json.dumps(payload_events, ensure_ascii=False)}"""
        last_error = None
        for attempt in range(1):
            try:
                response = _paced_generate_content(
                    client,
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=DISCOVERY_SYSTEM_PROMPT,
                        temperature=0.2, response_mime_type="application/json"
                    ),
                    max_retries=3
                )
                result = _extract_json(response.text)
                by_id = {f"EV{chunk_start+i}": event for i, event in enumerate(chunk)}
                for proposal in result.get("candidates", [])[:max_candidates_per_chunk]:
                    start_event = by_id.get(proposal.get("start_event_id"))
                    end_event = by_id.get(proposal.get("end_event_id"))
                    if not start_event or not end_event:
                        continue
                    start = float(start_event["start_seconds"])
                    end = float(end_event["end_seconds"])
                    if end_event["start_seconds"] < start or not 20 <= end-start <= 60:
                        continue
                    discovered.append(build_candidate(
                        episode, events, start, end,
                        method="gemini_discovery", rationale=str(proposal.get("reason", ""))[:500]
                    ))
                break
            except Exception as exc:
                last_error = exc
                raise RuntimeError(f"Gemini discovery failed for {episode.get('episode')}: {last_error}")
        if chunk_start + max_events_per_chunk >= len(events):
            break
    return discovered
