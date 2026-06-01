# 喵言汪语 V3.0 设计文档

## 核心原则

1. **三阶段分离**：种子生成 → 卡片派发+信源缓存 → 卡片生产，各阶段独立，不可混用
2. **信源前置**：卡片进入生产前，信源必须已在硬盘上。生产阶段禁止联网抓取
3. **显卡妹权限边界**：可写 output/cards/、output/drafts/、output/logs/。禁止修改任何 .py/.json/.md 配置文件
4. **所有代码修改走 git**，有 commit 追溯

## 部署架构

| 阶段 | 在哪跑 | 用什么 | 触发方式 |
|------|--------|--------|---------|
| 阶段一二 | 本地 Mac | 显卡妹(qwen35b @ 3080) + 本地 AI | 手动 |
| 阶段三 | NAS | 显卡妹(qwen35b @ 3080) + daemon | daemon 自驱动 |

阶段一二共享本地的 seed_pool / registry / cards.json。完成后 `rsync` 推到 NAS，NAS 只跑阶段三。

## 三阶段流程

```
[本地 Mac]                            [NAS]
阶段一+二: 种子生成+信源缓存+派发       阶段三: 卡片生产
                                         
seed_pool.json → 信源缓存 shared/       S1 读缓存
  → cards.json (ready)                  S2-S6 写卡
  → source_registry/index.json          S7 核查
                                        ❌ 禁止联网
                    │
                    └── rsync ──→ NAS
```

## 第零步：系列扩展（全自动）

在种子生成之前运行。每天检查，自动提案，自动写入。

### 触发参数

| 参数 | 值 |
|------|-----|
| 检查频率 | 每天 |
| 饱和阈值 | 子话题覆盖 ≥ 70% |
| 触发条件 | ≥1 系列饱和 |
| 冷却期 | 新系列创建后 3 天内不重复创建同系列 |
| 总量上限 | 活跃系列 ≤ 16 个 |

### 自动审批路径

```
检测饱和 → 生成提案 → 四道校验 + 三条安全阀
                          │
                    ┌─────┼─────┐
                    ▼     ▼     ▼
                 全部通过  部分通过  挂了
                    │       │       │
                 验证分≥8  5≤分<8  分<5
                    │       │       │
                    ▼       ▼       ▼
                 自动写入  写staging  自动拒绝
                           等人看
```

### 四道硬性校验
1. 关联 ≥2 个现有系列
2. ≥3 个 seed 通过信源验证
3. 语义重叠度 < 40%
4. 内容边界定义清晰

### 三条安全阀
1. 活跃系列总数 ≤ 16
2. 同系列 3 天冷却期
3. 写入 ≠ 上线：自动写入后不会自动 dispatch 到卡片队列，人类手动触发

## 阶段一：种子生成

**运行位置**：本地 Mac（调 3080 显卡妹），手动触发。

**目标**：种子池 pending 保持 ~500 个。

**输入**：`config/series_definitions.py`（系列定义：topic/style/forbidden/engine_pref/subtopics）

**种子结构**：
```json
{
  "title": "犬类驯化起源：考古学与基因组学的双重证据",
  "goal": "综合考古学发现和DNA研究，讲述狼如何在15000年中逐步演化为家犬",
  "engine": "pubmed",
  "kw": "dog domestication origin archaeological genomic evidence",
  "status": "pending"
}
```

**执行脚本**：`scripts/seed_generator.py`

**过程**：
1. 遍历所有系列，检查 `seed_pool.json` 中该系列 pending 种子数
2. pending < 目标的系列 → 调显卡妹（qwen35b @ <GPU_SERVER>:8080）按系列约束生成候选
3. `seed_gate.py` 5维质检：goal可执行性、kw质量、标题去重、标题吸引力、engine合法性
4. engine 必须来自 `config/settings.py` 的 `ENGINE_MAP`
5. 通过 → 写入 `seed_pool.json`，status=pending

**输出**：`seed_pool.json`，所有种子 status=pending

**触发**：手动执行 `python3 scripts/seed_generator.py`，或本地 AI 在 pending 不足时调用

**不做的事**：不抓信源、不创建卡片队列、不调 NAS

## 阶段二：卡片派发 + 信源缓存

**运行位置**：本地 Mac，手动触发。**不调显卡妹**（纯 IO + WebSearch）。

**输入**：`seed_pool.json`（pending 种子）+ `ENGINE_MAP`

**信源采集工具**：**WebSearch**（Claude 内置）。不用 curl，不用代理，不用 WebFetch。

测试结果（2026-05-31）：
| 引擎 | WebSearch | WebFetch | 结论 |
|------|-----------|----------|------|
| 百度百科 | ✅ 完整抓取（数据、年代、实验） | ❌ 被拦 | WebSearch 够用 |
| Wikipedia | ✅ 之前测试全部正常 | ❌ 被拦 | 同上 |

