import io
import json
import os
import zipfile
import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.parser import parse_many
from src.candidate_generator import generate_candidates, deduplicate_candidates
from src.llm_analyzer import discover_with_gemini
from src.llm_analyzer import evaluate_with_gemini, evaluate_heuristically
from src.scoring import final_score, validate_candidate
from src.ranking import select_diverse_candidates


load_dotenv()

def load_runtime_secrets():
    """Load Streamlit Cloud secrets into environment variables."""

    # Local .env takes priority.
    if os.getenv("GEMINI_API_KEY"):
        return

    # Access Streamlit secrets only when a cloud key is needed.
    try:
        secrets = st.secrets
    except Exception:
        return

    for key in ["GEMINI_API_KEY", "GEMINI_MODEL", "GEMINI_MIN_REQUEST_INTERVAL"]:
        value = secrets.get(key)
        if value:
            os.environ[key] = str(value)


load_runtime_secrets()

CHECKPOINT_PATH = Path("data/run_checkpoint.json")

def _fingerprint_episodes(episodes):
    payload = json.dumps(episodes, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def _load_checkpoint(fingerprint):
    try:
        data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        if data.get("fingerprint") == fingerprint:
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"fingerprint": fingerprint, "discovered_by_episode": {}, "evaluations": {}}

def _save_checkpoint(data):
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CHECKPOINT_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(CHECKPOINT_PATH)

def _balanced_evaluation_batch(candidates, limit):
    """Choose high-heuristic candidates while cycling across episodes."""
    groups = {}
    for candidate in candidates:
        groups.setdefault(candidate.get("episode", "Unknown"), []).append(candidate)
    for episode in groups:
        groups[episode].sort(key=lambda x: float(x.get("heuristic_score", 0)), reverse=True)
    selected = []
    episode_names = sorted(groups)
    while len(selected) < limit:
        added = False
        for episode in episode_names:
            if groups[episode] and len(selected) < limit:
                selected.append(groups[episode].pop(0))
                added = True
        if not added:
            break
    return selected
st.set_page_config(page_title="Kuku PromoFinder AI", page_icon="🎬", layout="wide")
st.title("🎬 Kuku PromoFinder AI")
st.caption("Screenplay ingestion + Gemini-assisted discovery + editorial evaluation")
st.caption("Reliability: paced Gemini requests, retry-delay handling, and resumable local checkpoints.")

def read_zip(uploaded):
    with zipfile.ZipFile(io.BytesIO(uploaded.getvalue())) as archive:
        return [
            (Path(name).name, archive.read(name).decode("utf-8-sig", errors="replace"))
            for name in archive.namelist()
            if name.lower().endswith(".txt") and not name.endswith("/")
        ]

mode = st.radio("Input method", ["Upload ZIP", "Upload TXT files", "Paste screenplay text"], horizontal=True)
items = []

if mode == "Upload ZIP":
    f = st.file_uploader("Upload ZIP containing screenplay TXT files", type=["zip"])
    if f:
        try:
            items = read_zip(f)
            st.success(f"Found {len(items)} screenplay files.")
        except zipfile.BadZipFile:
            st.error("Invalid ZIP file.")
elif mode == "Upload TXT files":
    files = st.file_uploader("Upload screenplay TXT files", type=["txt"], accept_multiple_files=True)
    if files:
        items = [(f.name, f.getvalue().decode("utf-8-sig", errors="replace")) for f in files]
else:
    pasted = st.text_area("Paste screenplay text", height=300)
    label = st.text_input("Episode/file label", "Pasted Episode")
    if pasted.strip():
        items = [(label.strip() + ".txt", pasted)]

if st.button("Parse screenplays", type="primary", disabled=not items):
    parsed, errors = parse_many(items)
    st.session_state["parsed"] = parsed
    st.session_state["parse_errors"] = errors
    st.session_state.pop("candidates", None)

