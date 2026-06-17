# CodeImpact Agent Demo Script

This script is designed for a 3-minute interview demo. The goal is to show that CodeImpact Agent is a tool-first Agent backend, not a UI demo or a thin LLM wrapper.

## 0. One-Sentence Positioning

CodeImpact Agent takes a Python repo and a `git diff`, uses deterministic tools to extract code evidence, then uses LangGraph, RAG, Memory, and an LLM/fallback risk node to produce a structured impact report that can be called from CLI or MCP.

## 1. Setup Check

From the project root:

```powershell
cd C:\Users\29738\Desktop\agent\codeimpact-agent
python -m pip install -e .
```

Optional LLM environment:

```powershell
$env:CODEIMPACT_ENABLE_LLM="1"
$env:OPENAI_API_BASE="https://api.example.com/v1"
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_CHAT_MODEL="your-model"
```

If the explicit LLM switch or API variables are absent, the demo still works with `risk_source: fallback`. Tests force the switch off so the suite does not make network calls.

## 2. Demo Line 1: CLI Analyzer

Command:

```powershell
python -m codeimpact analyze --repo C:\Users\29738\Desktop\github\rca --diff docs\rca_e677b29.diff
```

What to point out:

- `changed_files` comes from the diff parser.
- `related_files` comes from AST reverse dependency analysis, not LLM guessing.
- `risk_level`, `risk_reasoning`, and `risk_source` show whether the risk decision came from the LLM or fallback.
- `retrieved_context` and `context_sources` show the RAG layer: the model gets code/test/doc snippets before it reasons about risk.
- `test_focus`, `review_focus`, `confidence`, `assumptions`, and `evidence` show the prompt-engineering layer: the model is constrained by a risk rubric and diff hunk evidence instead of free-form guessing.
- `test_suggestions` are deterministic suggestions based on changed and downstream files.

Trimmed output to show:

```json
{
  "changed_files": [
    "src/baselines/external.py",
    "src/models/router.py",
    "tests/test_fault_conditioning.py",
    "tests/test_router_learned.py"
  ],
  "related_files": [
    {
      "path": "C:\\Users\\29738\\Desktop\\github\\rca\\src\\baselines\\__init__.py",
      "reason": "reverse import dependency",
      "depth": 1
    }
  ],
  "risk_level": "medium",
  "risk_source": "fallback",
  "risk_reasoning": "AST found 1 reverse dependencies for the touched module(s); downstream tests should be prioritized.",
  "test_focus": [
    "Run tests covering `src/models/router.py`",
    "Run downstream tests for modules that import the touched files."
  ],
  "review_focus": [
    "Inspect behavioral changes in `src/models/router.py`",
    "Check whether changed symbols are part of an imported API used by related files."
  ],
  "confidence": 0.62,
  "retrieved_context": [
    {
      "path": "tests/test_core.py",
      "chunk_type": "function",
      "symbol": "test_run_returns_expected_value",
      "score": 0.38,
      "snippet": "def test_run_returns_expected_value():     assert run() == 2"
    }
  ],
  "context_sources": [
    "AST reverse dependency",
    "RAG retrieved code/test/doc context"
  ],
  "retrieval_ms": 3.2,
  "test_suggestions": [
    "Run unit tests covering `src/models/router.py`",
    "Run downstream regression tests for: C:\\Users\\29738\\Desktop\\github\\rca\\src\\baselines\\__init__.py"
  ]
}
```

Interview explanation:

> I intentionally do not ask the LLM to infer imports from raw text. The deterministic tools first produce changed files, downstream files, line-change scale, and compact diff hunk evidence. Then I add a lightweight retrieval layer for code/tests/docs, and only after that does the LLM receive a risk rubric and output bounded risk reasoning, review focus, test focus, confidence, and assumptions.

## 3. Demo Line 2: LangGraph Workflow

Command:

```powershell
python -m codeimpact analyze-graph --repo C:\Users\29738\Desktop\github\rca --diff docs\rca_e677b29.diff
```

What to point out:

- The graph path runs the same analysis as a state machine.
- `memory_context` appears after previous runs because SQLite Memory stores analysis reports.
- If a change is high risk and has broad reverse dependencies, the graph routes to `deep_analysis`.

Flow:

```text
parse diff
  -> build AST dependency graph
  -> recall analysis memory
  -> LLM/fallback risk assessment
  -> conditional route:
       high risk + broad impact -> deep_analysis -> report
       otherwise                -> report
  -> store report in memory
```

Trimmed output fields to show when present:

```json
{
  "risk_level": "medium",
  "risk_source": "fallback",
  "memory_context": [
    {
      "source": "C:\\Users\\29738\\Desktop\\github\\rca",
      "risk_level": "medium",
      "risk_reasoning": "AST found 1 reverse dependencies for the touched module(s); downstream tests should be prioritized."
    }
  ]
}
```

