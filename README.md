# LocalLLM-IP-Factory


> **目标：** 榨干本地 LLM 算力，全自动内容流水线
> **定位：** 用本地 LLM 按系列批量生产垂直领域科普/故事/调研/方法论等内容卡片

三阶段全自动流水线：**种子生成 → 信源采集 + 卡片派发 → 正文生产**。

---

## 快速开始

```bash
# 1. 安装依赖
pip install crawl4ai
http_proxy=http://<PROXY>:7897 python3 -m playwright install chromium

# 2. 编辑环境变量
cp config/.env.example config/.env
# 填入你的 GPU 地址和代理

# 3. 放话题定义文件到 docs/SERIES_TOPICS.md（格式见下文）

# 4. (可选) 测试本地信源功能
cp demo_data/example_document.txt data/source_cache/local/

# 5. 跑
bash scripts/pipeline_all.sh --target 300 --count 10
```

---

## 🧠 PM agent：初始化话题定义

将以下提示词发给 PM agent，生成 `docs/SERIES_TOPICS.md`：

> **"请阅读项目代码和现有文档，理解这个内容 IP 的业务逻辑。然后根据你对项目的理解，生成 `docs/SERIES_TOPICS.md`——这是种子生成阶段依赖的话题定义文件，后续所有内容生产都基于这个文件。**
>
> **要求：**
> - 每系列一个 `##` 区块，key 为单字母（如 A/B/C/D/E/F/G）
> - 每个区块必须包含：风格、引擎（web/pubmed）、目标规则、关键词规则、子话题、示例种子（含 title/goal/engine/kw）、备注
> - 示例种子必须是可以直接用于网络搜索的英文 kw
> - 风格描述要能指导 LLM 的写作语气
> - 种子生成会读取此文件来构建 prompt，所以定义要清晰、具体
>

> **项目目标：** 榨干本地 LLM 算力，全自动内容流水线
>
> **输出格式参考：** 见下方代码块"

参考格式：

```
## A：背景知识

- 风格：科普叙事，有温度有深度，不学术腔
- 引擎：pubmed（优先），web
- 目标规则：科普写作目标，必须包含具体知识点
- 关键词规则：英文关键词 ≥3 词
- 子话题：子话题1、子话题2、子话题3
- 示例种子：
  - title: 示例标题
  - goal: 示例写作目标，包含具体内容和叙事角度
  - engine: pubmed
  - kw: english search keywords at least 3 words
- 备注：系列定位说明
```

文件路径 `docs/SERIES_TOPICS.md`，种子生成阶段自动读取。要调整话题方向，直接修改此文件。

---

## 三阶段架构

| 阶段 | 做什么 | 产出 | 依赖 |
|------|--------|------|------|
| **一：种子生成** | LLM 按系列生成话题种子 | `seed_pool.json` | GPU |
| **二：信源派发** | 搜索引擎 → 网页抓取 → LLM 排序 → 缓存 → 建卡 | `source_cache/` · `source_registry/` · `cards.json` | Crawl4AI + 代理 |
| **三：正文生产** | 7 阶段流水线（研究→大纲→初稿→自审→修订→润色→核查） | `output/cards/{id}.md` · `cards.json`(status→done) | GPU |

## 核心文件

| 文件 | 说明 |
|------|------|
| `scripts/pipeline_all.sh` | **全流程入口**，支持 `--repeat` `--duration` `--interval` |
| `scripts/generate_and_dispatch.py` | 阶段一+二：种子生成 + 信源派发 |
| `scripts/translate_sources.py` | 格式转换：将 `local/` 中的 PDF/Office/HTML 转为 markdown |
| `scripts/reset_all.py` | 一键清空卡片、种子、缓存（保留本地信源） |
| `docs/SERIES_TOPICS.md` | **系列话题定义**— 你的内容 IP 文件，种子生成依赖 |
| `src/models/prompts/seed.py` | 种子生成 prompt，从 `SERIES_TOPICS.md` 读取 |
| `src/models/prompts/draft.py` | 初稿 prompt，含信源引用指令 |
| `config/series_definitions.py` | 系列 Python 定义（可编辑） |
| `config/.env.example` | 环境变量模板 |
| `data/seed_pool.json` | 种子池 |
| `data/queue/cards.json` | 卡片队列 |
| `src/pipeline/orchestrator.py` | 7 阶段流水线协调器 |

## 自定义

### 配置话题方向

系统默认带了 7 个示例系列（B/R/M/S/Q/F/P）。要改为你自己的：

