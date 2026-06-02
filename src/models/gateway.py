"""本地模型 Gateway 封装

所有 LLM 调用统一走此模块。底层使用 HttpClient。
"""
from typing import Optional

from config.settings import (
    XIANKA_GATEWAY, DOUHUA_GATEWAY, GATEWAY_AUTH,
    XIANKA_MODEL, DOUHUA_MODEL, KG_MODEL, KG_GATEWAY,
    MAX_TOKENS, TEMPERATURE,
)
from src.models.client import HttpClient, ModelResponse


# ── 预建客户端 ──

_xianka = HttpClient(XIANKA_GATEWAY, GATEWAY_AUTH)
_douhua = HttpClient(DOUHUA_GATEWAY, GATEWAY_AUTH)
_kg = HttpClient(KG_GATEWAY, GATEWAY_AUTH, default_timeout=60)


def call_xianka(
    prompt: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
    structured: bool = False,
) -> Optional[str]:
    """调用主模型"""
    if structured:
        resp = _xianka.generate_structured(
            prompt, model=XIANKA_MODEL,
            max_tokens=max_tokens, temperature=temperature,
        )
        return resp  # dict or None
    resp = _xianka.generate(
        prompt, model=XIANKA_MODEL,
        max_tokens=max_tokens, temperature=temperature,
    )
    return resp.content if resp else None


def call_douhua(
    prompt: str,
    max_tokens: int = MAX_TOKENS,
    temperature: float = 0.8,
    structured: bool = False,
) -> Optional[str]:
    """调用辅助模型"""
    if structured:
        resp = _douhua.generate_structured(
            prompt, model=DOUHUA_MODEL,
            max_tokens=max_tokens, temperature=temperature,
        )
        return resp
    resp = _douhua.generate(
        prompt, model=DOUHUA_MODEL,
        max_tokens=max_tokens, temperature=temperature,
    )
    return resp.content if resp else None


def call_kg(prompt: str) -> Optional[str]:
    """调用知识图谱分类模型"""
    resp = _kg.generate(
        prompt, model=KG_MODEL,
        max_tokens=300, temperature=0.3,
    )
    return resp.content if resp else None


def call_kg_structured(prompt: str) -> Optional[dict]:
    """调用知识图谱模型并提取 JSON"""
    return _kg.generate_structured(
        prompt, model=KG_MODEL,
        max_tokens=300, temperature=0.3,
    )


# ── 响应清洗 ──

import re


def clean_response(text: str) -> str:
    """清洗模型返回的各种包装格式，提取纯正文"""
    if not text:
        return ""

    # 1. 提取 markdown code block 内的内容
    m = re.search(r'```(?:\w+)?\s*\n(.+?)\n```', text, re.DOTALL)
    if m:
        inner = m.group(1).strip()
        cm = re.search(r'content\s*=\s*"""(.+?)"""', inner, re.DOTALL)
        if cm:
            text = cm.group(1).strip()
        else:
            text = inner

    # 2. 切尾：移除尾部 Python 代码行
    lines = text.split('\n')
    tail_cut = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        s = lines[i].strip()
        if not s:
            continue
        if any(s.startswith(w) for w in [
            'with open(', 'print(', 'file.write(', 'f.write(',
            '__name__', 'if __name__', 'import ', 'from ',
            'open(', 'os.path', 'json.dump',
        ]):
            tail_cut = i
            continue
        break
    lines = lines[:tail_cut]

    # 3. 切头：移除前言/元描述
    cut = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if any(s.startswith(w) or w in s for w in [
            "The user", "Let me", "Now I", "I need", "Based on the sources",
            "让我先", "我先看", "现在让", "我需要先", "首先让",
            "---", "___", "卡片 ", "完成。", "以下是", "以下为",
            "content =", 'content=', '="""',
        ]):
            cut = i + 1
            continue
        if re.match(r'^[✅❌🆗⏱️]', s):
            cut = i + 1
            continue
        break
    text = '\n'.join(lines[cut:]).strip()

    # 4. 合并多余空行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text
