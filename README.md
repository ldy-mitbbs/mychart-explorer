# MyChart Explorer（中文版）

> English version: [README.en.md](README.en.md)

一个**本地运行、注重隐私**的 Web 应用，用来浏览你从 Epic MyChart 导出的电子健康信息（EHI），并用大语言模型（LLM）向你自己的健康数据提问。默认的 LLM 后端是本地部署的 [Ollama](https://ollama.com) 模型，因此除非你主动选择云端服务商，否则你的病历数据不会离开你的电脑。

> ⚠️ **本项目不是医疗器械。** 它只是一个个人数据探索工具，请勿用于临床决策。

## 功能特性

- **无需命令行即可完成配置**：在应用内的 **Setup（设置）** 页面中指定你的导出目录，然后点击 *Start ingest（开始导入）*，导入进度会实时显示。
- **精选的仪表盘**：包括概览、问题列表、用药、过敏、化验（含趋势图与参考范围）、生命体征、免疫接种、既往史、就诊记录完整详情、带 FTS5 全文检索的临床笔记、MyChart 消息（RTF 转纯文本），以及所有扁平化的 FHIR 资源。
- **通用表浏览器**：你 Epic 导出中的所有表（约 3700 个）—— 已导入的表通过 SQLite 访问，其余的则按需从 TSV 流式读取；列描述来自 Epic 数据字典，会作为悬停提示显示。
- **只读 SQL 控制台**：仅允许 SELECT，自动加 LIMIT，使用 `sqlglot` 做语法校验。
- **AI 聊天（支持工具调用）**：模型可以调用
  `get_patient_summary`、`list_tables`、`describe_table`、`run_sql`、
  `search_notes`、`get_note`、`get_message` 和 `lab_trend`。回答中会引用来源，例如
  `[note:123]`、`[msg:456]`、`[table:PROBLEMS code=...]`。
- **可插拔的 LLM**：Ollama（默认，本地）、OpenAI 或 Anthropic。使用云端服务商时，界面上会显示红色的 *"PHI sent to …"（个人健康信息已发送至…）* 提示横幅。

## 截图

![AI 回答一个问题，并引用笔记和化验趋势作为来源](docs/screenshots/chat1.png)

![同一个问题的中文回答 —— 本地模型可处理多语言查询](docs/screenshots/chat2.png)

![概览仪表盘：活动中的问题、最近的生命体征和最近的化验](docs/screenshots/summary.png)

![糖化血红蛋白（HEMOGLOBIN A1C）的化验趋势图](docs/screenshots/labs.png)

![Setup 页面展示导入状态](docs/screenshots/setup.png)

## 架构

```
mychart-explorer/
  ingest/       解析 schema HTM + 加载 TSV + 加载 FHIR NDJSON -> SQLite
                重新组装笔记 + MyChart 消息 + FTS5 索引
  backend/      FastAPI（仅监听 localhost）+ SQL 守卫 + LLM 路由 + 工具
                用于 UI 驱动导入的管理路由
  frontend/     React + Vite + TypeScript + recharts
  data/         mychart.db, schema.json, settings.json（自动生成，已在 gitignore 中）
```

## 前置要求

- **Python** 3.11+
- **Node.js** 18+
- **你的 Epic MyChart 导出数据** —— 从你的患者门户申请。解压到方便的位置；该目录应包含 `EHITables/`（TSV 文件）、`EHITables Schema/`（HTML 数据字典）和 `FHIR/`（NDJSON 文件）。
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

首次启动时，应用会把你引导到 **Setup（设置）** 页面。把你 Epic 导出目录的绝对路径粘贴进去，点击 *Validate（校验）*、*Save（保存）*，再点击 *Start ingest（开始导入）*。导入进度会实时流式显示在界面上。

### 命令行替代方式

喜欢用脚本？同样的流水线也提供了命令行接口：

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

在应用的 **Ask AI（向 AI 提问）** 标签 → *Settings（设置）* 中，从下拉菜单里选一个模型（由 `ollama list` 填充）。聊天会通过工具调用查询你的 SQLite 数据库，因此**请使用在 [ollama.com/library](https://ollama.com/library) 上带有 `tools` 标签的模型**。

#### 按内存选择模型

在默认的 Q4 量化下，显存 / 统一内存的粗略预算约为 `参数量 × 0.6 GB`，再加上几 GB 给上下文。如果你只用 CPU，同样的数字适用于系统内存，只是 tokens/秒 会慢一些。

| 你的内存     | 推荐的支持工具调用的模型（Ollama tag）                                  |
| ----------- | --------------------------------------------------------------------- |
| 4–6 GB      | `qwen3:1.7b`, `qwen2.5:1.5b`, `granite4:1b`, `granite4:3b`            |
| 8 GB        | `qwen3:4b`, `qwen2.5:3b`, `phi4-mini:3.8b`, `granite3.3:2b`           |
| 12–16 GB    | `qwen3:8b` *（甜点区）*, `qwen2.5:7b`, `qwen3.5:9b`, `granite3.3:8b`   |
| 24–32 GB    | `qwen3:14b`, `phi4:14b`, `qwen3.5:27b`（较吃紧）, `mistral-small:24b`, `qwen3.6:27b` † |
| 48–64 GB    | `qwen3:30b`（MoE，速度快）, `gpt-oss:20b`, `qwen3:32b`, `qwen3.5:35b`, `qwen3.6:35b` † |
| 96 GB+      | `qwen3:235b`（MoE）, `gpt-oss:120b`, `qwen3.5:122b`                   |

说明：

- **Qwen 3 / 3.5**（阿里巴巴）是目前最常用的开源模型家族 —— 工具调用能力强，覆盖从 0.6B 到 235B MoE 的多种规模。
- **Qwen3 30B MoE** 每个 token 只激活约 3B 参数，因此速度接近 7B 模型，推理能力却接近更大的模型 —— 如果你有足够内存装下权重，性价比很高。
- **Phi-4-mini / Phi-4**（微软）在相同参数量下推理能力非常出色。
- **Granite 4** / **Granite 3.3**（IBM）体积小、速度快、针对工具调用做了调优 —— 很适合 8 GB 内存的笔记本。
- **gpt-oss**（OpenAI 开放权重）和 **Mistral Small 3** 是中大规模上不错的选择。本应用请跳过基础版 **Gemma 3**，它不支持工具调用；如果你想用 Google 的模型，请选 **Gemma 4**。
- 如果某个模型在使用工具时行为异常，降一档规模，或者换成 `qwen3` 系列。

† **qwen3.6** 是最新发布的（2026 年 4 月），目前只有 27B/35B 两个尺寸。它是 `thinking` 类型的模型，在代码 Agent 场景下得分很高；但刚发布的模型在头一两周内工具调用模板可能还不稳定 —— 如果出现工具调用格式错误，请回退到 `qwen3:32b` 或 `qwen3.5:27b`。

### 云端（需主动开启）

在启动后端**之前**设置 API Key：

```sh
export OPENAI_API_KEY=sk-...      # 或
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

然后在聊天设置抽屉里选择对应的服务商。界面上会显示横幅提示当前正在使用云端服务。**每轮对话都会把你的 PHI（受保护健康信息）发送给该服务商**，因此请确认你能接受对方的数据政策后再启用。

## 隐私与安全

- 后端仅绑定到 `127.0.0.1`，不会在局域网上监听。
- 运行时以只读方式打开 SQLite。
- `/api/sql` 端点会用 `sqlglot` 解析每条查询，拒绝非 `SELECT` / `WITH` 的语句，并自动注入行数限制。
- `data/`（包含你导入的数据库和设置）已在 gitignore 中。
- 应用不发送任何遥测数据。

## 环境变量

所有环境变量都是可选的 —— 你也可以直接在 Setup 页面配置。

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

每个阶段都是幂等且相互独立的，因此在修改 `ingest/tables.py` 中的精选表列表后，重新运行是安全的。

## 添加更多表

默认会把约 40 张临床表加载进 SQLite 以便快速访问。你导出中的其他任何表仍可通过 **Tables 浏览器**按需访问（从 TSV 流式读取）。要把一张表提升到 SQLite：

1. 在 `ingest/tables.py` 中加入它的名字（以及可选的索引列）。
2. 重新运行导入（Setup 页面 → *Re-ingest*，或在命令行中使用
   `--skip-schema --skip-fhir`）。

## 免责声明

本项目与 Epic Systems、任何医疗机构或任何电子病历厂商均无关联。使用风险自负。作者并非临床医生，本项目也不提供医学建议。

## 许可证

[MIT](LICENSE)