if "parsed" in st.session_state:
    parsed = st.session_state["parsed"]
    errors = st.session_state.get("parse_errors", [])
    a, b, c = st.columns(3)
    a.metric("Episodes parsed", len(parsed))
    b.metric("Scenes", sum(x["scene_count"] for x in parsed))
    c.metric("Timed events", sum(x["event_count"] for x in parsed))
    if errors:
        st.warning(f"{len(errors)} file(s) could not be fully parsed.")
        st.dataframe(pd.DataFrame(errors), use_container_width=True)

    with st.expander("View screenplay parsing summary"):
        st.dataframe(pd.DataFrame([{
            "Episode": x["episode"], "File": x["source_file"],
            "Scenes": x["scene_count"], "Timed events": x["event_count"],
            "Logline": x.get("logline", "")
        } for x in parsed]), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Promo Discovery")
    st.write("Generate candidate windows and evaluate them with Gemini.")
    env_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
    if env_key:
       st.success(f"Gemini API configured · Model: {model}")
    else:
       st.warning(
        "GEMINI_API_KEY not found. Configure it in your local .env "
        "file or Streamlit Cloud Secrets."
    )
    
    discovery_method = st.radio(
        "Candidate discovery method",
        ["Gemini-assisted discovery (recommended)", "Heuristic baseline (comparison/fallback)"],
        horizontal=True
    )
    max_per_ep = st.slider("Maximum discovered candidates per episode", 2, 12, 6)
    evaluation_limit = st.slider("Maximum candidates to evaluate with Gemini", 1, 60, 20)
    st.caption("This is the maximum number of NEW pending candidates evaluated per run. Previously successful evaluations are reused from the checkpoint.")
    episode_limit = st.slider("Episodes to process in this run", 1, len(parsed), len(parsed))
    use_fallback = st.checkbox("Allow heuristic scoring if Gemini evaluation fails", value=False)
    st.markdown("**Final recommendation diversity**")
    overlap_threshold = st.slider("Suppress candidates when this share of the shorter clip overlaps", 0.30, 0.90, 0.50, 0.05)
    max_final_per_episode = st.slider("Maximum final recommendations per episode", 1, 10, 3)

    st.info("Resume behavior: keep the same screenplay input and click the run button again. Cached discovery and successful Gemini evaluations are reused; the next run evaluates the next pending candidates.")

    if st.button("Discover and evaluate promos", type="primary"):
        selected_episodes = parsed[:episode_limit]
        fingerprint = _fingerprint_episodes(selected_episodes)
        checkpoint = _load_checkpoint(fingerprint)
        candidates = []
        discovery_errors = []
        discovery_progress = st.progress(0)
        discovery_status = st.empty()
        if discovery_method.startswith("Gemini"):
            for index, ep in enumerate(selected_episodes):
                episode_name = ep["episode"]
                discovery_status.write(f"Gemini discovering moments · {episode_name} ({index+1}/{len(selected_episodes)})")
                cached = checkpoint["discovered_by_episode"].get(episode_name)
                if cached is not None:
                    candidates.extend(cached)
                else:
                    try:
                        found = discover_with_gemini(ep)
                        checkpoint["discovered_by_episode"][episode_name] = found
                        _save_checkpoint(checkpoint)
                        candidates.extend(found)
                    except Exception as exc:
                        discovery_errors.append({"episode": episode_name, "error": str(exc)})
                discovery_progress.progress((index + 1) / max(1, len(selected_episodes)))
            candidates = deduplicate_candidates(candidates, max_per_episode=max_per_ep)
        else:
            with st.spinner("Generating heuristic candidate windows..."):
                candidates = generate_candidates(selected_episodes, max_per_episode=max_per_ep)
        discovery_status.write(f"Discovery complete · {len(candidates)} valid candidate(s) found.")
        if discovery_errors:
            st.warning(f"Discovery failed for {len(discovery_errors)} episode(s). Other episodes continue to be processed.")
            st.dataframe(pd.DataFrame(discovery_errors), use_container_width=True)

        ep_lookup = {x["episode"]: x for x in selected_episodes}
        for candidate in candidates:
            ep = ep_lookup.get(candidate["episode"], {})
            candidate["episode_logline"] = ep.get("logline", "")
            candidate["continuity_notes"] = ep.get("continuity_notes", "")
            candidate["validation_errors"] = validate_candidate(
                candidate,
                episode_duration=max([sc.get("end_seconds") or 0 for sc in ep.get("scenes", [])] + [0])
            )
        candidates = [x for x in candidates if not x["validation_errors"]]
        candidates.sort(key=lambda x: x["heuristic_score"], reverse=True)
        st.session_state["discovery_errors"] = discovery_errors
        st.session_state["discovery_summary"] = {
            "method": discovery_method,
            "episodes_processed": len(selected_episodes),
            "candidates_found": len(candidates)
        }

        # Resume-aware batching: only candidates without a successful checkpointed
        # Gemini evaluation are eligible for this run's evaluation budget.
        pending_candidates = [
            x for x in candidates
            if checkpoint["evaluations"].get(
                x.get("candidate_id", f"{x['episode']}_{x['start_seconds']}")
            ) is None
        ]
        selected = _balanced_evaluation_batch(pending_candidates, evaluation_limit)
        selected_ids = {
            x.get("candidate_id", f"{x['episode']}_{x['start_seconds']}")
            for x in selected
        }
        evaluated = []
        progress = st.progress(0)
        status = st.empty()
        processed_new = 0

        for candidate in candidates:
            candidate_id = candidate.get(
                "candidate_id", f"{candidate['episode']}_{candidate['start_seconds']}"
            )
            cached_evaluation = checkpoint["evaluations"].get(candidate_id)

            if cached_evaluation is not None:
                evaluation = cached_evaluation
            elif candidate_id in selected_ids:
                processed_new += 1
                status.write(
                    f"Evaluating pending candidate {processed_new} of {len(selected)} · "
                    f"{candidate['episode']}"
                )
                try:
                    evaluation = evaluate_with_gemini(candidate)
                    # Persist only successful Gemini evaluations. Failed calls remain
                    # pending so a later run can retry them without losing prior work.
                    if evaluation.get("evaluation_mode") == "gemini":
                        checkpoint["evaluations"][candidate_id] = evaluation
                        _save_checkpoint(checkpoint)
                except Exception as exc:
                    candidate["gemini_error"] = str(exc)
                    if use_fallback:
                        evaluation = evaluate_heuristically(candidate)
                        evaluation["risks"].append(
                            "Gemini call failed; heuristic fallback used."
                        )
                    else:
                        evaluation = {
                            "hook": "Not evaluated",
                            "cliffhanger": "Not evaluated",
                            "standalone_clarity": "Not evaluated",
                            "why_it_works": "Gemini evaluation failed; retry this run later.",
                            "scores": {},
                            "recommendation": "pending",
                            "risks": [str(exc)],
                            "evaluation_mode": "failed"
                        }
                progress.progress(processed_new / max(1, len(selected)))
            else:
                evaluation = None

            candidate["evaluation"] = evaluation
            candidate["evaluation_mode"] = (
                evaluation.get("evaluation_mode", "unknown")
                if evaluation else "not_evaluated"
            )
            candidate["final_score"] = (
                final_score(evaluation) if evaluation and evaluation.get("scores") else None
            )
            evaluated.append(candidate)

        status.write(
            f"Evaluation pass complete · {processed_new} pending candidate(s) attempted · "
            f"{sum(x.get('evaluation_mode') == 'gemini' for x in evaluated)} total Gemini evaluations."
        )
        evaluated.sort(key=lambda x: (x["final_score"] is not None, x["final_score"] or -1), reverse=True)
        # Keep every discovered candidate for auditability, but produce a separate
        # non-overlapping, episode-diverse recommendation list for editors.
        rankable = [
            x for x in evaluated
            if x.get("evaluation_mode") in ("gemini", "heuristic_fallback")
            and x.get("final_score") is not None
        ]
        final_candidates, suppressed_candidates = select_diverse_candidates(
            rankable,
            overlap_threshold=overlap_threshold,
            max_per_episode=max_final_per_episode
        )
        # Failed and unevaluated items remain in the complete raw output, never the final ranked list.
        st.session_state["all_candidates"] = evaluated
        st.session_state["candidates"] = final_candidates
        st.session_state["suppressed_candidates"] = suppressed_candidates
        st.session_state["ranking_settings"] = {
        "overlap_threshold": overlap_threshold,
        "max_final_per_episode": max_final_per_episode,
        "editorial_policy": {
        "eligible_recommendations": ["strong", "consider"],
        "excluded_recommendations": ["reject", "missing_or_invalid"]
        }
    }


if "candidates" in st.session_state:
    candidates = st.session_state["candidates"]
    all_candidates = st.session_state.get("all_candidates", candidates)
    gemini_count = sum(x.get("evaluation_mode") == "gemini" for x in all_candidates)
    fallback_count = sum(x.get("evaluation_mode") == "heuristic_fallback" for x in all_candidates)
    pending_count = sum(x.get("evaluation_mode") == "not_evaluated" for x in all_candidates)
    suppressed = st.session_state.get("suppressed_candidates", [])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Gemini evaluated", gemini_count)
    c2.metric("Heuristic fallback", fallback_count)
    c3.metric("Pending", pending_count)
    c4.metric("Excluded / suppressed", len(suppressed))
    if st.session_state.get("discovery_summary"):
        st.caption(f"Discovery: {st.session_state['discovery_summary']['method']} · "
                   f"Episodes processed: {st.session_state['discovery_summary']['episodes_processed']} · "
                   f"Candidates found: {st.session_state['discovery_summary']['candidates_found']}")

    rows = []
    for rank, x in enumerate(candidates, 1):
        ev = x.get("evaluation") or {}
        scores = ev.get("scores", {})
        rows.append({
            "Rank": rank,
            "Episode": x["episode"],
            "Start": x["start_timestamp"],
            "End": x["end_timestamp"],
            "Duration": x["duration_seconds"],
            "Score / 100": x["final_score"],
            "Hook": scores.get("hook", ""),
            "Cliffhanger": scores.get("cliffhanger", ""),
            "Evaluation": x.get("evaluation_mode")
        })
    st.subheader("Final diverse promo recommendations")
    settings = st.session_state.get("ranking_settings", {})
    st.caption(
    "Editorial gate: strong/consider only; reject or missing decisions excluded · "
    f"Non-maximum suppression: overlap ≥ {settings.get('overlap_threshold', 0.5):.0%} "
    f"of shorter clip · Maximum {settings.get('max_per_episode', settings.get('max_final_per_episode', 3))} "
    "recommendations per episode"
   )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for rank, x in enumerate(candidates[:20], 1):
        ev = x.get("evaluation")
        with st.expander(f"#{rank} · {x['episode']} · {x['start_timestamp']}–{x['end_timestamp']} · {x.get('final_score') if x.get('final_score') is not None else 'Not evaluated'}"):
            if ev:
                st.markdown(f"**Evaluation mode:** {x['evaluation_mode']}")
                st.markdown(f"**Recommendation:** {ev.get('recommendation', '')}")
                st.markdown(f"**Hook:** {ev.get('hook', '')}")
                st.markdown(f"**Cliffhanger:** {ev.get('cliffhanger', '')}")
                st.markdown(f"**Standalone clarity:** {ev.get('standalone_clarity', '')}")
                st.markdown(f"**Why it works:** {ev.get('why_it_works', '')}")
                st.markdown(f"**Risks:** {', '.join(ev.get('risks', [])) or 'None reported'}")
            else:
                st.info("Not yet evaluated by Gemini.")
            if x.get("discovery_rationale"):
                st.markdown(f"**Discovery rationale:** {x['discovery_rationale']}")
            st.markdown(f"**Scenes:** {x['scenes']} · **Duration:** {x['duration_seconds']} seconds")
            st.text(x["screenplay_excerpt"][:5000])
            if x.get("screenplay_excerpt"):
                st.caption("Excerpt event timestamps are clipped to the selected promo interval.")

    with st.expander(f"View {len(suppressed)} suppressed candidates and why they were excluded"):
        if suppressed:
            suppressed_rows = [{
                "Episode": x.get("episode"),
                "Start": x.get("start_timestamp"),
                "End": x.get("end_timestamp"),
                "Score": x.get("final_score"),
                "Reason": (x.get("suppression") or {}).get("reason"),
                "Overlap": (x.get("suppression") or {}).get("overlap_ratio"),
                "Suppressed by": (x.get("suppression") or {}).get("suppressed_by")
            } for x in suppressed]
            st.dataframe(pd.DataFrame(suppressed_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No candidates were suppressed in this run.")

    # Raw output retains all evaluated/discovered candidates and selection decisions.
    raw_payload = {
        "discovery_summary": st.session_state.get("discovery_summary", {}),
        "ranking_settings": st.session_state.get("ranking_settings", {}),
        "candidates": all_candidates,
        "suppressed_candidates": suppressed
    }
    raw = json.dumps(raw_payload, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("Download complete discovery output (JSON)", raw, "promo_candidates_raw.json", "application/json")
    final_json = json.dumps(candidates, ensure_ascii=False, indent=2).encode("utf-8")
    st.download_button("Download final diverse recommendations (JSON)", final_json, "final_promo_recommendations.json", "application/json")
    flat = pd.DataFrame(rows).to_csv(index=False).encode("utf-8")
    st.download_button("Download final ranked recommendations (CSV)", flat, "ranked_promo_candidates.csv", "text/csv")
