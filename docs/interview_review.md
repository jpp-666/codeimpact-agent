# CodeImpact Agent Resume Readiness Review

## Judgment

CodeImpact Agent is suitable for a resume as an Agent backend project, especially for roles that value code tooling, LangGraph orchestration, MCP integration, and deterministic tool use before LLM reasoning.

The positioning should be conservative:

- Good: "Python code change impact analysis Agent backend"
- Good: "LangGraph + AST reverse dependency analysis + MCP/FastAPI interfaces + LLM/fallback risk assessment"
- Required for interview demo: show `risk_source=llm` by running `analyze --require-llm`
- Avoid: "production-grade code review platform"
- Avoid: "high-accuracy RAG system"
- Avoid: "fully automated test generation"

Current verification state:

- Test suite: `29 passed, 2 warnings`
- Eval rows: `18`
- `changed_file_hit_rate`: `1.0`
- `related_file_hit_rate`: `0.8888888888888888`
- `retrieval_hit_rate`: `0.5555555555555556`
- Context metrics: `context_recall_at_5=0.2273`, `context_precision_at_5=0.1493`, `context_mrr_at_5=0.3333`

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

Current `retrieval_hit_rate` is `0.5556`, so do not write "high retrieval accuracy" or imply production-grade RAG quality.

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

Recommended Agent-role version:

```text
CodeImpact Agent｜代码变更影响分析 Agent 后端
独立开发｜Python / LangGraph / FastMCP / OpenAI SDK / FastAPI / SQLite

- 基于 LangGraph StateGraph 实现 parse -> dependency -> retrieve_context -> reason_risk -> report 工作流，支持 Memory recall/store 和高风险分支路由，将单次 LLM 调用组织成可扩展的多步骤 Agent 后端。
- 实现 Python AST 反向依赖图分析，支持普通 import、from import、相对导入、字符串字面量 importlib.import_module 和包 re-export，用于定位代码变更可能影响的下游模块。
- 接入 OpenAI-compatible LLM API，使用 JSON structured output 约束 risk_level、risk_reasoning、test_focus、review_focus、confidence、assumptions 等字段；提供 deterministic fallback，并通过 --require-llm 保证面试 demo 能展示真实 LLM 调用。
- 增加 SQLite Memory 和 SQLite FTS5/BM25 本地上下文检索，将代码、测试、README、docs 片段作为 LLM 风险判断证据；明确保留 lexical retrieval 的局限，不包装成高准确率 RAG。
- 通过 FastMCP 暴露 6 个工具，同时提供 Typer CLI 和 FastAPI HTTP API，覆盖本地命令、Agent client 和服务化调用场景。
- 设计 18 条样本回归评测集与 pytest/CI 验证，当前 changed_file_hit_rate=1.0、related_file_hit_rate=0.889、retrieval_hit_rate=0.556；保留动态 import 与词法检索 miss case，避免 fake-perfect 评测。
```

Short version:

```text
CodeImpact Agent 是一个 tool-first 代码变更影响分析 Agent 后端：先用 diff parser、Python AST 依赖图和 FTS5/BM25 检索提取代码证据，再通过 LangGraph 编排 Memory 与 OpenAI-compatible LLM 风险判断，最终通过 FastMCP、CLI 和 FastAPI 输出结构化 review/test focus。项目包含 18 条样本回归评测和 29 个 pytest 用例，指标用于验证核心链路并暴露静态分析与词法检索局限。
```

See `docs/resume_package_zh.md` for the public-safe copy-paste resume package.

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

For a live Agent interview, do not only show fallback output. Use `--require-llm` so the command fails unless the model call succeeds, then point to `risk_source=llm`.

### Why is retrieval_hit_rate low?

The retrieval metric is a strict path-level regression check over a small labeled set. It uses lexical retrieval, so it can miss files when query terms do not overlap with target content. That is an intentional limitation to discuss, not a number to market.

### Why use LangGraph if the flow is mostly sequential?

The workflow now includes typed state, Memory before risk reasoning, report persistence, and conditional routing into `deep_analysis` for high-risk broad-impact changes. LangGraph also leaves a clean extension point for future human-review or retry branches.

### What would you improve next?

1. Expand eval beyond 18 rows using real repository commits with manually reviewed ground truth.
2. Improve retrieval with better query construction or embeddings, then compare against the current lexical baseline.
3. Add deployment notes for the FastAPI service and MCP server.
4. Make MCP Memory storage configurable instead of module-level default SQLite.

## Final Recommendation

Use this project on the resume now. The best angle is not "model intelligence"; it is disciplined Agent engineering: deterministic tools, structured evidence, graph orchestration, MCP tool exposure, fallback behavior, tests, docs, and honest evaluation.
