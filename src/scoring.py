def final_score(evaluation):
    scores = evaluation.get("scores", {})
    weights = {
        "hook": 0.30,
        "cliffhanger": 0.30,
        "emotional_intensity": 0.20,
        "standalone_clarity": 0.20
    }
    total = sum(float(scores.get(k, 0)) * w for k, w in weights.items())
    return round(total * 10, 1)  # normalized to 0–100

def validate_candidate(candidate, episode_duration=None):
    errors = []
    start = candidate.get("start_seconds")
    end = candidate.get("end_seconds")
    if start is None or end is None:
        errors.append("Missing start/end timestamp")
    else:
        duration = end - start
        if start < 0:
            errors.append("Start timestamp is negative")
        if duration < 20 or duration > 60:
            errors.append("Duration must be between 20 and 60 seconds")
        if episode_duration is not None and end > episode_duration:
            errors.append("End timestamp exceeds episode duration")
    return errors