WebSearch 返回的内容（标题 + URL + 摘要 + 关键事实）直接写入 `shared/` 当信源缓存，不需要二次抓取。

**过程**：
1. 取 pending 种子，先查 `source_registry/index.json` 关键词匹配
2. 命中 → 直接链接，跳过搜索
3. 未命中 → **WebSearch** 搜索（中文百度百科 + 英文 Wikipedia/学术） → 走降级链
4. 搜索结果缓存到 `data/source_cache/shared/`
5. 信源元数据注册到 `data/source_registry/index.json`
6. 种子转为卡片条目，写入 `data/queue/cards.json`，status=ready

**降级链**：L0 原始 → L1 引擎降（pubmed→wikipedia→web）→ L2 kw降（提取核心词 OR 连接）→ L3 双重降 → L4 source_failed。每级降级后**先查注册中心**，命中即停。

**输出**：`cards.json`（status=ready）+ `source_cache/shared/` + `source_registry/index.json`

**不做的事**：不写正文、不调 GPU、不调显卡妹

## 推送 NAS（阶段二→阶段三的桥梁）

**谁执行**：你敲 `/push-to-nas`，Skill 自动跑。

**流程**：

```
/push-to-nas
  │
  ├─ ① 遍历 cards.json 所有 ready 卡片
  │    查每张的 claims.source_id → 核对 shared/ 文件是否存在
  │
  ├─ ② 不全的 → 标记 pending_source，不推
  │    打印 "缺 N 个信源，留在本地"
  │
  ├─ ③ 全的 → rsync 推 NAS
  │    cards.json + source_cache/shared/ + source_registry/
  │
  └─ ④ 报告: "推了 N 张 ready，M 张缺信源未推"
```

**这条命令保证**：NAS 上的 S1 永远只读已有缓存，永远不会遇到"缓存文件不存在"。

## 阶段三：卡片生产（7阶段流水线）

**输入**：`cards.json`（ready 卡片）+ `source_cache/shared/`（已缓存信源）+ `source_registry/index.json`

**7个阶段**：

| 阶段 | 名称 | 做什么 | 调GPU |
|------|------|--------|-------|
| S1 | 研究 | 从 `source_registry` 读缓存信源，load 进 context | ❌ IO |
| S2 | 大纲 | xianka 根据信源生成结构化大纲（JSON） | ✅ |
| S3 | 初稿 | xianka 根据大纲写出正文 | ✅ |
| S4 | 自审 | douhua 对初稿多维度评分（JSON） | ✅ |
| S5 | 修订 | xianka 根据自审意见修改 | ✅ |
| S6 | 润色 | douhua 文字打磨 | ✅ |
| S7 | 核查 | douhua 逐条核对事实与信源一致性（JSON） | ✅ |

**S3 质检**：纯规则，不调模型。检查内容非空、无占位符、无代码块、字数合规、无禁词、无重复段落、信息密度达标

**输出**：`output/cards/{card_id}.md` + 更新 `cards.json` status=done

**禁止**：curl/联网/抓取信源。S1 只能读已有缓存。

## 权限模型

| 角色 | 可写 | 只读 | 禁止 |
|------|------|------|------|
| 显卡妹(qwen35b) | output/cards/, output/drafts/, output/logs/ | src/, config/, data/ | 修改任何 .py/.json/.md |
| 豆花(douhua) | cards.json(status), 质检报告 | src/, config/ | 修改 pipeline 代码 |
| 本地AI(Claude) | seed_pool.json, source_cache/, source_registry/ | src/ | 修改 pipeline 代码 |
| 人类 | 全部 | - | - |

## 显卡妹职责边界

✅ 能做：
- 7阶段流水线生成正文
- S4 自审 + S7 事实核查
- 写入 output/cards/ + output/drafts/ + output/logs/

❌ 不能做：
- 修改 src/ 下任何 .py 文件
- 修改 config/ 下任何文件
- 修改 cards.json 的 status 字段
- 修改 seed_pool.json
- 启动/停止 daemon 进程
- 抓取信源（curl/联网）
- git 操作

## daemon 行为约束

```
daemon = 纯循环:
  while True:
    取下一张 status=ready 的卡片
    跑 7 阶段流水线
    写入 output/cards/
    更新 cards.json status=done
    下一张

无自主决策：不重试、不重置、不选择卡片顺序、不修改配置
```

## 引擎来源

种子 engine 字段必须来自 `config/settings.py` 的 `ENGINE_MAP`：

