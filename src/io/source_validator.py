"""信源可用性验证器

在种子进入种子池之前，验证其搜索关键词能否从目标引擎返回有效结果。
这对事实类系列（B背景、R调研）至关重要——信源不可用的种子将产出低质量卡片。
"""
import json
import re
import subprocess
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from config.settings import PROXY, FETCH_TIMEOUT, SOURCE_URLS
from src.utils.logging import get_logger

logger = get_logger("source_validator")


@dataclass
class SourceValidationResult:
    kw: str
    engine: str
    available: bool
    result_count: int = 0
    sample_titles: list[str] = field(default_factory=list)
    error: str = ""


def validate_source(kw: str, engine: str = "web") -> SourceValidationResult:
    """测试一个搜索关键词能否从目标引擎返回有效结果

    Args:
        kw: 英文搜索关键词
        engine: 搜索引擎 (web/pubmed/arxiv/wikipedia)

    Returns:
        SourceValidationResult with availability and sample data
    """
    if not kw or len(kw.strip()) < 3:
        return SourceValidationResult(
            kw=kw, engine=engine, available=False,
            error="搜索词过短 (<3字符)"
        )

    query = kw.strip().replace(" ", "+")[:100]
    query_encoded = urllib.parse.quote(query)

    try:
        if engine == "pubmed":
            return _check_pubmed(query_encoded, kw)
        elif engine == "arxiv":
            return _check_arxiv(query_encoded, kw)
        elif engine in ("web", "web_fetch", "wikipedia"):
            return _check_wikipedia(query_encoded, kw)
        else:
            return _check_wikipedia(query_encoded, kw)
    except Exception as e:
        return SourceValidationResult(
            kw=kw, engine=engine, available=False,
            error=str(e)[:100]
        )


def _check_pubmed(query_encoded: str, kw: str) -> SourceValidationResult:
    url = SOURCE_URLS["pubmed_search"].format(query=query_encoded, retmax=3)
    result = _curl(url)
    if not result:
        return SourceValidationResult(kw=kw, engine="pubmed", available=False,
                                      error="PubMed 请求无响应")

    pmids = re.findall(r"<Id>(\d+)</Id>", result)
    titles = re.findall(r'<ArticleTitle>(.*?)</ArticleTitle>', result, re.DOTALL)
    titles = [t.strip()[:80] for t in titles]

    return SourceValidationResult(
        kw=kw, engine="pubmed",
        available=len(pmids) > 0,
        result_count=len(pmids),
        sample_titles=titles[:3],
        error="" if pmids else "PubMed 无匹配结果"
    )


def _check_arxiv(query_encoded: str, kw: str) -> SourceValidationResult:
    url = SOURCE_URLS["arxiv_search"].format(query=query_encoded, retmax=3)
    result = _curl(url)
    if not result or len(result) < 100:
        return SourceValidationResult(kw=kw, engine="arxiv", available=False,
                                      error="arXiv 请求无响应或内容过短")

    entries = re.findall(r'<entry>', result)
    titles = re.findall(r'<title>(.*?)</title>', result)
    titles = [t.strip()[:80] for t in titles if t.strip() and "arXiv" not in t]

    return SourceValidationResult(
        kw=kw, engine="arxiv",
        available=len(entries) > 0,
        result_count=len(entries),
        sample_titles=titles[:3],
        error="" if entries else "arXiv 无匹配结果"
    )


def _check_wikipedia(query_encoded: str, kw: str) -> SourceValidationResult:
    url = SOURCE_URLS["wikipedia_search"].format(query=query_encoded)
    result = _curl(url)
    if not result:
        return SourceValidationResult(kw=kw, engine="wikipedia", available=False,
                                      error="Wikipedia API 无响应")

    try:
        data = json.loads(result)
        search_results = data.get("query", {}).get("search", [])
        titles = [r.get("title", "")[:80] for r in search_results[:3]]

        return SourceValidationResult(
            kw=kw, engine="wikipedia",
            available=len(search_results) > 0,
            result_count=len(search_results),
            sample_titles=titles,
            error="" if search_results else "Wikipedia 无匹配结果"
        )
    except (json.JSONDecodeError, KeyError) as e:
        return SourceValidationResult(kw=kw, engine="wikipedia", available=False,
                                      error=f"Wikipedia 响应解析失败: {str(e)[:80]}")


def _curl(url: str, max_chars: int = 8000) -> str:
    try:
        cmd = ["curl", "-s", "--proxy", PROXY, "-m", str(FETCH_TIMEOUT), url]
        r = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=FETCH_TIMEOUT + 5)
        return r.stdout[:max_chars]
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════
# 系列信源要求分级
# ══════════════════════════════════════════════════════════════

def validate_seed_source(series: str, kw: str, engine: str) -> SourceValidationResult:
    """对种子执行信源验证

    根据系列的信源策略决定是否强制检查。
    """
    from config.series_definitions import get_source_policy
    policy = get_source_policy(series)
    result = validate_source(kw, engine)

    if policy == "required" and not result.available:
        result.error = f"[{series}系列强制信源验证失败] {result.error}"

    return result
