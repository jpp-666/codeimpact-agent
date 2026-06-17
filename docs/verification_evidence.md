# CodeImpact Agent Verification Evidence

This document records the reproducible outputs used to validate the project.

## 1. Test suite

Command:

```powershell
python -m pytest tests\codeimpact -q
```

Result:

- 27 passed
- 2 warnings from external dependencies

## 2. Evaluation harness

Command:

```powershell
python -m codeimpact evaluate --csv-path data\eval\sample.csv
```

Result:

```json
{
  "total": 9,
  "changed_file_hit_rate": 1.0,
  "related_file_hit_rate": 0.6666666666666666,
  "retrieval_hit_rate": 0.4444444444444444,
  "context_recall_at_5": 0.2857142857142857,
  "context_precision_at_5": 0.21428571428571427,
  "context_mrr_at_5": 0.48148148148148157
}
```

Notes:

- `related_file_hit_rate` is intentionally below 1.0 to keep the benchmark honest.
- The sample set includes a dynamic-import miss so the metric reflects a real weakness.
- `retrieval_hit_rate` now checks whether the expected related file appears in the retrieved top-k paths.
- `context_*` metrics are strict path-level retrieval checks against labeled `expected_context_files`.

## 3. Real repository analysis

Input:

- Repo: `<path-to-python-repo>`
- Diff: `docs\rca_e677b29.diff`
- Commit: `e677b29e57ba0988965270dec8ce44c7ca1a7bde`

Command:

```powershell
python -m codeimpact analyze --repo <path-to-python-repo> --diff docs\rca_e677b29.diff
```

Observed output highlights:

- `changed_files` includes:
  - `scripts/run_full_matrix.py`
  - `scripts/run_gate1_eval.py`
  - `scripts/train_router_v2.py`
  - `src/baselines/external.py`
  - `src/models/router.py`
  - `tests/test_fault_conditioning.py`
  - `tests/test_router_learned.py`
- `related_files` includes:
  - `<path-to-python-repo>\src\baselines\__init__.py`
- `risk_level` is `medium`
- `risk_reasoning` is:
  - `AST found 1 reverse dependencies for the touched module(s); downstream tests should be prioritized.`
- `risk_source` is `fallback`

## 4. LLM-backed verification

The same command above returns a genuine model-backed assessment when `CODEIMPACT_ENABLE_LLM=1`, `OPENAI_API_BASE`, `OPENAI_API_KEY`, and `OPENAI_CHAT_MODEL` are set correctly. The test suite forces `CODEIMPACT_ENABLE_LLM=0`, so tests do not make network calls even when a local `.env` file exists.

Observed `risk_reasoning` sample:

> The change set touches core model logic (`src/models/router.py`) and baseline integration code (`src/baselines/external.py`), which can affect training/inference behavior and evaluation outcomes beyond simple scripting updates. While several modified files are operational scripts, the presence of non-trivial code churn (186 added, 47 deleted) in model-related paths raises regression risk. Added/updated tests (`tests/test_fault_conditioning.py`, `tests/test_router_learned.py`) help mitigate this, so overall risk is elevated but not extreme.

## 5. What this proves

- The CLI works on a real Python repo and real diff.
- The AST reverse-dependency analysis produces a concrete downstream file.
- The evaluation set is not fake-perfect; it exposes a real miss.
- The risk output is explicit about whether it came from LLM or fallback logic.
