#!/bin/bash
# 喵言汪语 V3 · 一体化全流程
# 本地运行，不需要 NAS。
# 用法: bash scripts/pipeline_all.sh [--target 300] [--count 10] [--daemon]
#   --target: 种子池 pending 目标数（默认 300）
#   --count:   本次派发卡片数（默认 10）
#   --daemon:  阶段三持续模式，处理完本次派发后继续守候新卡片
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

TARGET=300
COUNT=10
DAEMON=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --target) TARGET="$2"; shift 2 ;;
        --count)  COUNT="$2";  shift 2 ;;
        --daemon) DAEMON=true; shift ;;
        *) echo "用法: $0 [--target 300] [--count 10] [--daemon]"; exit 1 ;;
    esac
done

# ── 环境检查 ──
PYTHON=/opt/homebrew/bin/python3.11
if [ ! -f "$PYTHON" ]; then
    PYTHON=python3
fi

echo "🐱 喵言汪语 V3 一体化全流程"
echo "========================"
echo "Python: $($PYTHON --version 2>&1)"
echo "目标: target=$TARGET, count=$COUNT, daemon=$DAEMON"
echo ""

# ── .env ──
if [ ! -f config/.env ]; then
    echo "📝 创建 .env..."
    cat > config/.env << 'ENVEOF'
GATEWAY_URL=http://<GPU_SERVER_IP>:8080
XIANKA_MODEL=qwen35b
DOUHUA_MODEL=qwen35b
GATEWAY_AUTH=
PROXY=http://127.0.0.1:7897
ENVEOF
    echo "  已创建 config/.env"
fi

# ── 解锁 ──
bash scripts/unlock.sh 2>/dev/null || true

# ═══════════════════════════════════════
# 阶段一+二：种子生成 + 信源缓存 + 派发
# ═══════════════════════════════════════
echo ""
echo "📡 阶段一+二：种子生成 + 信源派发"
echo "-------------------------------------"
$PYTHON scripts/generate_and_dispatch.py --target "$TARGET" --count "$COUNT"

# ═══════════════════════════════════════
# 阶段三：卡片生产（本地 daemon）
# ═══════════════════════════════════════
echo ""
echo "⚙️  阶段三：卡片生产"
echo "-------------------------------------"

# 检查队列
CARDS_READY=$($PYTHON -c "
import json
q = json.loads(open('data/queue/cards.json').read())
ready = sum(1 for c in q.get('cards',[]) if c['status']=='ready')
done = sum(1 for c in q.get('cards',[]) if c['status']=='done')
print(f'{ready} {done}')
")
READY=$(echo "$CARDS_READY" | cut -d' ' -f1)
DONE=$(echo "$CARDS_READY" | cut -d' ' -f2)

if [ "$READY" -eq 0 ]; then
    echo "📭 无待生产卡片，跳过阶段三"
else
    echo "📊 队列: $READY ready, $DONE done"

    # 启动 dashboard（从项目根目录 serve，dashboard.html 在 output/ 下）
    if ! lsof -i :8899 >/dev/null 2>&1; then
        $PYTHON -m http.server 8899 > /dev/null 2>&1 &
        echo "  📊 dashboard: http://localhost:8899/output/dashboard.html"
    fi

    if [ "$DAEMON" = true ]; then
        echo "  🏭 启动持续生产模式 (daemon)..."
        $PYTHON -m src.main pipeline start --daemon &
        DAEMON_PID=$!
        echo "  PID: $DAEMON_PID"
        echo "  提示: 生产在后台持续运行"
        echo "  停止: kill $DAEMON_PID 或 bash scripts/daemon.sh stop"
    else
        echo "  🏭 启动生产流水线（处理 $READY 张后退出）..."
        $PYTHON -m src.main pipeline start --max-cards "$READY"
        echo "  ✅ 阶段三完成"
    fi
fi

# ── 报告 ──
echo ""
echo "========================"
echo "📊 最终报告"
echo "========================"
$PYTHON -c "
import json
q = json.loads(open('data/queue/cards.json').read())
cards = q.get('cards',[])
ready = sum(1 for c in cards if c['status']=='ready')
done = sum(1 for c in cards if c['status']=='done')
failed = sum(1 for c in cards if c['status']=='failed')
pending_src = sum(1 for c in cards if c.get('status','')=='pending_source')
print(f'  ✅ done:          {done}')
print(f'  ⏳ ready:         {ready}')
print(f'  ❌ failed:        {failed}')
print(f'  ⚠️  pending_source: {pending_src}')
print(f'  📝 output/cards/:  {len(list(Path(\"output/cards\").glob(\"*.md\")))} 个文件')
" 2>/dev/null || echo "  (报告生成失败)"

# ── 锁定 ──
bash scripts/lock.sh 2>/dev/null || true

echo ""
echo "✅ 全流程完成"
echo ""
echo "产出位置:"
echo "  📄 卡片: output/cards/"
echo "  📊 面板: http://localhost:8899/dashboard.html"
echo ""
if [ "$DAEMON" = false ]; then
    echo "提示: 想持续生产可加 --daemon 参数"
fi
