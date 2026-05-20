# Swigar — AI 驱动游戏化英语学习 Agent 平台

将学习诊断、任务规划、游戏行为、个性化记忆与反馈奖励连接成闭环的智能学习后端。游戏客户端（TypeScript Web）通过 HTTP API 上报事件并拉取调度决策；开发期可使用 Debug 面板观察 Agent 工作流。

## 架构概览

- **swigar_events** — 学习事件总线、语义 enrich、Debug 广播
- **swigar_memory** — 基于 [MemPalace](mempalace-reference/) 的 per-learner 记忆（Drawer 原文 + Closet 索引 + 时间知识图谱）
- **swigar_orchestrator** — 学习导演：Observe → Recall → Plan → Act
- **swigar_skills** — 诊断 / 规划 / 任务映射 / 报告
- **swigar_tools** — 题库、判题、安全过滤
- **services/api** — FastAPI 游戏集成与 Debug WebSocket
- **apps/debug-dashboard** — 开发调试页

## 快速开始

### 1. 安装依赖

```bash
cd d:\swigar_agent
pip install -e ./mempalace-reference -e ".[dev]"
```

### 2. 配置阿里云百炼 LLM

```bash
copy .env.example .env
```

编辑 `.env`，填入百炼 API Key（[控制台](https://bailian.console.aliyun.com/) → API-KEY）：

```env
DASHSCOPE_API_KEY=sk-你的密钥
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
SWIGAR_LLM_ENABLED=true
```

#### 选哪个模型？

本系统每次调度会连续调用 **3 次** LLM（诊断 → 规划 → 任务映射），且都要求 **稳定 JSON 输出** + **英语教学常识** + **游戏剧情文案**，选型建议如下：

| 模型 | 适合场景 | 对本项目的评价 |
|------|----------|----------------|
| **`qwen-plus`**（推荐默认） | 生产环境主模型 | 能力/延迟/成本最均衡；语法薄弱点推断、学习路径、NPC 钩子都够用 |
| **`qwen3.5-plus`** | 已开通新一代 Plus 的账号 | 结构化 JSON、指令遵循通常优于旧版 plus，可作为首选升级 |
| **`qwen-flash`** | 本地联调、压测、极简剧情 | 便宜快，但复杂时态诊断与多步推理易偏差，**不建议单独用于生产调度** |
| **`qwen-max` / `qwen3-max`** | 周报/家长报告、疑难个案 | 推理最强，价格是 Plus 数倍；**不适合**每次 `onAnswer`/`onMistake` 都触发（成本高、延迟大） |

**结论：** 请把 `.env` 里的 `DASHSCOPE_MODEL` 设为 **`qwen-plus`**；若百炼控制台已提供 **`qwen3.5-plus`**，可优先用它。开发阶段想省额度可临时改为 `qwen-flash`，上线前改回 Plus。

模型列表以百炼文档为准：[OpenAI 兼容接口支持的模型](https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope)。

验证连通性：

```bash
python scripts/verify_llm.py
```

成功时会打印模型返回的 JSON 学习计划。

### 3. 启动 API

**一键启动（API + 出题工作台 + 游戏，各开一个终端窗口）：**

```powershell
.\scripts\dev_all.ps1
# 停止：.\scripts\stop_dev_all.ps1
```

| 服务 | 地址 |
|------|------|
| Agent API | http://127.0.0.1:8000 |
| debug-dashboard | http://127.0.0.1:5173 |
| TacticalDuel | http://127.0.0.1:5000 |

**请使用项目 `.venv` 启动**（不要用 Anaconda 全局 `python`，否则 MemPalace 的 `onnxruntime` 可能 DLL 报错）：

```bash
# Windows（仅 API）
.\scripts\run_api.ps1

# 或手动
.\.venv\Scripts\activate
uvicorn swigar_api.main:app --reload --host 0.0.0.0 --port 8000
```

若 Vite 报 `ECONNREFUSED 127.0.0.1:8000`（Windows 上旧 uvicorn 僵尸进程占端口），**出题工作台**可改用 8010：

```powershell
# 终端 1
.\scripts\run_api_workbench.ps1

# 终端 2
cd apps/debug-dashboard
npm run dev
```

`apps/debug-dashboard/.env.development` 已把代理指向 `http://127.0.0.1:8010`。若 8000 无法释放，`.\scripts\run_api.ps1` 会自动改在 **8010** 启动（避免 WinError 10048 绑定失败后进程立刻退出）。游戏 TacticalDuel 仍要 8000 时，先在任务管理器结束占用端口的 Python/uvicorn，或执行 `.\scripts\stop_api.ps1` 后再 `.\scripts\run_api.ps1`。

### 3.1 一键检查：百炼 LLM + ONNX + MemPalace

```bash
.\.venv\Scripts\python scripts/verify_system.py
```

| 组件 | 依赖 | 是否需要 GPU |
|------|------|----------------|
| 百炼 LLM | `DASHSCOPE_API_KEY` | 否（云端） |
| MemPalace 向量检索 | 本机 `onnxruntime`（CPU 即可） | 否 |

`.env` 中建议：`MEMPALACE_EMBEDDING_DEVICE=cpu`。若终端曾设置 `SWIGAR_LLM_ENABLED=false`，仓库 `.env` 现已优先覆盖该键。

### 4. 启动产品演示页（Debug Showcase）

```bash
cd apps/debug-dashboard
npm install
npm run dev
```

浏览器打开 http://localhost:5173 。该页面为**商业产品展示风格**的 Agent 演示台，包含：

- **架构总览**：9 大模块可点击，实时高亮当前正在工作的模块
- **预设演示场景**：答错、连续失误、开始学习等一键触发
- **工作流时间线**：按模块着色展示 enrich → 记忆 → LLM → 决策 全链路
- **LearningDecision 卡片**：剧情钩子、教学理由、题库题目可视化

需先启动 API（步骤 3 或 workbench 的 `run_api_workbench.ps1`），WebSocket 连接成功后即可操作。

### 5. Docker（可选，含 PostgreSQL）

```bash
docker compose up --build
```

本地开发默认使用 SQLite：`./swigar.db`。

## Paper-Agent 主路径（按卷出题）

每卷 **10 题**（4 道题库真题 + 6 道 AI 变式），默认 **DB/GEN 交错组卷**（`SWIGAR_PAPER_INTERLEAVE=true`），难度路径约 1→5；游戏战斗只改接线，伤害仍由本地逻辑计算。

| 端点 | 说明 |
|------|------|
| `POST /v1/sessions/{learner_id}/start` | 开始会话并生成/激活当前卷 |
| `GET /v1/papers/current?learner_id=` | 当前 active 卷元数据 |
| `GET /v1/papers/{paper_id}/questions/{index}` | 按索引取单题（不泄露整卷答案） |
| `POST /v1/papers/{paper_id}/answers` | 服务端判题 + 写记忆/画像 |
| `POST /v1/papers/{paper_id}/finish` | 收尾并激活预生成下一卷 |
| `GET /v1/papers/queue?learner_id=` | 下一卷是否已排队 |
| `GET /v1/learners/{id}/reserve` | 学习者 reserve 题库池数量 |
| `GET /v1/learners/{id}/profile` | 学生画像（工作台） |
| `GET /v1/learners/{id}/workflow` | Agent 白话工作流日志 |

编排：`PaperOrchestrator` → Plan → **MistakeReview（卷内去重）** → Retrieve(4) → **Generate（G1–G6 槽位 + 错题模式）** → Validate → **交错 Assemble** → **PaperAssemblyValidate（卷级）**。  
每卷默认混入 **2 道**历史错题（替换 DB 槽位，不占额外名额），混入前与种子/全卷做 **intra-paper** 去重，避免与 AI 题同 stem。

### 组卷与答题并行

- **判题**（`POST .../answers`）仅用规则 `EvaluatorTool`，不用 LLM。
- **组卷 LLM** 在 `DashScopeLLMClient.complete_json_async` 线程池中执行，不阻塞 asyncio 事件循环。
- **启动瀑布流**（`POST .../start`）：resume active → promote queued → hybrid（reserve 补卷 + 缺口 LLM）→ 新用户 cold_start（0 LLM 题库卷）→ full（并行 Generate）。
- **预取下一卷**：`SWIGAR_PREFETCH_ON_SESSION_START=true` 且 `SWIGAR_PREFETCH_DELAY_SEC` 延迟后后台组 `queued` 卷；冷启动首卷不预取；`SWIGAR_PREFETCH_FALLBACK_AT_QUESTION=7` 为兜底。
- **题库镜像**：`python scripts/sync_question_bank.py` 导出 `data/question_bank.json`，设 `SWIGAR_QUESTION_BANK_SOURCE=json`（Agent 答卷仍用 `DATABASE_URL` 云端 PG）。

### 变式生题与卷级质量

规格见 [`skills/question_generation_skill.md`](skills/question_generation_skill.md)、[`skills/question_validation_skill.md`](skills/question_validation_skill.md)、[`skills/paper_assembly_validation_skill.md`](skills/paper_assembly_validation_skill.md)。

- **三级相似度**（`question_similarity.py`）：lexical + structural frame + semantic 规则；卷内 `check_intra_paper_diversity`。
- **生成**：T1–T6 变式算子、G1–G6 槽位贪心选 6 道；`learner_recent_errors` → `error_pattern.py`；≥`SWIGAR_MIN_ERROR_TARGETED_GENERATED` 道针对错题模式。
- **校验**：答案泄露、选项词性、等级适配；卷级 `paper_score` / `recommendation` 写入工作流 trace。
- **知识点混排**（`knowledge_clusters.py`）：每卷主 KP + 1–2 个同簇相近点（如过去式 + 过去完成时），避免 10 题同一细粒度题型；工作流输出 `kp_distribution`。

环境变量：`SWIGAR_GENERATE_CANDIDATE_COUNT`、`SWIGAR_PAPER_INTERLEAVE`、`SWIGAR_MIN_ERROR_TARGETED_GENERATED`、`SWIGAR_MAX_REVISE_CANDIDATES`（默认 2，限制 step6 修订次数）、`SWIGAR_PAPER_KP_MIX`、`SWIGAR_MIN_DISTINCT_KP`、`SWIGAR_MAX_SAME_KP_RATIO`、`SWIGAR_SIMILARITY_EMBEDDING`（可选 embedding Phase2）。

### 跨卷去重与知识点轮换

- **近期答对排除**：`AnswerStore.list_recent_correct_ids` + 组卷时并入 `exclude_ids`（默认 `SWIGAR_EXCLUDE_RECENT_DAYS=14`）。错题复习、未答结转仍会复现；仅抑制「刚答对的原题 ID」反复出现。
- **题库检索轮换**：`QuestionBankTool.find` 对匹配候选 `shuffle` 后再取前 N 道（`SWIGAR_RETRIEVE_SHUFFLE=true`），避免总命中 `question_bank.json` 数组前几条。
- **掌握度换簇**：当同语法簇多数 KP 的 `accuracy_by_kp` ≥ `SWIGAR_KP_MASTERED_THRESHOLD`（默认 0.8）时，`PaperPlanSkill` 切换到其它语法簇（`rotate_plan_if_mastered`）。
- **Reserve**：`select_from_reserve` 同样跳过近期答对 ID。
- 工作流 trace 含 `exclude_recent_count` 与 `retrieve_ids`，便于核对。

### 双端联调（工作台 + TacticalDuel 游戏）

两端均调用 **同一 Swigar API**（`http://127.0.0.1:8000`，游戏经 Vite 代理 `/v1`）：

| 端 | 入口 | 下一题方式 |
|----|------|------------|
| debug-dashboard | Agent 工作台 | 本端提交或游戏端答题后，约 2 秒内自动进入下一题；末题仍显示「完成试卷」 |
| TacticalDuel | 游戏设置 → **出题模式** | **本地题库**：内置题库；**Paper 双端统一**：放技能出题 → 选题 → **确认并结算技能** → 下次放技能才出下一题 |

**必须对齐 `learner_id`**：工作台登录的 `uid` 与游戏的 `game_user_id` / `playerInfo.userUid` 一致（见 `apps/debug-dashboard/src/lib/gameAuth.ts` 与 `TacticalDuel/client/src/lib/utils/userUtils.ts`）。否则为两套独立试卷。

- 游戏 **Paper 双端统一** 模式下，`startPaperSession` 会复用工作台已有 active 卷并从 `current_index` 续答；**不会**在 API 失败时静默回退本地题库。
- 游戏经 `:5000/v1` 反代时，`express.json()` 必须注册在反代**之后**（见 `TacticalDuel/server/index.ts`），否则 `POST .../answers` 会挂起直至判题超时。
- 游戏须点「确认并结算技能」后才结算伤害并关窗；工作台在检测到服务端 `current_index` 前进后会自动显示下一题（亦可手动点「下一题」）。
- 确认 `GET /health` 中 `db_ready: true` 后再组卷/答题。

### 答题幂等

- `answer_records` 对 `(paper_id, question_index)` 唯一；重复提交返回已有判题结果，不重复写 MemPalace。
- MemPalace 事件 ID 由 `paper_id:question_index` 稳定派生；工作流默认不重复广播 persist/memory（`SWIGAR_VERBOSE_WORKFLOW=true` 可打开 MemPalace 日志）。

### 顺序答题（工作台 / API）

- 仅允许作答 `paper.current_index` 对应题目；跳题或重答返回 **409**。
- 提交后**无论对错**返回 `explanation`；须手动进入下一题（游戏：确认并结算技能后，下次放技能；工作台：「下一题」）；末题后调用 `POST .../finish`。
- `GET /v1/papers/{id}/preview` 对已答题返回 `answered`、`is_correct`、`user_answer`、`explanation`（未答题不泄露答案）。
- `POST /v1/sessions/{id}/start?intent=next`（工作台）：须**无进行中 active 卷**（已交卷）后组下一卷；有排队卷则直接激活，否则 LLM 组卷。`fresh=true` 仅供游戏端兼容。
- `POST /v1/sessions/{id}/start?intent=promote`（游戏）：有 queued 卷时秒开激活预生成卷。
- `POST /v1/sessions/{id}/start?fresh=true`（游戏）：放弃未完成 **active** 卷（**不**废弃 queued）；未作答题 harvest 到 reserve；有 queued 则优先 promote。
- 工作台与游戏共用 `localStorage.game_user_id` 作为学习者 ID（独立 MemPalace）。
- 工作台登录浮层（`LoginOverlay`）与《战术对决》共用 `currentUser` / `savedUserAuth`，经 Vite 代理 `POST /api/user/login|register` → 游戏后端（:5000）；未登录时遮罩覆盖主站，Header 可「切换账号」。

### 工作台实时架构图

`apps/debug-dashboard`：登录浮层 / 画像 / 顺序答题 / **PAL Paper 架构图**（`PaperArchitectureLive`）+ 模块 Inspector（LLM prompt/response trace，WebSocket `/debug/stream`）。

## TacticalDuel 端到端集成

战斗答题可在游戏设置中选择 **本地题库** 或 **Paper 双端统一**（`gameSettings.questionSourceMode` → `questionUtils.ts` / `paperSession.ts`）。  
仍保留 `swigarBridge` 事件镜像与 `LearningDecision` 弹窗（兼容演示）。

### 开发环境

推荐：`.\scripts\dev_all.ps1`（API + 工作台 + 游戏一次拉起）。

或手动：

1. 根目录启动 Agent API：`.\scripts\run_api.ps1`（端口 8000，与根目录 `.env` 共用 `DATABASE_URL`）
2. 配置 [`TacticalDuel/.env`](TacticalDuel/.env)（见 [`TacticalDuel/.env.example`](TacticalDuel/.env.example)）：
   - `VITE_SWIGAR_PAPER_FALLBACK=false` — 强制 Paper-Agent 出题（交错组卷、知识点混排）
   - `VITE_SWIGAR_USE_PROXY=true` — 浏览器走同源 `/v1`（游戏服 `server/swigarProxy.ts` 反代到 8000；须保留 `/v1` 路径前缀，否则组卷会 404 `Not Found`）
3. 启动游戏：`cd TacticalDuel && npm run dev`（http://localhost:5000）
4. 开局显示「AI 正在组卷」；完成后放技能答题，弹窗显示题号/知识点/来源角标

### 生产部署

- 游戏 Express 将 `/v1` 代理到 `SWIGAR_API_URL`（与 Agent API 同机或内网）
- 前端 `VITE_SWIGAR_USE_PROXY=true`，`API_BASE` 为空（相对路径）
- Agent API 与游戏库使用同一 PostgreSQL（题库 `questions_*` + 答卷/画像）

### 游戏行为说明

- 新局：有 queued 则 `intent=promote`（秒开）；新用户 cold_start（&lt;5s）；老用户有 reserve 则 hybrid；否则 full LLM 组卷
- 刷新页面：若存在未完成 active 卷则自动 **resume**，不丢进度
- 答满 10 题或 `paper_finished` 时自动 `POST .../finish`；对局结束也会 `finish`
- 卷内 **知识点混排** 时，每题 `knowledge_point` 可能不同（属正常，用于辨析相近语法）
- 本地调试回退：设 `VITE_SWIGAR_PAPER_FALLBACK=local` 使用内置 `questionBank`

论文评估：`python scripts/eval_dissertation.py`（含 `paper_results_*.csv` Paper 场景）。

## 游戏集成契约

### 上报学习事件

`POST /v1/events`

```json
{
  "type": "onAnswer",
  "learner_id": "u_123",
  "session_id": "s_456",
  "game_context": {
    "map_id": "castle",
    "room_id": "r_07",
    "npc_id": "blacksmith",
    "quest_id": "grammar_dungeon_1"
  },
  "payload": {
    "question_id": "q_pp_001",
    "skill_tags": ["grammar.present_perfect"],
    "user_answer": "I have went",
    "correct_answer": "I have gone",
    "is_correct": false,
    "time_spent_ms": 12000
  }
}
```

支持事件类型：`onSessionStart`、`onAnswer`、`onMistake`、`onTaskDone`、`onLowEngage`、`onDialogue`。

### 拉取待执行决策

`GET /v1/decisions/{learner_id}/pending`

响应示例：

```json
{
  "action_type": "dungeon_quiz",
  "narrative_hook": "NPC 带你去训练室巩固现在完成时…",
  "content": { "questions": [{ "id": "q_pp_001", "prompt": "..." }] },
  "rationale": "Repeated mistakes on grammar.present_perfect",
  "memory_refs": [],
  "status": "pending"
}
```

`action_type` 取值：`assign_task` | `npc_dialogue` | `dungeon_quiz` | `feedback_reward` | `hint` | `difficulty_adjust`

### 确认决策已呈现

`POST /v1/decisions/{decision_id}/ack`

### 学习情境

`GET /v1/situation/{learner_id}`

### 老师/家长目标

- `GET /v1/goals?learner_id=...`
- `POST /v1/goals` — body 见 `GoalCreate` 模型

### 学习报告

`GET /v1/reports/{learner_id}?days=7`

### Debug WebSocket

`WS /debug/stream` — 实时 trace、事件处理结果、决策输出。

## 记忆存储

每位学习者的 MemPalace 数据目录：

- `~/.swigar/palaces/{learner_id}/` — Chroma 向量库
- `~/.swigar/palaces/{learner_id}/knowledge_graph.sqlite3` — 掌握度时间线

Wing 映射：`grammar` / `vocabulary` / `dungeon` / `dialogue` / `learner`

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `DASHSCOPE_API_KEY` | — | 百炼 API Key（必填方可启用 LLM） |
| `DASHSCOPE_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | OpenAI 兼容端点 |
| `DASHSCOPE_MODEL` | `qwen-plus` | 模型名，如 `qwen-turbo` / `qwen-max` |
| `SWIGAR_LLM_ENABLED` | `true` | `false` 时仅用规则引擎 |
| `SWIGAR_LLM_FALLBACK_ON_ERROR` | `true` | LLM 失败时回退规则 |
| `SWIGAR_MEMORY_DISABLED` | `false` | `true` 关闭 MemPalace 写入 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./swigar.db` | 与游戏相同的 PostgreSQL URL 亦可；`postgresql://` 会自动转为 `postgresql+asyncpg://` |
| `SWIGAR_QUESTION_BANK_SOURCE` | `auto` | `auto` / `postgres` / `json` / `builtin`；`auto` 在有 PostgreSQL 时从 `questions_grammar`、`questions_words` 加载 |
| `SWIGAR_HOME` | `~/.swigar` | 学习者记忆根目录 |
| `CORS_ORIGINS` | `http://localhost:5173,...` | API CORS |

完整示例见 [.env.example](.env.example)。

### 验证 LLM 已接入

1. `GET http://localhost:8000/health` 应返回 `"llm_configured": true`，且 `question_bank_count` 为云端题库数量（非 4）
2. Debug 面板触发 Orchestrate，工作流中应出现 `llm_request` / `llm_response` trace
3. `narrative_hook` 应为模型生成的剧情文案，而非固定模板句

## 测试

```bash
pytest packages services/api/tests -q
```

## 演示脚本

```bash
python scripts/demo_loop.py
```

模拟：错题事件 → 记忆写入 → Agent 调度 → 输出 `LearningDecision`。

## Git / GitHub Desktop

**请用本目录作为仓库根目录：** `d:\swigar_agent`（不要打开子文件夹 `Swigar_PAL_Agent`）。

历史上若在项目内克隆过 `Swigar_PAL_Agent` 子目录，它会与父目录共用远程 `swigar2103/Swigar_PAL_Agent`，但本地只停留在「仅 README」的旧提交，GitHub Desktop 会显示 **1↑ 2↓**；在该子目录 **Force push** 会用空壳历史覆盖云端，导致 GitHub 上代码消失。

正确做法：

1. GitHub Desktop → **File → Add local repository** → 选择 `d:\swigar_agent`
2. 同步时优先 **Pull**，再 **Push**；仅在确认要以本地为准时才 Force push
3. 勿在仅含 README 的嵌套克隆目录里操作同一远程
