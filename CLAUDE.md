# 喵言汪语 V3 — 宠物按钮沟通内容IP

三阶段全自动流水线：**种子生成 → 信源采集 + 卡片派发 → 正文生产**。

## 快速开始

```bash
# 安装依赖
pip install crawl4ai
http_proxy=http://<PROXY_HOST>:7897 python3 -m playwright install chromium

# 一条命令跑通三阶段
bash scripts/pipeline_all.sh --target 300 --count 10
```

## 三阶段架构

| 阶段 | 脚本 | 做什么 | 依赖 |
|------|------|--------|------|
| 一 | `generate_and_dispatch.py` 内嵌 | 显卡妹生成种子 → `seed_pool.json` | 3080 GPU |
| 二 | `generate_and_dispatch.py` 内嵌 | Crawl4AI 搜信源 → LLM排序 → 缓存 → 建卡 | Crawl4AI + 代理 |
| 三 | `pipeline_all.sh` → `orchestrator.py` | 7阶段流水线写正文 → `output/cards/` | 3080 GPU |

## 核心文件

| 文件 | 说明 |
|------|------|
| `scripts/pipeline_all.sh` | **全流程入口**，一键跑通三个阶段 |
| `scripts/generate_and_dispatch.py` | 阶段一+二：种子生成 + 信源派发（Crawl4AI + LLM增强） |
| `scripts/daemon.sh` | 阶段三守护进程 |
| `src/pipeline/orchestrator.py` | 7阶段流水线协调器 |
| `config/series_definitions.py` | 7个原始系列定义 |
| `data/seed_pool.json` | 种子池（B/R/M/S/Q/F/P 七系列） |
| `data/queue/cards.json` | 卡片队列 |
| `docs/V3_DESIGN.md` | 完整设计文档 |

## 监视面板

```bash
# 手动启动
python3 -m http.server 8899
# 浏览器打开
open http://localhost:8899/output/dashboard.html
```

## 数据流

```
显卡妹(qwen35b @ <GPU_SERVER>:8080)
  │
  ├─ 阶段一: 生成种子 → seed_pool.json
  │
  ├─ 阶段二: Crawl4AI搜信源 → LLM排序 → 缓存 → 建卡
  │   ├─ data/source_cache/shared/     ← 信源缓存
  │   ├─ data/source_registry/         ← 信源注册
  │   └─ data/queue/cards.json         ← 卡片队列 (status=ready)
  │
  └─ 阶段三: 7阶段流水线 → output/cards/{id}.md
      └─ data/queue/cards.json         ← 更新状态 (status=done)
```

## 权限

`src/` `config/` 默认只读（chmod 444）。脚本自动 unlock → 执行 → lock。

## 设计文档

完整设计文档：`docs/V3_DESIGN.md`
