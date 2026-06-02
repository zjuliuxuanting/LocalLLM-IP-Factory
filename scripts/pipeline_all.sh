#!/bin/bash
# LocalLLM-IP-Factory · 一体化全流程
# 本地运行，不需要 NAS。
# 用法:
#   单次运行: bash scripts/pipeline_all.sh --target 50 --count 5
#   循环运行: bash scripts/pipeline_all.sh --target 50 --count 3 --repeat 3
#   定时运行: bash scripts/pipeline_all.sh --target 50 --count 3 --duration 3600
# 用法:
#   单次运行: bash scripts/pipeline_all.sh --target 50 --count 5
#   循环运行: bash scripts/pipeline_all.sh --target 50 --count 3 --repeat 3
#   定时运行: bash scripts/pipeline_all.sh --target 50 --count 3 --duration 3600

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# ── PID 锁：防止多个实例同时运行 ──
PIDFILE="/tmp/pipeline_all.pid"
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "❌ 已有 pipeline 实例在运行 (PID=$OLD_PID)，退出。"
        exit 1
    fi
fi
echo $$ > "$PIDFILE"
trap "rm -f $PIDFILE" EXIT

TARGET=50
COUNT=10
DAEMON=false
REPEAT=0
DURATION=0
INTERVAL=10

while [[ $# -gt 0 ]]; do
    case $1 in
        --target)   TARGET="$2";   shift 2 ;;
        --count)    COUNT="$2";    shift 2 ;;
        --repeat)   REPEAT="$2";   shift 2 ;;
        --duration) DURATION="$2"; shift 2 ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        --daemon)   DAEMON=true;   shift ;;
        *) echo "用法: $0 [--target 50] [--count 5] [--repeat N] [--duration SEC] [--interval SEC] [--daemon]"; exit 1 ;;
    esac
done

PYTHON=/opt/homebrew/bin/python3.11
if [ ! -f "$PYTHON" ]; then
    PYTHON=python3
fi

# ── .env ──
if [ ! -f config/.env ]; then
    echo "📝 创建 .env..."
    cat > config/.env << 'ENVEOF'
GATEWAY_URL=http://<GPU_SERVER>:8080
XIANKA_MODEL=qwen35b
DOUHUA_MODEL=qwen35b
GATEWAY_AUTH=
PROXY=http://<PROXY_HOST>:7897
ENVEOF
    echo "  已创建 config/.env"
fi

bash scripts/unlock.sh 2>/dev/null || true

# ── 加载 .env ──
if [ -f config/.env ]; then
    set -a; source config/.env; set +a
fi

# ── dashboard + 配置 API ──
if ! lsof -i :8899 >/dev/null 2>&1; then
    $PYTHON scripts/config_api.py > /dev/null 2>&1 &
    echo "📡 Dashboard + 配置 API 已启动 (端口 8899)"
fi

# ── 系列定义自动生成 ──
if $PYTHON -c "from config.series_definitions import all_series_keys; exit(0 if len(all_series_keys())==0 else 1)" 2>/dev/null; then
    echo "📝 系列定义为空，调用 LLM 从 SERIES_TOPICS.md 自动生成..."
    set -a; source config/.env 2>/dev/null; set +a
    $PYTHON scripts/import_series_names.py --apply 2>&1 | sed 's/^/  /'
fi

# ═══════════════════════════════════════
# 第零步：本地信源翻译（检测新文件 + 已修改文件）
# ═══════════════════════════════════════
LOCAL_DIR="data/source_cache/local"
if [ -d "$LOCAL_DIR" ] && [ -n "$(ls -A "$LOCAL_DIR" 2>/dev/null)" ]; then
    NEED_TRANSLATE=$($PYTHON scripts/check_local_files.py 2>/dev/null)
    NEED_COUNT=$(echo "$NEED_TRANSLATE" | grep -c '^' 2>/dev/null || echo "0")
    if [ -n "$NEED_TRANSLATE" ]; then
        echo ""
        echo "📁 第零步：本地信源翻译"
        echo "-------------------------------------"
        echo "$NEED_TRANSLATE"
        echo ""
        $PYTHON scripts/translate_sources.py
    fi
