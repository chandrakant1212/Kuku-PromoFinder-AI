# Kuku PromoFinder AI
### Gemini-Assisted Promotional Clip Discovery and Recommendation

Kuku PromoFinder AI is a Streamlit-based tool that analyzes screenplay events and identifies promising 20–60 second promotional clip candidates. It uses Google Gemini for candidate discovery and editorial evaluation, while Python enforces timestamp validity, clip-duration constraints, editorial eligibility, and final recommendation diversity.

The application exports ranked recommendations in JSON and CSV formats, with an audit trail that preserves discovered candidates and explains why some candidates were excluded or suppressed.

## Key Features

- **AI-assisted discovery:** Uses Gemini to identify promising promotional moments from screenplay event chunks.
- **Timestamp validation:** Resolves Gemini-selected event IDs against original screenplay timestamps instead of accepting arbitrary model-generated timestamps.
- **Clip-duration enforcement:** Validates that candidates are between 20 and 60 seconds and remain within episode boundaries.
- **Editorial evaluation:** Evaluates candidates for hook strength, cliffhanger potential, emotional intensity, standalone clarity, risks, and overall recommendation.
- **Deterministic editorial quality gate:** Allows only explicit `strong` and `consider` recommendations into the final shortlist. Excludes `reject` and missing/unknown recommendation labels regardless of numeric score.
- **Diverse recommendations:** Applies temporal non-maximum suppression (NMS) and a configurable per-episode recommendation cap after editorial eligibility filtering.
- **Checkpoint and resume:** Reuses successful discovery and evaluation results across runs and allows pending evaluations to be resumed.
- **Exportable results:** Produces raw JSON output and ranked CSV recommendations with exclusion/suppression reasons.
- **Heuristic baseline:** Provides a non-LLM baseline for comparison. It should not be interpreted as an AI editorial judgment.

## How It Works

1. **Screenplay parsing:** Parses screenplay files into scenes and timestamped events.
2. **Candidate discovery:** Sends bounded event chunks to Gemini. The model returns start and end event IDs rather than free-form timestamps.
3. **Timestamp resolution and validation:** Python resolves the returned IDs to the original timestamps and rejects missing IDs, invalid ordering, out-of-range clips, and durations outside 20–60 seconds.
4. **Excerpt construction:** Builds the exact screenplay excerpt for each selected interval. Displayed event timestamps are clipped to the promo interval.
5. **Editorial evaluation:** Gemini evaluates selected candidates for hook, cliffhanger, emotional intensity, standalone clarity, risks, and recommendation.
6. **Editorial quality gate:** Python deterministically permits `strong` and `consider`; it excludes `reject` and missing/unknown decisions. A high numeric score cannot override an explicit rejection.
7. **Diversity selection:** Eligible candidates pass through temporal NMS and a per-episode recommendation cap.
8. **Export:** The application provides raw candidate data and final ranked recommendations in JSON and CSV formats.

## Editorial Quality Gate

The final recommendation stage uses the categorical Gemini recommendation separately from the weighted numeric score.

| Gemini recommendation | Final shortlist treatment |
|---|---|
| `strong` | Eligible |
| `consider` | Eligible |
| `reject` | Excluded |
| Missing or unrecognized | Excluded |

This prevents a candidate explicitly rejected by the editorial evaluator from entering the final shortlist merely because its weighted score is high. Excluded candidates remain in the raw JSON audit output with an exclusion reason, so the decision is transparent and reviewable.

The gate is deterministic post-processing; it does not change Gemini's evaluation or erase the original evaluation data. Human editorial review remains necessary.

## Technology

- Python
- Streamlit
- Google Gemini API
- pytest and GitHub Actions
- JSON and CSV for result exports

## Requirements

- Python installed on your machine
- A Google Gemini API key
- The project source files and screenplay input files

## Installation and Setup

The following commands are for Windows PowerShell.

### 1. Clone the repository

```powershell
git clone https://github.com/chandrakant1212/Kuku-PromoFinder-AI.git
cd Kuku-PromoFinder-AI
```

