# CodeImpact Agent 技术面试审查报告

## 1. 总体结论

**判定：可以写进简历，评分 6.5/10**

- 项目架构设计合理——确定性工具（diff parser + AST 反向依赖图）先提取结构化证据，LLM 只做风险推理这一步，这是正确的 Agent 设计思路，比"把所有事情丢给 LLM"高一个层次。
- LangGraph、MCP、AST、Memory、Eval 五个技术点全部有真实代码支撑，不是空壳包装。
- 但 LangGraph 的使用过于线性（4 个节点串行，无条件分支、无并行、无 human-in-the-loop），Memory 未参与决策流程（只写不读），Eval 样本量太小（5 条）。这些会被有经验的面试官一眼看穿。
- 总体定位：比 PDF QA / 求职助手 / 普通 RAG 项目强，但离"强 Agent 项目"还差一步。适合投递初中级 Agent 开发岗，高级岗需要补强。

---

## 2. Agent 岗匹配度

### 2.1 多步编排（LangGraph）

- **结论：中**
- **证据文件**：`src/codeimpact/graph.py:44-88`
- **事实**：StateGraph 有 4 个节点 `parse → dependency → reason_risk → report`，全部串行 `add_edge`，无 `add_conditional_edges`，无并行分支，无循环。
- **面试时怎么讲**：强调"为什么选择线性流而不是复杂图"——因为代码影响分析的步骤有严格依赖关系，parse 必须在 dependency 之前，dependency 必须在 risk 之前。可以提到"如果要扩展，会在 reason_risk 后加条件分支：high risk 走人工审批节点，low risk 直接出报告"。
- **面试官可能追问**：
  - "你的 graph 全是线性的，和写 4 个函数顺序调用有什么区别？为什么需要 LangGraph？"
  - "如果 LLM 返回 unknown，你会重试还是走 fallback？为什么不在图里加条件边？"

### 2.2 工具化（MCP）

- **结论：强**
- **证据文件**：`src/codeimpact/mcp_server.py`，`tests/codeimpact/test_mcp_server.py`
- **事实**：6 个 MCP tool 全部用 `@mcp.tool()` 注册，测试中用 `mcp.call_tool()` 验证了工具调用和返回值。FastMCP 用法正确。
- **面试时怎么讲**：MCP 让这个 Agent 的能力可以被任何 MCP 客户端（Claude Desktop、Cursor 等）直接调用，不需要重新集成。
- **面试官可能追问**：
  - "MCP 和直接暴露 REST API 有什么区别？你为什么选 MCP？"
  - "你的 MCP server 有没有被真实的 LLM 客户端调用过？"

### 2.3 外部工具调用

- **结论：强**
- **证据文件**：`src/codeimpact/diff_parser.py`（171 行完整 diff 解析器），`src/codeimpact/ast_graph.py`（224 行 AST 反向依赖图），`src/codeimpact/rag/search.py`（BM25 检索）
- **事实**：diff parser 处理了 rename、new file、deleted file、hunk 行号追踪等边界情况。AST 模块处理了 `import`、`from ... import`、相对导入、`importlib.import_module`、`__import__`、`__init__.py` re-export。这两个模块是项目最扎实的部分。
- **面试时怎么讲**：这是项目的核心差异化——不是让 LLM 猜依赖关系，而是用 AST 精确构建 import 图，再用 BFS 追踪反向依赖。LLM 只在确定性工具给出证据后做风险判断。
- **面试官可能追问**：
  - "AST 无法处理动态 import（`__import__(var)`）和条件 import（`if TYPE_CHECKING`）怎么办？"
  - "你的 BFS max_depth=2，为什么是 2？有没有做过实验？"

### 2.4 LLM 使用

- **结论：中**
- **证据文件**：`src/codeimpact/risk.py:12-46`
- **事实**：调用 OpenAI 兼容 API，system prompt 要求返回 JSON，用 `response_format={"type": "json_object"}` 约束输出格式，有 fallback 逻辑。LLM 的输入是结构化的（changed_files、related_files、added/deleted 行数），不是原始 diff 文本。
- **面试时怎么讲**：LLM 的角色是"在确定性证据基础上做风险推理"，不是"猜测代码结构"。这是 Agent 设计的正确分工。
- **面试官可能追问**：
  - "你只传了文件路径和行数给 LLM，没传 diff 内容本身。LLM 怎么判断'改了什么'？"
  - "fallback 逻辑很简单（related < 3 就 medium，>= 3 就 high），这和 LLM 的判断差距有多大？你有没有对比过？"