fi

# ═══════════════════════════════════════
# 网络预检：搜索引擎真实可用性（LLM 判断 + 仅一次）
# ═══════════════════════════════════════
echo ""
echo "🌐 网络预检..."
NET_STATUS=$($PYTHON << 'PYEOF'
import asyncio, json, pathlib, re, sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent if '__file__' in dir() else pathlib.Path.cwd()
sys.path.insert(0, str(SCRIPT_DIR))

status = {'proxy_ok': False, 'ddg_ok': False, 'baidu_ok': False, 'local_count': 0, 'ddg_detail': '', 'baidu_detail': ''}

# 本地信源
local_dir = pathlib.Path('data/source_cache/local')
if local_dir.exists():
    status['local_count'] = len([f for f in local_dir.iterdir() if f.is_file() and f.suffix not in ('.json','.yml','.yaml')])
reg_file = pathlib.Path('data/source_registry/index.json')
if reg_file.exists():
    reg = json.loads(open(reg_file).read())
    status['local_count'] += len([s for s in reg.values() if s.get('source_type') == 'local_translated'])

VERIFY_PROMPT = """判断以下网页内容是否是一个真实的搜索引擎结果页面（包含搜索结果链接），还是一个验证码/拦截/错误页面。

只回答一个词: REAL 或 FAKE

网页片段:
{content}"""

async def check_engine(name: str, url: str, proxy_ok: bool = False):
    try:
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler() as crawler:
            r = await crawler.arun(url)
            if not r or not r.markdown:
                return False, "", proxy_ok
            text = r.markdown[:3000]
            urls = re.findall(r'https?://[^\s)\]">]+', text)
            real_urls = [u for u in urls if not any(s in u for s in ('duckduckgo.com','baidu.com','google.com','bing.com'))]
            
            if len(real_urls) >= 3:
                # 用 LLM 确认不是验证码
                try:
                    from src.models.gateway import call_xianka
                    result = call_xianka(VERIFY_PROMPT.format(content=text[:2000]), max_tokens=10, temperature=0.1)
                    if result and 'FAKE' in result.upper():
                        return False, f"LLM判断为假页面", proxy_ok
                except: pass
                return True, f"{len(real_urls)} 个真实URL", True
            
            return False, f"仅 {len(real_urls)} 个URL", proxy_ok
    except Exception as e:
        return False, str(e)[:80], proxy_ok

async def main():
    ddg_ok, ddg_detail, proxy_ok = await check_engine('ddg', 'https://html.duckduckgo.com/html/?q=Python+programming+language')
    status['ddg_ok'] = ddg_ok
    status['proxy_ok'] = proxy_ok
    status['ddg_detail'] = ddg_detail
    
    baidu_ok, baidu_detail, _ = await check_engine('baidu', 'https://www.baidu.com/s?wd=Python编程语言')
    status['baidu_ok'] = baidu_ok
    status['baidu_detail'] = baidu_detail

asyncio.run(main())
print(json.dumps(status, ensure_ascii=False))
PYEOF
)

DDG_OK=$(echo "$NET_STATUS" | $PYTHON -c "import json,sys; print(json.loads(sys.stdin.read()).get('ddg_ok', False))" 2>/dev/null || echo "False")
BAIDU_OK=$(echo "$NET_STATUS" | $PYTHON -c "import json,sys; print(json.loads(sys.stdin.read()).get('baidu_ok', False))" 2>/dev/null || echo "False")
LOCAL_N=$(echo "$NET_STATUS" | $PYTHON -c "import json,sys; print(json.loads(sys.stdin.read()).get('local_count', 0))" 2>/dev/null || echo "0")
DDG_DETAIL=$(echo "$NET_STATUS" | $PYTHON -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('ddg_detail','') or d.get('baidu_detail',''))" 2>/dev/null || echo "")

echo "  DuckDuckGo: $([ "$DDG_OK" = "True" ] && echo '✅ 可达' || echo "❌ 不通 ($DDG_DETAIL)")"
echo "  百度:       $([ "$BAIDU_OK" = "True" ] && echo '✅ 可达' || echo "❌ 不通")"
echo "  本地信源:   $LOCAL_N 个"

