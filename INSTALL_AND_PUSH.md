# Install the PromoFinder test and CI patch

Copy these files into the root of your existing `Kuku-PromoFinder-AI` project, preserving the folder structure:

- Replace `test_ranking.py`
- Add the four files under `tests/`
- Add `.github/workflows/tests.yml`
- Add `requirements-dev.txt`

Do not overwrite your application source files.

## Run tests locally (Windows PowerShell)

From the project root, activate your existing virtual environment, then run:

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

To see each test name:

```powershell
python -m pytest -v
```

## Commit and push

Review the files first:

```powershell
git status
git diff -- test_ranking.py
```

Stage only the intended test and workflow files:

```powershell
git add test_ranking.py tests/ .github/workflows/tests.yml requirements-dev.txt
git status
```

Commit and push:

```powershell
git commit -m "Add pytest coverage and GitHub Actions CI"
git push
```

## Verify GitHub Actions

Open the repository's **Actions** tab. The `Python tests` workflow should start automatically after the push. Open the run and confirm that the test job passes.

The workflow does not need `GEMINI_API_KEY`; these tests exercise local parsing, candidate construction, scoring, and ranking logic only.