1. 删除 `data/seed_pool.json` 里的示例系列，或重新生成
2. 编辑 `docs/SERIES_TOPICS.md`，改为你自己 IP 的话题
3. 可选：编辑 `config/series_definitions.py` 修改示例系列数据
4. 可选：编辑 `PROJECT_MAP.md` 修改卡片编号规则

### 环境变量

```bash
cp config/.env.example config/.env
```

| 变量 | 说明 | 示例 |
|------|------|------|
| `GATEWAY_URL` | LLM 推理服务地址 | `http://192.168.1.100:8080` |
| `XIANKA_MODEL` | 主模型名 | `qwen35b` |
| `PROXY` | 爬虫代理 | `http://127.0.0.1:7897` |

## 运行模式

```bash
# 单次运行（补种 → 派发 → 生产）
bash scripts/pipeline_all.sh --target 300 --count 10

# 循环 5 轮
bash scripts/pipeline_all.sh --target 300 --count 5 --repeat 5

# 跑 1 小时
bash scripts/pipeline_all.sh --target 300 --count 5 --duration 3600

# 带轮间间隔
bash scripts/pipeline_all.sh --target 300 --count 5 --repeat 5 --interval 30
```

## 监视面板 & 配置界面

`pipeline_all.sh` 会自动启动。如需手动启动：

```bash
python3 scripts/config_api.py --port 8899

# 浏览器打开
#   面板:   http://localhost:8899/output/dashboard.html
#   配置:   http://localhost:8899/output/config.html
```

### 配置页功能

- **在线修改** LLM 地址、模型、API 密钥、代理，保存写入 `config/.env`
- **实时状态** — 右上角显示 LLM 连接状态（已连接/不可达/未配置），走服务端代理避免跨域
- **测试连接** — 深度学习测试：先 ping 搜索引擎 API（PubMed/arXiv/Patent），再用 LLM 验证搜索结果是否为真实内容（防止 DDG 返回图片页骗过阈值）
- **引擎预检** — 种子生成前自动检测各引擎可用性，不可用引擎自动跳过并通知 LLM 换用替代引擎

### 信源引擎

| 引擎 | 后端 | 适用场景 |
|------|------|---------|
| `pubmed` | NIH E-utilities API | 科普/科研 |
| `arxiv` | arXiv API | 技术/前沿 |
| `patent` | Google Patents | 调研/产品 |
| `web` | 百度 / DDG / Wikipedia | 新闻/故事/问答 |

种子生成时 LLM 会根据引擎可用性和 kw 指引自动选择最合适的引擎。

## 数据流

```
LLM(qwen35b @ <GPU_SERVER>:8080)
  │
  ├── 阶段一: 读 docs/SERIES_TOPICS.md → 生成种子 → seed_pool.json
  │
  ├── 阶段二: DuckDuckGo/百度搜索 → Crawl4AI 抓取 → LLM 排序
  │           或: 本地信源优先匹配
  │   ├── data/source_cache/local/         ← 你的本地文档（PDF/DOCX/HTML/...）
  │   ├── data/source_cache/shared/        ← 信源缓存
  │   ├── data/source_registry/index.json  ← 信源注册中心
  │   └── data/queue/cards.json            ← 卡片队列 (status=ready)
  │
  └── 阶段三: 7 阶段流水线 → output/cards/{id}.md
      ├── S1 Research:  读取信源缓存
      ├── S2 Outline:   写大纲
      ├── S3 Draft:     写初稿 ← 引用信源材料
      ├── S4 Review:    质检
      ├── S5 Revise:    修订
      ├── S6 Polish:    润色
      ├── S7 Factcheck: 事实核查
      └── data/queue/cards.json → status 更新
```

## 本地信源（高优先级）

阶段二自动优先使用本地文档作为信源：

```bash
# 1. 把文档放入 local/
#    支持的格式：.pdf .doc .docx .html .htm .rtf .txt .md
open data/source_cache/local/

# 2. 用 LLM 转换格式（PDF→MD, Office→TXT, HTML→MD）
python3 scripts/translate_sources.py

# 3. 跑 pipeline，本地信源自动优先匹配
bash scripts/pipeline_all.sh --target 300 --count 10
```

匹配规则：`translate_sources.py` 在翻译时让LLM从文档内容中提取英文关键词，注册到 `source_registry`。`dispatch_one()` 用种子关键词与注册关键词匹配——有交集即匹配，优先作为信源（优先级 10，最高）。

`reset_all.py` 会保留 `local/` 目录不变，只清空运行产生的缓存。

## 权限

`src/` `config/` 下 .py 文件默认只读（chmod 444）。脚本自动解锁 → 执行 → 锁定。