echo "$NET_STATUS" > data/.network_status.json

# 循环或单次执行
# ── 注意：set -e 已移除，因为 generate_and_dispatch.py 退出时 asyncio 清理
#     会触发非零返回码，导致 bash 提前退出。改用手动错误检查。──
# ═══════════════════════════════════════

CYCLE=0
START_TS=$(date +%s)

while true; do
    CYCLE=$((CYCLE + 1))

    echo ""
    echo "=============================================="
    echo "🐱 LocalLLM-IP-Factory · 周期 $CYCLE"
    echo "=============================================="

    # ═════ 阶段一+二 ═════
    echo ""
    echo "📡 阶段一+二：种子生成 + 信源派发"
    echo "-------------------------------------"
    $PYTHON scripts/generate_and_dispatch.py --target "$TARGET" --count "$COUNT"

    # ═════ 阶段三 ═════
    echo ""
    echo "⚙️  阶段三：卡片生产"
    echo "-------------------------------------"
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
        echo ""
        echo "▶ 阶段三开始..."
        echo "  🏭 生产卡片 $READY 张，实时进度:"
        # 在后台 tail pipeline.jsonl，提取 msg 字段显示
        LOGFILE="output/logs/pipeline.jsonl"
        : > "$LOGFILE"
        (tail -f "$LOGFILE" 2>/dev/null | while read line; do
            echo "$line" | /opt/homebrew/bin/python3.11 -c "
import sys,json
try:
    d=json.loads(sys.stdin.read())
    stage=d.get('stage','') or d.get('logger','')
    card=d.get('card_id','')
    msg=d.get('msg','')
    dur=d.get('duration_s','')
    if dur: dur=f'({dur}s)'
    tag=f'{stage}/{card}' if card else stage
    print(f'    {tag} {msg} {dur}')
except:
    print(f'    {sys.stdin.read()[:120]}')
" 2>/dev/null
        done) &
        TAIL_PID=$!
        if [ "$DAEMON" = true ]; then
            $PYTHON -m src.main pipeline start --daemon
        else
            $PYTHON -m src.main pipeline start --max-cards "$READY"
        fi
        kill $TAIL_PID 2>/dev/null
        wait $TAIL_PID 2>/dev/null
        echo "  ✅ 阶段三完成"
    fi

    # ── 本轮报告 ──
    echo ""
    echo "📊 周期 $CYCLE 报告"
    $PYTHON -c "
import json
q = json.loads(open('data/queue/cards.json').read())
cards = q.get('cards',[])
ready = sum(1 for c in cards if c['status']=='ready')
done = sum(1 for c in cards if c['status']=='done')
failed = sum(1 for c in cards if c['status']=='failed')
print(f'  ✅ done: {done}  ⏳ ready: {ready}  ❌ failed: {failed}')
" 2>/dev/null

    # ── 判断是否继续循环 ──
    if [ "$REPEAT" -gt 0 ] && [ "$CYCLE" -ge "$REPEAT" ]; then
        echo ""
        echo "🏁 达到循环次数上限 ($REPEAT)，退出"
        break
    fi

    if [ "$DURATION" -gt 0 ]; then
        NOW=$(date +%s)
        ELAPSED=$((NOW - START_TS))
        if [ "$ELAPSED" -ge "$DURATION" ]; then
            echo ""
            echo "🏁 达到运行时长上限 (${DURATION}s)，退出"
            break
        fi
    fi

    # ── 单次模式（无 --repeat 也无 --duration）→ 只跑一轮 ──
    if [ "$REPEAT" -eq 0 ] && [ "$DURATION" -eq 0 ]; then
        break
    fi

    echo ""
    echo "⏳ 等待 ${INTERVAL}s 后下一轮..."
    sleep "$INTERVAL"
done

# ── 最终报告 ──
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
" 2>/dev/null || echo "  (报告生成失败)"

# ── 锁定 ──
bash scripts/lock.sh 2>/dev/null || true

echo ""
echo "✅ 全流程完成"
echo ""
echo "产出位置:"
echo "  📄 卡片: output/cards/"
echo "  📊 面板: http://localhost:8899/output/dashboard.html"
