#!/bin/bash
# 喵言汪语 · Watchdog（给 cron 用）
# cron: * * * * * /bin/bash /volume1/work_space/workspace_openclaw/喵言汪语/scripts/watchdog.sh
#
# 只做一件事：确保 daemon 进程活着。
# 不推卡片——卡片由 daemon 自己连续推进。
# 如果 daemon 死了（GPU OOM / 进程被杀 / 异常退出），watchdog 在 1 分钟内拉起。

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$SCRIPT_DIR/.daemon.pid"
LOG_FILE="$SCRIPT_DIR/output/logs/daemon.log"

# 如果 pid 文件存在且进程活着 → 什么都不做
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    exit 0
fi

# 进程不存在 → 拉起
cd "$SCRIPT_DIR"
if [ -f config/.env ]; then
    set -a; source config/.env; set +a
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ daemon 已死，重新拉起..." >> "$LOG_FILE"
nohup python3 -m src.main pipeline start --daemon >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PID=$!" >> "$LOG_FILE"
