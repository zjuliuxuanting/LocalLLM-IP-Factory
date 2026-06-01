#!/bin/bash
# 喵言汪语 V3 · NAS 阶段三启动脚本
# 推到 NAS 后运行：bash scripts/nas_start.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "🐱 喵言汪语 V3 · NAS 阶段三"
echo "========================"

# 1. 安装依赖
echo "📦 检查 Python..."
python3 --version
echo ""

# 2. 写 .env（如果不存在）
if [ ! -f config/.env ]; then
    cat > config/.env << 'EOF'
GATEWAY_URL=http://<GPU_SERVER_IP>:8080
XIANKA_MODEL=qwen35b
DOUHUA_MODEL=qwen35b
GATEWAY_AUTH=
PROXY=http://127.0.0.1:7890
EOF
    echo "✅ .env 已创建"
fi

# 3. 检查队列
CARDS=$(python3 -c "
import json
with open('data/queue/cards.json') as f: q = json.load(f)
ready = sum(1 for c in q.get('cards',[]) if c['status']=='ready')
done = sum(1 for c in q.get('cards',[]) if c['status']=='done')
print(f'{ready} ready, {done} done')
")
echo "📊 队列: $CARDS"

# 4. 启动 daemon
bash scripts/daemon.sh start

# 5. Watchdog
WATCHDOG_CMD="* * * * * /bin/bash $SCRIPT_DIR/scripts/watchdog.sh"
(crontab -l 2>/dev/null | grep -v "watchdog.sh"; echo "$WATCHDOG_CMD") | crontab -
echo "⏰ watchdog cron 已配置"

# 6. 面板
echo ""
echo "========================"
echo "✅ 阶段三启动完成"
echo ""
echo "查看状态:"
echo "  bash scripts/daemon.sh status"
echo "  python3 -m src.main status"
echo "  ls output/cards/ | wc -l"
echo ""
echo "面板: python3 -m http.server 8899 --directory output/"
echo "  然后浏览器打开 http://<NAS_IP>:8899/dashboard.html"
echo "========================"
