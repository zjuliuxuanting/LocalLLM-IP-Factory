# 脱敏修复计划

## 问题清单

| # | 严重度 | 问题 | 涉及文件 |
|---|--------|------|---------|
| 1 | 🔴 | 运行时数据文件被 git 追踪 | `.gitignore`、`data/queue/cards.json`、`data/seed_pool.json`、`data/source_registry/index.json` |
| 2 | 🔴 | JSON 文件中 `cache_path`/`source_files` 暴露本地绝对路径 | `data/queue/cards.json`、`data/source_registry/index.json` |
| 3 | 🟡 | push_to_nas.py 暴露 NAS 路径 | `scripts/push_to_nas.py` |
| 4 | 🟡 | watchdog.sh 注释暴露 NAS cron 路径 | `scripts/watchdog.sh` |
| 5 | 🟡 | NAS_MOUNT.md 暴露基础设施信息 | `NAS_MOUNT.md` |

---

## 修复步骤

### Step 1: .gitignore 追加运行时数据目录

在 `.gitignore` 中追加：

```
data/queue/
data/seed_pool.json
data/source_registry/
```

### Step 2: 从 git 移除已追踪的运行时数据文件

```bash
git rm --cached data/queue/cards.json
git rm --cached data/seed_pool.json
git rm --cached data/source_registry/index.json
```

### Step 3: 确保初始数据文件存在（代码依赖它们）

创建空的数据文件作为占位，让代码能正常启动：

- `data/queue/cards.json` → `{"cards": []}`
- `data/seed_pool.json` → 空系列定义
- `data/source_registry/index.json` → `{}`

这些文件在 `.gitignore` 排除后，`git checkout` 时不会自动创建，所以需要有一个初始化机制。

解决方案：在 `pipeline_all.sh` 和 `reset_all.py` 中确保这些文件存在。或者创建一个 `scripts/init_data.py` 脚本。

### Step 4: 脱敏 push_to_nas.py NAS 路径

将 `NAS_PATH` 改为占位符：

```python
NAS_PATH = "/<NAS_MOUNT>/workspace_openclaw/<PROJECT_NAME>/"
```

### Step 5: 脱敏 watchdog.sh cron 注释

watchdog.sh L3：

```bash
# cron: * * * * * /bin/bash <PROJECT_ROOT>/scripts/watchdog.sh
```

### Step 6: 脱敏 NAS_MOUNT.md

移除 NAS 型号、OpenClaw 端口、项目路径等基础设施信息，只保留通用的挂载说明。

### Step 7: 提交并推送

```bash
git add -A
git commit -m "脱敏：运行时数据 gitignore + 路径信息清理"
git push
```