### 2.5 Memory

- **结论：弱**
- **证据文件**：`src/codeimpact/memory/sqlite_memory.py`，`graph.py:70-74`
- **事实**：SQLiteMemoryStore 实现了 store/recall/consolidate，代码质量可以。但在主流程中只有写入（`graph.py:71` 的 `runtime.remember`），没有读取。recall 只在 MCP tool 中暴露，主分析流程不会 recall 历史来辅助决策。
- **面试时怎么讲**：诚实说"当前 Memory 主要用于持久化分析历史，供后续查询。下一步计划是在 reason_risk 节点 recall 同一模块的历史风险记录，作为 LLM 的额外上下文。"
- **面试官可能追问**：
  - "Memory 在主流程里只写不读，那它和写日志有什么区别？"
  - "如果 Memory 参与决策，你怎么防止历史记录误导当前判断？"

### 2.6 Eval

- **结论：中**
- **证据文件**：`src/codeimpact/eval.py`，`tests/codeimpact/test_eval.py`，`docs/verification_evidence.md`
- **事实**：5 条样本，3 个指标（changed_file_hit_rate=1.0, related_file_hit_rate=0.6, retrieval_hit_rate=0.8）。验证文档诚实标注了 0.6 是因为动态 import miss。
- **面试时怎么讲**：强调"eval 的目的不是证明准确率高，而是建立可复现的回归检测机制。0.6 的 related_file_hit_rate 暴露了 AST 静态分析的已知局限（动态 import），这是有意保留的。"
- **面试官可能追问**：
  - "5 条样本能说明什么？这个 eval 有统计意义吗？"
  - "你的 eval 没有测 LLM 输出质量（risk_level 是否正确），只测了确定性工具的覆盖率，为什么？"

### 2.7 工程完整度

- **结论：强**
- **证据**：`pyproject.toml`（标准打包），CLI 入口（typer），MCP server，13 个测试，verification_evidence.md，真实仓库验证
- **面试时怎么讲**：项目可以 `pip install -e .` 后直接用 `codeimpact analyze` 命令，也可以启动 MCP server 被 AI IDE 调用。不是 notebook 级别的 demo。

---

## 3. 主要优点

1. **AST 反向依赖图是真功夫**（`ast_graph.py`）：处理了相对导入、`importlib.import_module`、`__init__.py` re-export、BFS 深度控制。这不是调库能做到的，面试时可以展开讲 10 分钟。

2. **确定性工具 + LLM 推理的分工设计正确**：diff parser 和 AST graph 提供结构化证据，LLM 只做最后一步风险判断。这比"把 diff 丢给 GPT 让它猜"高一个档次，体现了 Agent 设计的核心原则。

3. **MCP 集成是真实的**：不是写了个 README 说"支持 MCP"，而是有 FastMCP 注册、有测试验证 `call_tool` 返回值。

4. **Eval 诚实**：没有造假到 1.0，主动暴露了 0.6 的弱点并解释原因。这在面试中反而是加分项——说明你理解系统的局限。

5. **工程闭环**：CLI + MCP + tests + docs + eval + 真实仓库验证，不是 notebook demo。

---

## 4. 主要短板和风险

### 4.1 LangGraph 只是线性管道

**问题**：`graph.py` 的 4 个节点全部 `add_edge` 串行连接，没有条件分支、没有并行、没有循环、没有 human-in-the-loop。面试官会问"这和 `parse(); dependency(); risk(); report()` 四行代码有什么区别？"

**面试回答策略**：
> "当前版本确实是线性的，因为 MVP 阶段的步骤有严格依赖。但 LangGraph 的价值在于：(1) 状态管理——每个节点只读写自己关心的 state key，不需要手动传参；(2) 可观测性——LangGraph 自带 trace；(3) 扩展性——下一步我计划加条件边：如果 AST 发现 related_files > 5，走 deep_analysis 节点做更细粒度的函数级影响分析；如果 risk_level=high，走 human_review 节点。"

### 4.2 Memory 只写不读

**问题**：`graph.py:71` 只有 `runtime.remember()`，主流程没有 `runtime.recall()`。Memory 没有参与决策。

**面试回答策略**：
> "当前 Memory 的定位是'分析历史持久化'，供 MCP 的 recall_memory 工具被外部 Agent 查询。下一步是在 reason_risk 节点加入 recall：查询同一模块过去 5 次分析的 risk_level，如果历史上反复出现 high risk，即使本次改动小也应该提高警惕。这是一个'经验积累'的设计。"

