"""喵言汪语 · 统一配置

纯配置和路径定义。所有 IO 操作通过 src/io/store.py 完成。
敏感信息优先从环境变量读取，其次是 .env 文件。
"""
import os
from pathlib import Path

# ── 项目根目录 ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── 数据目录 ──
DATA_DIR = PROJECT_ROOT / "data"
QUEUE_DIR = DATA_DIR / "queue"
CACHE_DIR = DATA_DIR / "source_cache"
KG_DIR = DATA_DIR / "knowledge_graph"
REF_DIR = DATA_DIR / "reference"

# ── 输出目录 ──
OUTPUT_DIR = PROJECT_ROOT / "output"
CARDS_DIR = OUTPUT_DIR / "cards"
DRAFTS_DIR = OUTPUT_DIR / "drafts"
REPORTS_DIR = OUTPUT_DIR / "reports"
LOGS_DIR = OUTPUT_DIR / "logs"
METRICS_DIR = OUTPUT_DIR / "metrics"

# ── 配置文件 ──
QUEUE_FILE = QUEUE_DIR / "cards.json"
SEED_POOL_FILE = DATA_DIR / "seed_pool.json"
PROJECT_MAP_FILE = PROJECT_ROOT / "PROJECT_MAP.md"
NODES_FILE = KG_DIR / "nodes.json"
EDGES_FILE = KG_DIR / "edges.json"
SEMANTIC_STATE_FILE = KG_DIR / "semantic_state.json"

# ── 本地模型 Gateway（3080 单端口） ──
# ⚠️ 3080 只有 1 个推理进程端口，xianka 和 douhua 共享同一端口，通过不同 temperature/system_prompt 区分行为
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8080")
XIANKA_GATEWAY = os.environ.get("XIANKA_GATEWAY", GATEWAY_URL)
DOUHUA_GATEWAY = os.environ.get("DOUHUA_GATEWAY", GATEWAY_URL)
GATEWAY_AUTH = os.environ.get("GATEWAY_AUTH", "")

# ── 本地模型名（默认 qwen35b） ──
XIANKA_MODEL = os.environ.get("XIANKA_MODEL", "qwen35b")
DOUHUA_MODEL = os.environ.get("DOUHUA_MODEL", "qwen35b")
KG_MODEL = os.environ.get("KG_MODEL", XIANKA_MODEL)
KG_GATEWAY = os.environ.get("KG_GATEWAY", XIANKA_GATEWAY)

# ── 代理配置 ──
PROXY = os.environ.get("PROXY", "http://127.0.0.1:7897")

# ── 流水线参数（单端口 3080） ──
# ⚠️ 3080 只有 1 个推理进程端口，所有 GPU 调用严格串行
TARGET_PENDING = 300
MAX_RETRIES = 1
RETRY_COOLDOWN = 30
CURL_TIMEOUT = 120
FETCH_TIMEOUT = 30
MAX_TOKENS = 4096
TEMPERATURE = 0.8

# ── 质控参数 ──
MIN_CHARS_DEFAULT = 300
MAX_CHARS_DEFAULT = 800
KG_SEMANTIC_BATCH_SIZE = 5
KG_MAX_CARD_CONTENT = 1500

# ── 搜索引擎映射 ──
ENGINE_MAP = {
    "arxiv": "arxiv",
    "pubmed": "pubmed",
    "wikipedia": "wikipedia",
    "web": "web_fetch",
    "patent": "google_patents",
    "semantic": "semantic_scholar",
    "britannica": "web_fetch",
    "nih": "web_fetch",
}

# ── 信源 URL 模板 ──
SOURCE_URLS = {
    "pubmed_search": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmax={retmax}",
    "pubmed_fetch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&rettype=abstract&retmode=xml",
    "arxiv_search": "https://export.arxiv.org/api/query?search_query={query}&max_results={retmax}",
    "arxiv_pdf": "https://arxiv.org/pdf/{arxiv_id}.pdf",
    "wikipedia_search": "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json",
    "wikipedia_extract": "https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=extracts&exintro=1&explaintext=1&format=json",
    "theconversation": "https://theconversation.com/us/search?q={query}",
    "sciencedaily": "https://www.sciencedaily.com/search/?keyword={query}",
    "bing": "https://www.bing.com/search?q={query}",
}


def ensure_dirs():
    """确保所有数据目录存在（启动时调用一次）"""
    for d in [DATA_DIR, QUEUE_DIR, CACHE_DIR, KG_DIR, REF_DIR,
              OUTPUT_DIR, CARDS_DIR, DRAFTS_DIR, REPORTS_DIR,
              LOGS_DIR, METRICS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
