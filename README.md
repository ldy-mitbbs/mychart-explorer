# MyChart Explorer（中文版）

> English version: [README.en.md](README.en.md)

这是一个**本地运行、注重隐私**的 Web 应用，适合用来浏览你从 Epic MyChart 导出的电子健康信息（EHI），并借助大语言模型（LLM）查询和理解自己的健康数据。默认的 LLM 后端是本地部署的 [Ollama](https://ollama.com) 模型，因此除非你主动启用云端服务商，否则你的病历数据不会离开本机。

> ⚠️ **本项目不是医疗器械。** 它只是一个个人数据探索工具，请勿用于临床决策。

## 功能特性

- **无需命令行即可完成配置**：在应用内的 **Setup（设置）** 页面中选择你的导出目录，然后点击 *Start ingest（开始导入）*，即可实时查看导入进度。
- **精选仪表盘**：提供概览、问题列表、用药、过敏、化验（含趋势图和参考范围）、生命体征、免疫接种、既往史、就诊记录完整详情、支持 FTS5 全文检索的临床笔记、MyChart 消息（RTF 转纯文本），以及所有扁平化后的 FHIR 资源。
- **通用表浏览器**：可查看 Epic 导出中的全部表（约 3700 张）。已导入的表通过 SQLite 访问，其余表则按需从 TSV 流式读取；每一列的说明来自 Epic 数据字典，并以悬停提示的形式展示。
- **只读 SQL 控制台**：仅允许执行 SELECT，自动附加 LIMIT，并使用 `sqlglot` 做语法校验。
- **AI 聊天（支持工具调用）**：模型可以调用
  `get_patient_summary`、`list_tables`、`describe_table`、`run_sql`、
  `search_notes`、`get_note`、`get_message` 和 `lab_trend`。回答会附带来源引用，例如
  `[note:123]`、`[msg:456]`、`[table:PROBLEMS code=...]`。
- **可插拔 LLM**：支持 Ollama（默认，本地）、OpenAI 和 Anthropic。启用云端服务商时，界面上会显示红色的 *"PHI sent to …"（个人健康信息已发送至…）* 提示横幅。

## 截图

![AI 回答一个问题，并引用笔记和化验趋势作为来源](docs/screenshots/chat1.png)

![同一个问题的中文回答 —— 本地模型可处理多语言查询](docs/screenshots/chat2.png)

![概览仪表盘：当前问题、最近的生命体征和近期化验结果](docs/screenshots/summary.png)

![糖化血红蛋白（HEMOGLOBIN A1C）的化验趋势图](docs/screenshots/labs.png)

![Setup 页面展示导入进度状态](docs/screenshots/setup.png)

## 架构

```
mychart-explorer/
  ingest/       解析 schema HTM + 导入 TSV + 导入 FHIR NDJSON -> SQLite
                重组笔记 + MyChart 消息 + 建立 FTS5 索引
  backend/      FastAPI（仅监听 localhost）+ SQL 防护 + LLM 路由 + 工具
                提供由 UI 驱动的导入管理路由
  frontend/     React + Vite + TypeScript + recharts
  data/         mychart.db, schema.json, settings.json（自动生成，且已加入 gitignore）
```

## 前置要求

- **Python** 3.11+
- **Node.js** 18+
- **你的 Epic MyChart 导出数据**：可通过患者门户申请。解压到一个方便的位置后，目录中应包含 `EHITables/`（TSV 文件）、`EHITables Schema/`（HTML 数据字典）和 `FHIR/`（NDJSON 文件）。
- **可选：[Ollama](https://ollama.com)**，用于本地 LLM 聊天。

## 快速开始

```sh
git clone https://github.com/ldy-mitbbs/mychart-explorer.git
cd mychart-explorer

# 1. Python 虚拟环境与依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动后端（一个终端）
uvicorn backend.main:app --host 127.0.0.1 --port 8765

# 3. 启动前端（另一个终端）
cd frontend
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

首次启动时，应用会自动跳转到 **Setup（设置）** 页面。将 Epic 导出目录的绝对路径粘贴进去，依次点击 *Validate（校验）*、*Save（保存）* 和 *Start ingest（开始导入）*，随后就可以在界面中实时看到导入进度。

### 命令行替代方式

如果你更习惯脚本化操作，也可以使用同一套导入流程对应的命令行接口：

```sh
python -m ingest --source "/path/to/your/Epic Export" --db data/mychart.db
```

## LLM 配置

### 本地（推荐）

```sh
brew install ollama           # 或参考 ollama.com 上你所用平台的安装说明
ollama serve &
ollama pull qwen3.5           # 默认模型；替代选项见下方的内存建议表
```

在应用的 **Ask AI（向 AI 提问）** 标签页里，打开 *Settings（设置）*，然后从下拉菜单中选择一个模型（列表由 `ollama list` 自动填充）。聊天功能会通过工具调用查询你的 SQLite 数据库，因此**请优先选择在 [ollama.com/library](https://ollama.com/library) 上带有 `tools` 标签的模型**。

#### 按内存选择模型

在默认的 Q4 量化下，显存或统一内存的大致预算可按 `参数量 × 0.6 GB` 估算，另外还需要额外预留几 GB 给上下文。如果你只使用 CPU，同样的数字也可大致对应系统内存，只是生成速度会更慢。

| 你的内存     | 推荐的支持工具调用的模型（Ollama tag）                                  |
| ----------- | --------------------------------------------------------------------- |
| 4–6 GB      | `qwen3:1.7b`, `qwen2.5:1.5b`, `granite4:1b`, `granite4:3b`            |
| 8 GB        | `qwen3:4b`, `qwen2.5:3b`, `phi4-mini:3.8b`, `granite3.3:2b`           |
| 12–16 GB    | `qwen3:8b` *（甜点区）*, `qwen2.5:7b`, `qwen3.5:9b`, `granite3.3:8b`   |
| 24–32 GB    | `qwen3:14b`, `phi4:14b`, `qwen3.5:27b`（较吃紧）, `mistral-small:24b`, `qwen3.6:27b` † |
| 48–64 GB    | `qwen3:30b`（MoE，速度快）, `gpt-oss:20b`, `qwen3:32b`, `qwen3.5:35b`, `qwen3.6:35b` † |
| 96 GB+      | `qwen3:235b`（MoE）, `gpt-oss:120b`, `qwen3.5:122b`                   |

说明：

- **Qwen 3 / 3.5**（阿里巴巴）是目前很主流的开源模型家族，工具调用能力强，覆盖从 0.6B 到 235B MoE 的多种规模。
- **Qwen3 30B MoE** 每个 token 实际只激活约 3B 参数，因此运行速度接近 7B 模型，但推理能力更接近大模型；如果你的内存足够容纳权重，它会是很有性价比的选择。
- **Phi-4-mini / Phi-4**（微软）在相同参数量下推理能力非常出色。
- **Granite 4** / **Granite 3.3**（IBM）体积小、速度快，并针对工具调用做了调优，很适合 8 GB 内存的笔记本。
- **gpt-oss**（OpenAI 开放权重）和 **Mistral Small 3** 也是中大规模里不错的选择。这个应用不建议使用基础版 **Gemma 3**，因为它不支持工具调用；如果你想用 Google 的模型，请选择 **Gemma 4**。
- 如果某个模型在工具调用时表现不稳定，可以先降一个参数档位，或者直接换成 `qwen3` 系列。

† **qwen3.6** 是 2026 年 4 月刚发布的新模型，目前只有 27B/35B 两个尺寸。它属于 `thinking` 类型，在代码 Agent 场景下成绩很强；不过新模型发布初期的工具调用模板往往还不够稳定，如果你遇到格式错误，建议先回退到 `qwen3:32b` 或 `qwen3.5:27b`。

### 云端（需主动开启）

请在启动后端**之前**设置 API Key：

```sh
export OPENAI_API_KEY=sk-...      # 或
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

然后在聊天设置面板中选择对应的服务商。界面会显示横幅，提示当前正在使用云端服务。**每轮对话都会将你的 PHI（受保护健康信息）发送给该服务商**，因此只有在你确认能够接受对方的数据政策后，才建议启用。

## 隐私与安全

- 后端仅绑定到 `127.0.0.1`，不会在局域网上监听。
- 运行时以只读方式打开 SQLite。
- `/api/sql` 端点会使用 `sqlglot` 解析每条查询，拒绝所有非 `SELECT` / `WITH` 的语句，并自动附加行数限制。
- `data/`（包含导入后的数据库和设置）已加入 gitignore。
- 应用不发送任何遥测数据。

## 环境变量

所有环境变量都是可选的，你也可以直接在 Setup 页面里完成配置。

| 名称 | 默认值 | 用途 |
|---|---|---|
| `MYCHART_SOURCE` | — | 覆盖源目录（否则使用 Setup 页面的设置） |
| `MYCHART_DB` | `data/mychart.db` | 输出的 SQLite 路径 |
| `MYCHART_SCHEMA_JSON` | `data/schema.json` | 解析后的数据字典路径 |
| `OPENAI_API_KEY` | — | 启用 OpenAI 服务商 |
| `ANTHROPIC_API_KEY` | — | 启用 Anthropic 服务商 |

## 导入命令行参数

```sh
python -m ingest --source ... --db ... [--skip-schema] [--skip-tsv] [--skip-fhir] [--skip-notes]
```

每个阶段都是幂等且彼此独立的，因此即使你修改了 `ingest/tables.py` 中的精选表列表，也可以放心重新运行。

## 添加更多表

默认会将约 40 张临床表加载到 SQLite 中，以便快速访问。导出数据中的其他表仍然可以通过 **Tables 浏览器**按需访问（从 TSV 流式读取）。如果你想把某张表也纳入 SQLite：

1. 在 `ingest/tables.py` 中加入它的名字（以及可选的索引列）。
2. 重新运行导入（通过 Setup 页面中的 *Re-ingest*，或在命令行中使用
   `--skip-schema --skip-fhir`）。

## 免责声明

本项目与 Epic Systems、任何医疗机构以及任何电子病历厂商均无关联。请自行承担使用风险。作者并非临床医生，本项目也不构成医学建议。

## 许可证

[MIT](LICENSE)
