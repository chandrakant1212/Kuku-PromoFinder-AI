# Kuku PromoFinder AI
### Gemini-Assisted Promotional Clip Discovery and Recommendation

Kuku PromoFinder AI is a Streamlit-based tool that analyzes screenplay events and identifies promising 20–60 second promotional clip candidates. It uses Google Gemini for candidate discovery and editorial evaluation, while Python enforces timestamp validity, clip-duration constraints, and final recommendation diversity.

The application exports ranked recommendations in JSON and CSV formats, with an audit trail that preserves discovered candidates and explains why some candidates were suppressed.

## Key Features

- **AI-assisted discovery:** Uses Gemini to identify promising promotional moments from screenplay event chunks.
- **Timestamp validation:** Resolves Gemini-selected event IDs against original screenplay timestamps instead of accepting arbitrary model-generated timestamps.
- **Clip-duration enforcement:** Validates that candidates are between 20 and 60 seconds and remain within episode boundaries.
- **Editorial evaluation:** Evaluates candidates for hook strength, cliffhanger potential, emotional intensity, standalone clarity, risks, and overall recommendation.
- **Diverse recommendations:** Applies temporal non-maximum suppression (NMS) and a configurable per-episode recommendation cap.
- **Checkpoint and resume:** Reuses successful discovery and evaluation results across runs and allows pending evaluations to be resumed.
- **Exportable results:** Produces raw JSON output and ranked CSV recommendations.
- **Heuristic baseline:** Provides a non-LLM baseline for comparison. It should not be interpreted as an AI editorial judgment.

## How It Works

1. **Screenplay parsing:** Parses screenplay files into scenes and timestamped events.
2. **Candidate discovery:** Sends bounded event chunks to Gemini. The model returns start and end event IDs rather than free-form timestamps.
3. **Timestamp resolution and validation:** Python resolves the returned IDs to the original timestamps and rejects missing IDs, invalid ordering, out-of-range clips, and durations outside 20–60 seconds.
4. **Excerpt construction:** Builds the exact screenplay excerpt for each selected interval. Displayed event timestamps are clipped to the promo interval.
5. **Editorial evaluation:** Gemini evaluates selected candidates for hook, cliffhanger, emotional intensity, standalone clarity, risks, and recommendation.
6. **Diversity selection:** A deterministic post-processing stage reduces excessive overlap and limits the number of recommendations from each episode.
7. **Export:** The application provides raw candidate data and final ranked recommendations in JSON and CSV formats.

## Technology

- Python
- Streamlit
- Google Gemini API
- JSON and CSV for result exports

## Requirements

- Python installed on your machine
- A Google Gemini API key
- The project source files and screenplay input files

## Installation and Setup

The following commands are for Windows PowerShell.

### 1. Clone the repository

```powershell
git clone https://github.com/<YOUR-USERNAME>/<YOUR-REPOSITORY>.git
cd <YOUR-REPOSITORY>
```

If you already have the project locally, open PowerShell in the project root and skip this step.

### 2. Create a virtual environment

```powershell
python -m venv venv
```

### 3. Activate the virtual environment