### 4.3 Eval 样本量只有 5

**问题**：5 条样本没有统计意义，面试官会质疑"这能证明什么？"

**面试回答策略**：
> "5 条样本的目的不是证明统计显著性，而是建立回归检测的 CI 基础设施。每次改动 AST 逻辑后跑一遍，确保不退化。如果要做严肃评测，需要从开源项目（如 CPython、Django）的 git history 中自动生成 ground truth，这是下一步计划。"

### 4.4 LLM prompt 没传 diff 内容

**问题**：`risk.py:70-84` 的 `_build_risk_prompt` 只传了文件路径和行数统计，没传实际代码变更内容。LLM 无法判断"改了什么逻辑"。

**面试回答策略**：
> "这是有意的 trade-off。传完整 diff 会导致 token 消耗大且 LLM 容易被细节干扰。当前设计让 LLM 基于'哪些文件改了、影响了多少下游、改动规模'做宏观风险判断。如果需要更精细的判断（比如'这个改动是否破坏了接口契约'），可以在 prompt 中加入 hunk 级别的摘要。"

### 4.5 Retrieval 模块未参与主流程

**问题**：`rag/search.py` 的 `LightweightRetriever` 只在 `eval.py` 中使用，主分析流程（`graph.py`、`cli.py`）完全没有调用它。

**面试回答策略**：
> "Retrieval 当前的定位是 eval 中验证'给定 query 能否检索到相关文件'。在主流程中，AST graph 已经精确追踪了依赖关系，不需要模糊检索。Retrieval 的未来用途是：当 AST 无法解析（动态 import、配置文件引用）时，作为 fallback 补充候选文件。"

---

## 5. 是否适合作为简历项目

**结论：可以写，但要注意措辞**

### 可以写的：
- LangGraph 多步编排
- MCP 工具暴露
- AST 反向依赖图
- LLM 风险推理 + fallback
- 评测框架

### 不能乱写的词：
- "生产级"——这是个人项目，没有生产流量
- "高准确率"——related_file_hit_rate 只有 0.6
- "完全自动化"——没有 CI/CD 集成
- "多 Agent 协作"——只有一个 Agent
- "RAG 系统"——retrieval 没参与主流程

### 可以写的指标：
- changed_file_hit_rate = 1.0（但要注明样本量 5）
- 13 个单元测试通过
- 6 个 MCP 工具

### 必须解释局限的指标：
- related_file_hit_rate = 0.6（必须说明是 AST 静态分析的已知局限）
- eval 样本量 = 5（必须说明是回归检测用途，不是统计验证）

---

## 6. 推荐简历话术

> **CodeImpact Agent — Python 代码变更影响分析工具**
>
> - 基于 LangGraph 构建 4 节点编排流程（diff 解析 → AST 依赖追踪 → LLM 风险推理 → 报告生成），实现结构化代码变更影响分析
> - 使用 Python AST 模块构建仓库级 import 反向依赖图，支持相对导入、动态 import、re-export 追踪，BFS 深度可控
> - 通过 FastMCP 暴露 6 个标准化工具（diff 分析、依赖查询、测试建议、Memory 读写），可被 AI IDE 直接调用
> - LLM 仅负责风险推理环节，输入为确定性工具提取的结构化证据（变更文件、下游依赖、改动规模），配合 fallback 启发式规则保证无 API 时可用
> - 构建评测框架验证工具链覆盖率（changed_file_hit_rate=1.0, retrieval_hit_rate=0.8, 样本量 5），暴露 AST 静态分析对动态 import 的已知局限

---

## 7. 面试 5 分钟讲解稿

### 第 1 分钟：背景和动机

> "我做这个项目的出发点是：团队 code review 时，reviewer 经常漏掉'改了 A 文件但没跑 B 文件的测试'这种下游影响。市面上的 AI code review 工具大多是把整个 diff 丢给 LLM 让它猜，但 LLM 不知道项目的 import 结构，容易漏判。我的思路是：让确定性工具先把依赖关系算清楚，再让 LLM 基于结构化证据做风险判断。"

### 第 2 分钟：技术架构

> "整体是一个 LangGraph 编排的 4 步流程：第一步 parse diff，把 git diff 文本解析成结构化对象；第二步用 AST 构建整个仓库的 import 反向依赖图，然后 BFS 找出被改文件的下游影响文件；第三步把结构化证据（哪些文件改了、影响了几个下游、改动规模）传给 LLM 做风险推理；第四步生成报告。同时通过 FastMCP 把这些能力暴露成 6 个工具，可以被 Claude Desktop 或 Cursor 直接调用。"

