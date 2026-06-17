# CodeImpact Agent Resume Readiness Review

## Judgment

CodeImpact Agent is suitable for a resume as an Agent backend project, especially for roles that value code tooling, LangGraph orchestration, MCP integration, and deterministic tool use before LLM reasoning.

The positioning should be conservative:

- Good: "Python code change impact analysis Agent backend"
- Good: "LangGraph + AST reverse dependency analysis + MCP tools + LLM/fallback risk assessment"
- Avoid: "production-grade code review platform"
- Avoid: "high-accuracy RAG system"
- Avoid: "fully automated test generation"

Current verification state:

- Test suite: `23 passed, 2 warnings`
- Eval rows: `9`
- `changed_file_hit_rate`: `1.0`
- `related_file_hit_rate`: `0.6666666666666666`
- `retrieval_hit_rate`: `0.4444444444444444`
- Context metrics: `context_recall_at_5=0.2857`, `context_precision_at_5=0.2143`, `context_mrr_at_5=0.4815`

## What Is Strong

### 1. Tool-first Agent design

The strongest story is the division of labor:

1. Deterministic tools parse the diff and inspect repository structure.
2. Python AST builds a reverse import graph for downstream impact.
3. Retrieval adds code/test/doc context.
4. SQLite Memory recalls prior analysis records.
5. The LLM receives structured evidence and a rubric, then produces bounded risk reasoning.
6. Fallback logic keeps the system usable without API credentials.

This is more defensible than sending raw diffs to an LLM and asking it to guess.

### 2. LangGraph is real, not just named

The graph currently has meaningful state transitions:

```text
parse -> dependency -> retrieve_context -> reason_risk
      -> conditional route:
           high risk + broad impact -> deep_analysis -> report
           otherwise                -> report
```

It also uses Memory before risk reasoning and stores the final report afterward. This is enough to call it a LangGraph workflow, but avoid saying "multi-agent collaboration."

### 3. MCP integration is real

FastMCP exposes 6 tools:

- `get_changed_files`
- `analyze_diff`
- `search_code_context`
- `suggest_tests`
- `save_memory`
- `recall_memory`

Tests verify tool listing and tool calls, so this is a legitimate resume point.

### 4. The eval harness is honest

The metrics are not fake-perfect. The sample set includes dynamic-import and context-retrieval misses, which gives you a credible answer when asked about limitations.

## Main Risks

### P1: Do not overstate retrieval quality

Current `retrieval_hit_rate` is `0.4444`, so do not write "retrieval_hit_rate 0.8" or imply strong RAG accuracy.

Use this framing instead:

> Built a small regression evaluation harness covering diff parsing, AST related-file discovery, and context retrieval; the current results intentionally expose static-analysis and lexical-retrieval limitations.

### P1: Do not call it production-grade

The project has tests and docs, but no CI/CD deployment, auth model, multi-user isolation, or large benchmark. It is a strong portfolio project, not a production system.

### P2: Explain AST limitations clearly

Static AST can handle normal imports, relative imports, string-literal `importlib.import_module(...)`, and `__init__.py` re-export patterns. It cannot fully resolve variable-driven dynamic imports, runtime monkeypatching, plugin registries, or config-driven imports.

This is not a fatal flaw if you explain it as a known boundary.

### P2: Treat test suggestions honestly

`test_suggestions` are deterministic and AST-derived. Do not say the LLM generates tests. The LLM/fallback risk layer produces `test_focus`, which is a prioritization aid, not generated test code.

## Resume Wording

Recommended version:

```text
CodeImpact Agent - Python Code Change Impact Analysis Agent Backend

- Built a LangGraph state-machine workflow that turns git diff input into a structured impact report, including changed files, downstream related files, retrieved context, risk level, review focus, and test focus.
- Implemented Python AST reverse dependency analysis to trace downstream import impact across a repository, with explicit handling for normal imports, relative imports, string-literal dynamic imports, and package re-exports.
- Added SQLite/FTS5-BM25 context retrieval over code, tests, README, and docs, then fed retrieved evidence plus diff hunk summaries into an OpenAI-compatible LLM risk assessor with JSON structured output and deterministic fallback.
- Exposed the backend through 6 FastMCP tools for MCP-compatible clients and provided a Typer CLI for local analysis, graph execution, and evaluation.
- Designed a 9-row regression eval harness covering diff parsing, dependency discovery, and context retrieval; results intentionally expose AST and lexical retrieval limitations rather than reporting fake-perfect scores.
```

Short version:

```text
Built CodeImpact Agent, a Python code-change impact analysis backend using LangGraph, FastMCP, Python AST, SQLite/FTS5-BM25, and OpenAI-compatible LLM risk assessment. The system parses git diffs, traces downstream imports, retrieves code/test/doc context, recalls prior analysis memory, and returns structured risk reports through CLI and MCP tools. Added a 9-row eval harness and pytest coverage for core paths.
```

## Do Not Write

- "RAG recall is 0.8" or "high retrieval accuracy"
- "LLM generates tests"
- "production-ready code review platform"
- "multi-agent system"
- "supports all Python import patterns"
- "100% recall"

## Interview Talking Points

### Why not just ask the LLM to review the diff?

Because import relationships and changed-file extraction are better handled by deterministic tools. The LLM is used after evidence extraction, where it is stronger: risk reasoning, review focus, test focus, confidence, and assumptions.

### Why is retrieval_hit_rate low?

The retrieval metric is a strict path-level regression check over a small labeled set. It uses lexical retrieval, so it can miss files when query terms do not overlap with target content. That is an intentional limitation to discuss, not a number to market.

### Why use LangGraph if the flow is mostly sequential?

The workflow now includes typed state, Memory before risk reasoning, report persistence, and conditional routing into `deep_analysis` for high-risk broad-impact changes. LangGraph also leaves a clean extension point for future human-review or retry branches.

### What would you improve next?

1. Add CI, so tests run on every push.
2. Expand eval from 9 rows to real repository commits with manually reviewed ground truth.
3. Improve retrieval with better query construction or embeddings, then compare against the current lexical baseline.
4. Make MCP Memory storage configurable instead of module-level default SQLite.

## Final Recommendation

Use this project on the resume now. The best angle is not "model intelligence"; it is disciplined Agent engineering: deterministic tools, structured evidence, graph orchestration, MCP tool exposure, fallback behavior, tests, docs, and honest evaluation.