| engine key | 实际抓取方式 | 适用场景 |
|-----------|-------------|---------|
| pubmed | PubMed API | 学术论文（B系列） |
| arxiv | arXiv API | 预印本 |
| wikipedia | Wikipedia API | 百科词条 |
| web | 通用网页抓取 | 行业数据、产品信息 |
| patent | Google Patents | 专利检索 |
| semantic | Semantic Scholar | 学术文献 |
| britannica | 大英百科 | 百科词条 |
| nih | NIH 数据库 | 医学/生物 |

种子生成时硬校验：`seed.engine in ENGINE_MAP`，不在则拒绝。

## 信源搜索降级策略

阶段二信源缓存时，原始 kw 可能搜出 0 结果。四层降级链：

```
L0 原始: engine + 完整kw，原样搜索
  ├─ 有结果 → 缓存，done
  └─ 0结果 → L1 引擎降级
       │
L1 引擎降级: kw不变，引擎降级 pubmed→wikipedia→web
  ├─ 有结果 → 缓存，done
  └─ 0结果 → L2 kw降级
       │
L2 kw降级: 提取2-4个核心词，OR连接。引擎保持L1
  ├─ 有结果 → 缓存，done
  └─ 0结果 → L3 双重降级
       │
L3 双重降级: 最简2个核心词OR + web引擎
  ├─ 有结果 → 缓存，done
  └─ 0结果 → source_failed
```

### 降级规则

| 级别 | kw 策略 | 引擎策略 |
|------|---------|---------|
| L0 | 完整 kw | 种子指定的 engine |
| L1 | 不变 | pubmed→wikipedia→web |
| L2 | 提取 2-4 个核心英文词，OR 连接 | 保持 L1 引擎 |
| L3 | 最简 2 词 OR | web |
| 失败 | - | 标记 source_failed |

### 测试验证（2026-05-31）

| 测试 | L0 | L2 | 结论 |
|------|-----|-----|------|
| B: cat hissing | ✅ 学术论文 | ✅ TICA+Wikivet | 质量持平 |
| R: pet facial recognition privacy | ❌ 0结果 | ✅ ITU国际标准+学术论文 | 降级救了它 |
| M: pet button training | ✅ PetMD+书籍 | ✅ PetMD+UC研究 | 质量持平 |

降级不会显著降低信源质量，对窄领域话题甚至能找到更好的替代源。

## V3.0 开发任务清单

### P0 — 项目结构（必须先做）

- [ ] **新建 V3 项目文件夹**：`<PROJECT_ROOT>/`，干净的 V3.0 代码库
- [ ] **权限基础设施**：`unlock.sh` / `lock.sh` 脚本，`chmod 444` 锁定 src/ config/，跑 skill 前上锁
- [ ] **三个 Skill 文件**：`/seed-generate`（阶段一）、`/source-dispatch`（阶段二）、`/push-to-nas`（同步推送）
- [ ] **拆分 seed_factory.py**：种子生成和卡片派发分离为两个独立模块
- [ ] **新建 source_downgrader.py**：实现四层降级链（L0→L1→L2→L3），由阶段二信源缓存脚本调用
- [ ] **S1 禁网**：`research.py` 去掉 curl/联网逻辑，只从 `source_cache/shared/` 读缓存
- [ ] **daemon 去自主决策**：去掉 `_retry_source_failed`、自动重置等逻辑，改为纯循环
- [ ] **HTML 状态面板**：daemon 每完成一张卡调用 `generate_dashboard.py`，生成 `output/dashboard.html`，浏览器打开可见进度条+日志+信源统计，30s 自动刷新

### P1 — 权限与隔离

- [ ] **显卡妹文件权限**：NAS 上 `chmod` 限制显卡妹进程对 src/ config/ 只有读权限
- [ ] **状态更新分离**：cards.json 的 status 变更由独立脚本（豆花）执行，不嵌入 daemon
- [ ] **git 强制**：所有 .py/.json 配置修改必须走 git commit

### P2 — 质量与容错

- [ ] **重试机制设计**：卡片生产失败后由谁重试、最多几次、间隔多久
- [ ] **source_failed 处理**：降级到 L4 仍无信源的卡片，人工介入流程
- [ ] **质检通过率监控**：daemon 运行时输出 ready→done 转化率

### P3 — 数据迁移

- [ ] **V2.0 存量迁移**：2311张卡片、629条信源迁移到 V3.0 三阶段格式
- [ ] **旧 seed_pool 清理**：移除 goal 为标签型的旧种子
- [ ] **本地↔NAS 同步方案**：信源缓存和队列的同步频率与方向

## 待讨论事项

- [x] 种子→卡片派发时，信源匹配失败的降级策略
- [ ] 卡片生产失败的重试机制（由谁触发、最多几次）
- [ ] 本地 AI 与 NAS daemon 的数据同步频率
- [ ] V2.0 存量数据迁移方案（2311张卡片、629条信源）
