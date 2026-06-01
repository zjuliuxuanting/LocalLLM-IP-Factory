#!/bin/bash
# 喵言汪语 · 守护启动脚本
# 用法: ./scripts/daemon.sh start|stop|status|restart
#
# 架构：
#   daemon 进程自驱动跑满 GPU（一张接一张，不间断）
#   cron 只做 watchdog：每分钟检查 daemon 是否存活，挂了就拉起
#   不再用 cron 推单张卡片
#
# 启动后 GPU 会持续跑直到所有 pending 卡片处理完，
# 队列空后每 60s 检查一次是否有新卡片。

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT="喵言汪语"
PID_FILE="$SCRIPT_DIR/.daemon.pid"
LOG_FILE="$SCRIPT_DIR/output/logs/daemon.log"

start_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "[$(date '+%H:%M:%S')] $PROJECT daemon 已在运行 (PID=$(cat "$PID_FILE"))"
        return 0
    fi

    cd "$SCRIPT_DIR"

    # 加载 .env
    if [ -f config/.env ]; then
        set -a; source config/.env; set +a
    fi

    echo "[$(date '+%H:%M:%S')] 启动 $PROJECT daemon..."
    nohup python3 -m src.main pipeline start --daemon >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "[$(date '+%H:%M:%S')] PID=$(cat "$PID_FILE")"
}

stop_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "[$(date '+%H:%M:%S')] 已停止 daemon (PID=$PID)"
        fi
        rm -f "$PID_FILE"
    else
        echo "[$(date '+%H:%M:%S')] daemon 未在运行"
    fi
}

status_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        PID=$(cat "$PID_FILE")
        echo "[$(date '+%H:%M:%S')] ✅ $PROJECT daemon 运行中 (PID=$PID)"

        # 看日志最后几行
        echo ""
        echo "最近日志:"
        tail -3 "$LOG_FILE" 2>/dev/null || echo "  (暂无日志)"

        # 看产出
        CARD_COUNT=$(ls "$SCRIPT_DIR/output/cards/"*.md 2>/dev/null | wc -l | tr -d ' ')
        echo ""
        echo "成品卡片: $CARD_COUNT 张"
    else
        echo "[$(date '+%H:%M:%S')] ❌ $PROJECT daemon 未运行"
    fi
}

case "${1:-start}" in
    start)   start_daemon ;;
    stop)    stop_daemon ;;
    restart) stop_daemon; sleep 2; start_daemon ;;
    status)  status_daemon ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