```powershell
venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this command in the current PowerShell session and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure the Gemini API key

Create a file named `.env` in the project root:

```env
GEMINI_API_KEY=your_actual_api_key
GEMINI_MODEL=gemini-flash-lite-latest
```

Replace the placeholder with your own API key.

**Security:** Never commit `.env`, paste your API key into source code, or publish it in screenshots or logs. Keep `.env` excluded through `.gitignore`.

## Run the Application

From the project root, with the virtual environment activated:

```powershell
streamlit run app.py
```

Streamlit will provide a local URL in the terminal. Open that URL in your browser to use the application.

## Discovery and Evaluation Controls

The application separates candidate discovery from Gemini evaluation.

- Start with a subset of episodes to check API quota and output quality.
- Increase the episode count when you are ready to process the full input pack.
- Adjust the Gemini evaluation limit separately from the discovery scope.
- Use the heuristic baseline when you want a comparison against the AI-assisted workflow.
- Review the top candidates manually before treating them as final promotional selections.

## Recommendation Diversity

After Gemini evaluates the candidates, PromoFinder applies a deterministic editorial selection stage.

### Temporal non-maximum suppression (NMS)

Candidates are compared only within the same episode. A lower-ranked candidate is suppressed when its overlap with a higher-ranked candidate reaches the configured fraction of the shorter clip's duration. The default threshold is 50%.

### Per-episode recommendation cap

The final recommendation list has a configurable maximum number of promos per episode. The default is 3, helping prevent a single episode from dominating the final shortlist.

### Audit trail

The complete discovery output retains all candidates, including suppressed candidates and their suppression reasons. Separate JSON and CSV exports contain the final diverse recommendations.

The overlap threshold and per-episode cap can be adjusted in the Streamlit interface. NMS is applied after evaluation so that the higher-scoring overlapping candidate is retained.

## Reliability and Resume Support

PromoFinder includes mechanisms to make API processing more resilient:

- A shared Gemini request-pacing mechanism applies to discovery and evaluation. The default minimum interval is 5.5 seconds between requests.
- Set `GEMINI_MIN_REQUEST_INTERVAL` to override the default request interval.
- HTTP 429 responses honor Gemini's retry delay. If no retry delay is supplied, the client waits 60 seconds before retrying.
- Discovery results and successful evaluations are checkpointed in `data/run_checkpoint.json`.
- When the same parsed input is run again, successful discovery and evaluation results can be reused.
- Evaluation candidates are selected using heuristic pre-scores in a round-robin process across episodes.
- Failed and pending candidates are excluded from final ranked recommendations but remain represented in the raw output where applicable.

### Resume pending evaluations

The evaluation limit is a per-run limit for new pending candidates, not a lifetime cap.

To continue processing:

1. Keep the same screenplay input files and their contents unchanged.
2. Keep `data/run_checkpoint.json` in the same project folder.
3. Run the application again.
4. Click **Discover and evaluate promos** again.
5. Repeat until the pending count reaches zero.

Successful results are reused, and the next batch of pending candidates is evaluated up to the configured limit. Failed Gemini calls are not treated as successful checkpointed evaluations and can be retried in a later run.

To force a fresh run after changing code or when you want to discard cached results, delete:

```text
data/run_checkpoint.json
```

**Note:** The checkpoint is local to the project folder and machine. It is not automatically shared between machines or included in the project ZIP.

## Outputs

The application provides:

- **Raw JSON:** Detailed discovery/evaluation data, including candidate-level information and the audit trail.
- **Ranked CSV:** Tabular recommendations for review and further analysis.
- **Final diverse recommendations:** The shortlist after the diversity-selection stage.

Candidates that have not been successfully evaluated remain pending and are not included in the final ranked recommendations.

## Quality Considerations and Limitations

- Candidate timestamps are derived from supplied event timestamps; Gemini does not directly choose arbitrary timestamps.
- Python validates the 20–60 second duration and episode boundaries.
- Event display timestamps are clipped to the selected promo interval. However, the original screenplay descriptions may describe an action that spans beyond the clip boundary.
- LLM recommendations are not guaranteed to be suitable promotional clips. Human review is necessary.
- Chunk-based discovery can miss story context that spans distant parts of an episode. Episode logline/continuity context is used during evaluation, while discovery is primarily chunk-local.
- The free Gemini API tier may impose rate and quota limits.
- A failed episode is recorded and does not stop processing of the remaining episodes.

## Security and GitHub Notes

Before publishing the repository:

- Keep `.env` out of Git.
- Keep API keys out of source code, notebooks, screenshots, and committed logs.
- Review generated JSON, CSV, and checkpoint files before committing. They may contain screenplay-derived or other input-specific data.
- Do not publish screenplay files or other copyrighted/private input material unless you have permission.
- Commit only files that are appropriate for public access.

## Project Status

This project provides an AI-assisted workflow for discovering, evaluating, and ranking promotional clip candidates. Final editorial selection should include human review of the recommended clips.