Interview explanation:

> The LangGraph value is not that the MVP has many agents. It is that each node owns a clear piece of state, Memory can be inserted before risk reasoning, and routing can branch for high-risk broad-impact changes without rewriting the whole command.

## 4. Demo Line 3: MCP Tool Surface

Start the server:

```powershell
python -m codeimpact.mcp_server
```

Open MCP Inspector or another MCP-compatible client and inspect these tools:

- `get_changed_files`
- `analyze_diff`
- `search_code_context`
- `suggest_tests`
- `save_memory`
- `recall_memory`

Suggested MCP demo input for `get_changed_files`:

```json
{
  "diff_text": "diff --git a/pkg/core.py b/pkg/core.py\n--- a/pkg/core.py\n+++ b/pkg/core.py\n@@ -1,2 +1,2 @@\n-def run():\n+def run(flag=False):\n     pass\n"
}
```

Expected shape:

```json
[
  "pkg/core.py"
]
```

Suggested MCP demo input for `analyze_diff`:

```json
{
  "repo": "C:\\Users\\29738\\Desktop\\github\\rca",
  "diff_text": "<paste contents of docs\\rca_e677b29.diff>"
}
```

Expected shape:

```json
{
  "changed_files": ["..."],
  "related_files": ["..."],
  "risk_level": "medium",
  "risk_source": "llm or fallback",
  "memory_context": ["present after previous graph/MCP runs"],
  "retrieved_context": ["..."],
  "context_sources": ["..."],
  "test_focus": ["..."],
  "review_focus": ["..."],
  "confidence": 0.7,
  "test_suggestions": ["..."]
}
```

Interview explanation:

> MCP makes this backend usable by external Agent clients. Instead of building a web UI, I expose the same capabilities as tool calls: one client can ask for changed files, another can ask for full impact analysis, and another can save or recall project memory.

## 5. Demo Line 4: Evaluation Harness

Command:

```powershell
python -m codeimpact evaluate --csv-path data\eval\sample.csv
```

Expected output:

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

How to explain the metrics:

- `changed_file_hit_rate`: whether diff parsing finds the expected changed file.
- `related_file_hit_rate`: whether AST reverse dependency search finds the expected downstream file.
- `retrieval_hit_rate`: whether local context search retrieves the expected related file.
- `context_*`: strict path-level checks against labeled expected code/test/doc context files.

Important framing:

> The eval set is a small regression harness, not a statistical benchmark. The related-file score is intentionally below 1.0 because the sample includes dynamic imports that static AST cannot fully resolve. I kept those misses to show known limitations instead of reporting fake-perfect numbers.

## 6. Three-Minute Talk Track

Minute 1: Motivation

> Code review often misses downstream impact: a developer changes module A, but tests or reviewers forget module B that imports it. I built CodeImpact Agent to make that impact analysis explicit for Python repos.

Minute 2: Architecture

> The pipeline is diff parser -> AST import graph -> RAG retrieval -> memory recall -> LLM/fallback risk reasoning -> structured report. The key design is tool-first: code structure comes from deterministic analysis, and retrieval adds semantic context from tests and docs instead of relying on the model to guess.

Minute 3: Agent Fit

> It uses LangGraph for stateful orchestration, FastMCP for tool exposure, SQLite Memory for historical context, and an OpenAI-compatible LLM call for rubric-based risk, review-focus, and test-focus reasoning. The current limitation is static AST coverage and small eval size; the next improvement would be a larger labeled diff set.

## 7. Questions To Be Ready For

Q: Why is this not just a script?

A: The script-like part is only the execution surface. Internally it has tool boundaries, graph state, memory recall/store, conditional routing, LLM/fallback reasoning, and MCP exposure. Those are Agent backend concerns.

Q: Why not let the LLM read the full diff and decide everything?

A: Because imports and downstream impact are better handled by deterministic tools. The LLM is used after evidence extraction, where it is stronger: risk reasoning, prioritizing review focus, proposing test focus, stating assumptions, and estimating confidence.

Q: Why is `related_file_hit_rate` below 1.0?

A: The sample includes dynamic-import cases. Static AST analysis has known limits there. I kept those cases to make the evaluation honest and to identify the next fallback path.

Q: Where is the prompt engineering?

A: The risk prompt contains an explicit high/medium/low rubric, compact diff hunk evidence, AST related-file evidence, retrieved code/test/doc context, and optional Memory context. The output schema forces the model to return risk level, reasoning, test focus, review focus, confidence, assumptions, and cited evidence instead of a generic paragraph.

Q: What is the next best improvement?

A: Expand the eval set with carefully labeled commits and add a small metric for risk-classification quality. I would not add a frontend or heavy RAG stack before that.
