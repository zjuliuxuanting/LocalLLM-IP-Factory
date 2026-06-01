"""校验工具集"""
import re


def check_forbidden_words(text: str, forbidden: list) -> list:
    """检查文本是否包含禁止词，返回命中的禁止词列表"""
    if not forbidden:
        return []
    return [w for w in forbidden if w in text]


def check_char_count(text: str, min_chars: int, max_chars: int) -> tuple:
    """检查字数是否在范围内，返回 (ok, actual_count, message)"""
    count = len(text)
    if count < min_chars:
        return False, count, f"字数不足: {count} < {min_chars}"
    if count > max_chars:
        return False, count, f"字数超标: {count} > {max_chars}"
    return True, count, "OK"


def check_title_match(text: str, expected_title: str) -> bool:
    """检查小节标题是否出现在正文中"""
    if not expected_title:
        return True
    # 取标题前5个字匹配即可
    key = expected_title[:5]
    return key in text


def check_code_wrapper(text: str) -> list:
    """检查是否被代码块或其他格式包裹，返回问题列表"""
    issues = []
    stripped = text.strip()
    if stripped.startswith("```"):
        issues.append("以代码块开头")
    if stripped.startswith("content"):
        issues.append("以 content= 开头")
    if stripped.startswith("with open"):
        issues.append("以 with open 开头")
    if "完成" in text[:50]:
        issues.append("开头含'完成'")
    if "已写入" in text[:50]:
        issues.append("开头含'已写入'")
    return issues


def extract_sources(text: str) -> list:
    """从文本中提取信源引用"""
    sources = []
    # 匹配 [数字] 引用格式
    sources.extend(re.findall(r'\[\d+\]', text))
    # 匹配 URL
    sources.extend(re.findall(r'https?://[^\s)]+', text))
    # 匹配 PMC ID
    sources.extend(re.findall(r'PMC\d+', text))
    # 匹配 PMID
    sources.extend(re.findall(r'PMID[:\s]*(\d+)', text))
    return sources


def check_source_references(text: str, has_search_config: bool) -> bool:
    """检查是否有信源引用（软检查，仅当有搜索配置时才检查）"""
    if not has_search_config:
        return True
    refs = extract_sources(text)
    return len(refs) > 0