### 第 3 分钟：核心技术点——AST 反向依赖图

> "这是项目最核心的模块。我用 Python 的 ast 模块遍历仓库所有 .py 文件，提取 import 语句构建有向图。难点在于：相对导入需要根据当前文件位置解析；`importlib.import_module('pkg.core')` 这种动态 import 需要特殊处理；`__init__.py` 的 re-export 需要额外追踪。构建好图之后，对变更文件做 BFS，max_depth=2，找出所有可能受影响的下游文件。"

### 第 4 分钟：Demo 和指标

> "实际跑一下：输入一个真实 Python 仓库和一个 git diff 文件，输出 JSON 报告，包含 changed_files、related_files、risk_level、test_suggestions。我建了一个 5 条样本的评测集，changed_file_hit_rate 是 1.0，related_file_hit_rate 是 0.6。0.6 不是 bug，是 AST 静态分析的已知局限——有一条样本用了动态 import，AST 追踪不到。"

### 第 5 分钟：局限和下一步

> "三个主要局限：一是 LangGraph 当前是线性流，没有条件分支，下一步计划加 risk_level=high 时走人工审批节点；二是 Memory 当前只写不读，下一步让 risk 节点 recall 历史分析辅助判断；三是 eval 样本量太小，计划从开源项目 git history 自动生成 ground truth 扩充到 50+ 条。"

---

## 8. 最终建议

### 现在是否可以开始投递？

**可以投递初中级 Agent 开发岗**。项目展示了正确的 Agent 设计思路（工具 + LLM 分工），技术栈覆盖了 LangGraph / MCP / AST / LLM / Memory / Eval，工程完整度够用。

### 投递前还必须补什么？

如果时间允许，补两件事会显著提升说服力：

1. **让 Memory 参与决策**：在 `reason_risk_node` 中加一行 `runtime.recall()`，把同模块历史 risk 记录拼入 LLM prompt。这样 Memory 就不再是摆设，而是真正影响输出的组件。

2. **给 LangGraph 加一条条件边**：比如 `reason_risk` 之后，如果 `risk_level == "high"` 且 `related_files > 3`，走一个 `deep_analysis` 节点（哪怕只是多输出一段详细建议）。这样面试官就不能说"你的 graph 和顺序调用没区别"。

### 如果只能再花 2 小时，最值得做哪 2 件事？

1. **（1 小时）在 `reason_risk_node` 加 recall + 条件边**：recall 历史记录拼入 prompt，加一条 `add_conditional_edges` 让 high risk 走不同路径。这一改同时解决了"Memory 只写不读"和"LangGraph 无分支"两个最大短板。

2. **（1 小时）把 eval 样本从 5 扩到 15-20**：从你的 `rca` 仓库的 git log 中多取几个 commit 的 diff，手动标注 expected_related。样本量到 15 以上，面试官就不太会纠结"5 条能说明什么"。

---

## 附录：需要 Codex 执行的改进任务清单

以下是可以直接交给 Codex 执行的具体任务：

### 任务 1：在 reason_risk_node 加入 Memory recall

- 文件：`src/codeimpact/graph.py`
- 位置：`reason_risk_node` 函数内
- 要求：
  - 在调用 `call_risk_model` 之前，先 `runtime.recall(state["repo"], memory_type="analysis", limit=3)`
  - 把 recall 到的历史 risk_level 和 risk_reasoning 拼入 `_build_risk_prompt` 的上下文
  - 如果没有历史记录，行为不变

### 任务 2：给 LangGraph 加条件边

- 文件：`src/codeimpact/graph.py`
- 要求：
  - 在 `reason_risk` 之后加 `add_conditional_edges`
  - 条件：如果 `risk_level == "high"` 且 `len(related_files) > 3`，走新节点 `deep_analysis`
  - `deep_analysis` 节点：输出更详细的风险分析建议（可以是基于规则的，不必调 LLM）
  - 否则直接走 `report`
  - `deep_analysis` 完成后也走 `report`

### 任务 3：扩充 eval 样本

- 目录：`data/eval/`
- 要求：
  - 从 `C:\Users\29738\Desktop\github\rca` 仓库的 git log 中选取 10-15 个有意义的 commit
  - 为每个 commit 生成 diff 文件
  - 在 `sample.csv` 中添加对应行，手动标注 expected_changed 和 expected_related
  - 确保新样本覆盖：纯新增文件、纯删除文件、跨包修改、`__init__.py` 修改等场景
