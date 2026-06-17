# CodeImpact Agent Resume Package

This document is a public-safe resume and interview positioning note for CodeImpact Agent. It keeps the claims conservative and tied to implemented behavior.

## 推荐项目标题

```text
CodeImpact Agent｜代码变更影响分析 Agent 后端
独立开发｜Python / LangGraph / FastMCP / OpenAI SDK / FastAPI / SQLite
```

## 简历描述

```text
基于 Python 构建代码变更影响分析 Agent 后端，输入 git diff 后自动解析变更文件、追踪 Python 模块下游依赖、检索相关代码/测试/文档上下文，并通过 OpenAI-compatible LLM 输出结构化风险评估、review focus 和 test focus。项目使用 LangGraph 编排多节点工作流，通过 FastMCP、Typer CLI 和 FastAPI 暴露能力，并设计 18 条样本的回归评测集验证 diff 解析、依赖发现和上下文检索效果。
```

## 推荐 Bullet

```text
- 基于 LangGraph StateGraph 实现 parse -> dependency -> retrieve_context -> reason_risk -> report 工作流，支持 Memory recall/store 和高风险分支路由，将单次 LLM 调用组织成可扩展的多步骤 Agent 后端。
- 实现 Python AST 反向依赖图分析，支持普通 import、from import、相对导入、字符串字面量 importlib.import_module 和包 re-export，用于定位代码变更可能影响的下游模块。
- 接入 OpenAI-compatible LLM API，使用 JSON structured output 约束 risk_level、risk_reasoning、test_focus、review_focus、confidence、assumptions 等字段；提供 deterministic fallback，并通过 --require-llm 保证面试 demo 能展示真实 LLM 调用。
- 增加 SQLite Memory 和 SQLite FTS5/BM25 本地上下文检索，将代码、测试、README、docs 片段作为 LLM 风险判断证据；明确保留 lexical retrieval 的局限，不包装成高准确率 RAG。
- 通过 FastMCP 暴露 get_changed_files、analyze_diff、search_code_context、suggest_tests、save_memory、recall_memory 6 个工具，同时提供 Typer CLI 和 FastAPI HTTP API，覆盖本地命令、Agent client 和服务化调用场景。
- 设计 18 条样本回归评测集与 pytest/CI 验证，当前 changed_file_hit_rate=1.0、related_file_hit_rate=0.889、retrieval_hit_rate=0.556；保留动态 import 与词法检索 miss case，避免 fake-perfect 评测。
```

## 不要这样写

- 不要写“多 Agent 协作系统”。当前是单工作流多工具节点。
- 不要写“高准确率 RAG”。当前 retrieval_hit_rate 是小样本回归指标，不是大规模 benchmark。
- 不要写“LLM 自动生成测试”。系统输出 test_focus，deterministic test_suggestions 不是测试代码生成。
- 不要写“生产级代码审查平台”。项目没有鉴权、多用户隔离、部署和大规模评测。
- 不要写“支持所有 Python import”。变量驱动 dynamic import 和运行时注入仍是已知限制。

## 面试定位

一句话：

```text
这是一个 tool-first 的 Agent 后端项目：先用确定性工具提取代码证据，再用 LangGraph 编排 Memory、检索和 LLM 风险判断，最后通过 MCP/CLI/API 暴露给外部调用。
```

回答“为什么是 Agent 项目”：

```text
这个项目不是裸 LLM wrapper。LLM 之前有 diff parser、AST dependency graph、context retriever、SQLite Memory 这些工具节点；LangGraph 负责状态传递和条件路由；MCP 把能力暴露给外部 Agent client。LLM 的职责是基于工具产出的证据做风险分级、review focus、test focus 和 assumptions，而不是直接读一段 diff 自由发挥。
```

## 已知边界

- Eval 是 18 条样本 regression harness，不是大规模 benchmark。
- Retrieval 是 SQLite FTS5/BM25 词法检索，不是 embedding retrieval。
- Static AST 不能完全覆盖变量驱动 dynamic import、运行时 monkeypatch、复杂 plugin registry。
- FastAPI 是服务化接口，不包含鉴权、多用户隔离和部署配置。
