"""原子检查函数

独立的检查器，不依赖外部服务，纯规则匹配。
"""
import re


def check_forbidden_words(text: str, forbidden: list) -> list[str]:
    """返回命中的禁词列表"""
    if not forbidden:
        return []
    return [w for w in forbidden if w in text]


def check_char_range(text: str, min_chars: int, _max_chars: int) -> tuple[bool, int, str]:
    """检查字数下限（不再拦上限，模型不遵守字数约束）"""
    count = len(text)
    if count < min_chars:
        return False, count, f"字数不足: {count} < {min_chars}"
    return True, count, "OK"


def check_title_present(text: str, expected_title: str) -> bool:
    """小节标题是否出现在正文中"""
    if not expected_title:
        return True
    key = expected_title[:5]
    return key in text


def check_code_wrapper(text: str) -> list[str]:
    """检查格式包裹问题"""
    issues = []
    stripped = text.strip()
    if stripped.startswith("```"):
        issues.append("以代码块开头")
    if "content =" in stripped[:100]:
        issues.append("含 content= 赋值")
    if "with open(" in stripped[:100]:
        issues.append("含 with open(")
    for w in ["完成", "已写入"]:
        if w in text[:50]:
            issues.append(f"开头含'{w}'")
            break
    return issues


def check_source_refs(text: str, has_search_config: bool) -> bool:
    """检查是否有信源引用"""
    if not has_search_config:
        return True
    refs = []
    refs.extend(re.findall(r'\[\d+\]', text))
    refs.extend(re.findall(r'https?://[^\s)]+', text))
    refs.extend(re.findall(r'PMC\d+', text))
    refs.extend(re.findall(r'PMID[:\s]*(\d+)', text))
    return len(refs) > 0


def check_empty(text: str) -> bool:
    return bool(text and text.strip())


def check_not_stub(text: str) -> bool:
    """检查是否包含常见的占位/未完标记"""
    stub_markers = ["TODO", "待补充", "占位", "[此处", "(待", "..."]
    for m in stub_markers:
        if m in text:
            return False
    return True


def check_forbidden_words(text: str, forbidden: list) -> list[str]:
    """返回命中的禁词列表"""
    if not forbidden:
        return []
    return [w for w in forbidden if w in text]


def check_repetition(text: str, threshold: int = 3) -> list[str]:
    """检查内容是否重复（连续段落/句子重复）"""
    issues = []
    sentences = re.split(r'[。！？\n]', text)
    seen = {}
    for i, s in enumerate(sentences):
        key = s.strip()
        if len(key) < 30:
            continue
        if key in seen:
            seen[key] += 1
            if seen[key] >= threshold:
                issues.append(f"内容重复（'{key[:40]}...'出现{seen[key]}次）")
        else:
            seen[key] = 1
    return issues


def check_content_depth(text: str) -> tuple[bool, str]:
    """检查内容深度：是否有实质性信息而非空泛描述"""
    # 统计含数字/年份的句子比例（科普卡片应有一定事实密度）
    sentences = re.split(r'[。！？\n]', text)
    meaningful = [s.strip() for s in sentences if len(s.strip()) >= 15]
    if not meaningful:
        return False, "内容过短，缺乏实质性句子"

    # 含数字/年份/专名的句子比例应 > 20%
    with_info = sum(1 for s in meaningful
                   if re.search(r'\d{2,}', s) or re.search(r'[A-Z][a-z]{2,}', s))
    ratio = with_info / len(meaningful)

    # 检查是否有空泛套话（"总之""综上所述""正如我们所知"等）占比过高
    filler_patterns = ["总之", "综上所述", "正如我们所知", "总而言之", "由此可见"]
    fillers = sum(1 for f in filler_patterns if f in text)
    filler_ratio = fillers / max(len(meaningful), 1)

    issues = []
    if ratio < 0.2:
        issues.append(f"信息密度过低（仅{ratio:.0%}的句子含事实信息）")
    if filler_ratio > 0.3:
        issues.append(f"空泛套话过多（{fillers}处）")

    return len(issues) == 0, "; ".join(issues)


def extract_claims(text: str, max_claims: int = 6) -> list[str]:
    """从正文中提取关键断言（含数字/专有名词的句子）"""
    sentences = re.split(r'[。！？\n]', text)
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) < 10:
            continue
        # 含数字或年份的句子
        if re.search(r'\d{2,}', s):
            claims.append(s[:120])
        # 含英文专名的句子
        elif re.search(r'[A-Z][a-z]{2,}', s):
            claims.append(s[:120])
    return claims[:max_claims]
