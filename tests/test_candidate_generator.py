from src.candidate_generator import build_candidate, collect_events


def sample_episode():
    return {
        "episode": "Episode 2",
        "source_file": "episode_2.txt",
        "scenes": [{
            "scene_number": 1,
            "heading": "INT. HOUSE - NIGHT",
            "events": [{
                "type": "Reveal",
                "start": "00:00",
                "end": "00:40",
                "start_seconds": 0,
                "end_seconds": 40,
                "duration_seconds": 40,
                "description": "A hidden secret is revealed.",
            }],
        }],
    }


def test_collect_events_adds_scene_metadata_and_sorts_events():
    events = collect_events(sample_episode())
    assert len(events) == 1
    assert events[0]["scene_number"] == 1
    assert events[0]["scene_heading"] == "INT. HOUSE - NIGHT"


def test_build_candidate_clips_event_excerpt_to_candidate_window():
    episode = sample_episode()
    events = collect_events(episode)
    result = build_candidate(episode, events, 10, 30)
    assert result["duration_seconds"] == 20
    assert "[00:10.00-00:30.00]" in result["screenplay_excerpt"]
    assert result["episode"] == "Episode 2"
    assert result["scenes"] == [1]