If you already have the project locally, open PowerShell in the project root and skip this step.

### 2. Create and activate a virtual environment

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Configure the Gemini API key

Create a `.env` file in the project root:

```env
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-3.5-flash-lite
```

Never commit `.env` or expose your API key in source code, screenshots, or logs.

## Run the Application

```powershell
streamlit run app.py
```

## Run Automated Tests

```powershell
python -m pytest -v
```

GitHub Actions runs the test suite on pushes to `main` and pull requests targeting `main`.

## Discovery and Evaluation Controls

The application separates candidate discovery from Gemini evaluation.

- Start with a subset of episodes to check API quota and output quality.
- Increase the episode count when you are ready to process the full input pack.
- Adjust the Gemini evaluation limit separately from the discovery scope.
- Use the heuristic baseline when you want a comparison against the AI-assisted workflow.
- Review the top candidates manually before treating them as final promotional selections.

## Recommendation Diversity

After editorial eligibility filtering, PromoFinder applies deterministic diversity selection.

### Temporal non-maximum suppression (NMS)

Candidates are compared only within the same episode. A lower-ranked candidate is suppressed when its overlap with a higher-ranked candidate reaches the configured fraction of the shorter clip's duration. The default threshold is 50%.

### Per-episode recommendation cap

The final recommendation list has a configurable maximum number of promos per episode. The default is 3.

### Audit trail

The complete discovery output retains evaluated candidates, including editorially excluded candidates and candidates suppressed by temporal overlap or the per-episode cap. The `suppression.reason` field distinguishes `editorial_reject`, `editorial_approval_missing_or_invalid`, `temporal_overlap`, and `episode_limit`.

## Reliability and Resume Support

- A shared Gemini request-pacing mechanism applies to discovery and evaluation.
- HTTP 429 responses honor Gemini's retry delay. If no retry delay is supplied, the client waits before retrying.
- Discovery results and successful evaluations are checkpointed in `data/run_checkpoint.json`.
- When the same parsed input is run again, successful discovery and evaluation results can be reused.
- Failed and pending candidates are excluded from final ranked recommendations but remain represented in raw output where applicable.

### Resume pending evaluations

1. Keep the same screenplay input files and their contents unchanged.
2. Keep `data/run_checkpoint.json` in the same project folder.
3. Run the application again.
4. Click **Discover and evaluate promos** again.
5. Repeat until the pending count reaches zero.

Successful results are reused. Failed Gemini calls are not treated as successful checkpointed evaluations and can be retried in a later run.

## Outputs

- **Raw JSON:** Detailed discovery/evaluation data, including editorial exclusions and diversity suppression reasons.
- **Final recommendations JSON:** Only candidates that pass editorial eligibility and diversity selection.
- **Ranked CSV:** Tabular final recommendations for review and further analysis.

## Quality Considerations and Limitations

- Candidate timestamps are derived from supplied event timestamps; Gemini does not directly choose arbitrary timestamps.
- Python validates the 20–60 second duration and episode boundaries.
- The categorical editorial gate reduces explicit rejects but does not guarantee promotional success.
- LLM recommendations are not guaranteed to be suitable promotional clips. Human review is necessary.
- Chunk-based discovery can miss story context that spans distant parts of an episode.
- The free Gemini API tier may impose rate and quota limits.
- A failed episode is recorded and does not stop processing of the remaining episodes.

## Security and GitHub Notes

- Keep `.env` out of Git.
- Keep API keys out of source code, notebooks, screenshots, and committed logs.
- Review generated JSON, CSV, and checkpoint files before committing. They may contain screenplay-derived or other input-specific data.
- Do not publish screenplay files or other copyrighted/private input material unless you have permission.

## Project Status

Kuku PromoFinder AI provides an AI-assisted workflow for discovering, evaluating, and ranking promotional clip candidates. It combines LLM-based editorial assessment with deterministic timestamp validation, recommendation eligibility rules, and diversity selection. Final editorial selection should include human review.
