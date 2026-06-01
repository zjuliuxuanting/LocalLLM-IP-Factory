#!/usr/bin/env python3
"""格式转换：将 data/source_cache/local/ 中的原始文档转换为 markdown/text

支持的格式：.pdf .doc .docx .html .htm .rtf .txt .md
转换方式：
  - PDF: pdfminer（跨平台）
  - docx: python-docx（跨平台）
  - 其他 Office 格式: macOS textutil
  - LLM 做最终清理和格式化
输出结果切分为 chunk 后注册到 source_registry，供阶段二优先使用。

用法:
  python3 scripts/translate_sources.py              # 全部转换
  python3 scripts/translate_sources.py --dry-run    # 预览不改
"""
import argparse, hashlib, json, re, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from src.models.gateway import call_xianka

LOCAL_DIR = SCRIPT_DIR / "data" / "source_cache" / "local"
SHARED_DIR = SCRIPT_DIR / "data" / "source_cache" / "shared"
REG_FILE = SCRIPT_DIR / "data" / "source_registry" / "index.json"

TEXT_EXTS = {".txt", ".md"}
HTML_EXTS = {".html", ".htm"}
OFFICE_EXTS = {".doc", ".docx", ".rtf", ".odt"}

CHUNK_SIZE = 2000
CHUNK_OVERLAP = 200

FORMAT_PROMPT = """你是一个文档处理助手。做两件事：

## 第一件：格式转换
将以下原始内容转换为干净的 Markdown 格式。
- 保留所有事实、数据、人名、地名
- 去除页眉页脚、页码、导航栏
- 用适当的 markdown 标题结构组织内容
- 不要添加原文没有的内容

## 第二件：提取搜索关键词
从内容中提取 3-8 个英文搜索关键词（kw），用于后续搜索引擎匹配。
- 每个关键词 1-3 个英文词
- 覆盖内容的核心主题
- 用逗号分隔

## 输出格式
先输出 Markdown 正文，然后在末尾单独一行输出：
---KW---
kw1, kw2, kw3

原始内容：
{content}"""


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """将长文本切分为有重叠的 chunk，在句子边界断开"""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        # 在 chunk 边界处找最近的句子结束符
        boundary = max(text.rfind("。", start, end), text.rfind("\n", start, end),
                       text.rfind(". ", start, end), text.rfind("!\n", start, end))
        if boundary > start + chunk_size // 2:
            end = boundary + 1
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def extract_text(filepath: Path) -> str:
    """尝试从各种格式提取纯文本（跨平台）"""
    ext = filepath.suffix.lower()

    if ext in TEXT_EXTS:
        return filepath.read_text(encoding="utf-8", errors="replace")

    if ext in HTML_EXTS:
        return filepath.read_text(encoding="utf-8", errors="replace")

    # Office 文档：docx 用 python-docx，其他用 textutil 兜底
    if ext in OFFICE_EXTS:
        if ext == ".docx":
            try:
                from docx import Document
                doc = Document(str(filepath))
                paras = [p.text for p in doc.paragraphs]
                text = "\n".join(paras)
                if len(text.strip()) > 100:
                    return text
            except ImportError:
                pass
        # 兜底：macOS textutil
        try:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as tmp:
                tmp_path = tmp.name
            subprocess.run(
                ["textutil", "-convert", "txt", "-output", tmp_path, str(filepath)],
                capture_output=True, timeout=30,
            )
            text = Path(tmp_path).read_text(encoding="utf-8", errors="replace")
            return text
        except Exception as e:
            return f"[提取失败: {e}]"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # PDF → pdfminer（跨平台）
    if ext == ".pdf":
        try:
            from pdfminer.high_level import extract_text as pdf_extract
            text = pdf_extract(str(filepath))
            if len(text.strip()) > 100:
                return text
        except ImportError:
            pass
        return f"[PDF 提取失败，请安装 pdfminer.six: {filepath.name}]"

    return f"[不支持的格式: {ext}]"


def format_with_llm(text: str, filename: str) -> tuple[str, list[str]]:
    """用 LLM清理/格式化文本为 markdown，同时提取关键词。GPU 不可达则死等。"""
    if len(text) < 100:
        return text, []
    prompt = FORMAT_PROMPT.format(content=text[:12000])

    # 一直重试，直到 GPU 返回有效结果
    import time as _time
    for attempt in range(1, 999):
        result = call_xianka(prompt, max_tokens=4096, temperature=0.2)
        if result and len(result) > 50:
            break
        delay = min(attempt * 5, 60)
        print(f"    ⚠️ GPU 不可达 (attempt {attempt})，{delay}s 后重试...")
        _time.sleep(delay)
    else:
        raise RuntimeError("GPU 永久不可达，无法完成翻译")

    # 从结果中分离正文和关键词
    kw_part = result.split("---KW---")[-1].strip() if "---KW---" in result else ""
    body = result.split("---KW---")[0].strip() if "---KW---" in result else result
    keywords = [k.strip().lower() for k in kw_part.split(",") if k.strip()] if kw_part else []

    if not keywords:
        raise RuntimeError(f"LLM 未返回关键词，内容可能无法解析。结果: {result[:200]}")

    return body, keywords


def save_and_register(
    filepath: Path,
    formatted: str,
    keywords: list[str] = None,
) -> list[tuple[str, str, int]]:
    """将格式化结果切 chunk 后保存，每条 chunk 独立注册到 source_registry
    
    Returns: [(sid, cache_path, chunk_index), ...]
    """
    chunks = chunk_text(formatted)
    safe_name = re.sub(r'[^\w\-_]+', '_', filepath.stem)[:40]
    base_sid = f"src_local_{hashlib.md5(filepath.name.encode()).hexdigest()[:10]}"

    reg = {}
    if REG_FILE.exists():
        reg = json.loads(REG_FILE.read_text())

    results = []
    for i, chunk in enumerate(chunks):
        fname = f"local_{safe_name}_ch{i:03d}.md"
        fpath = SHARED_DIR / fname
        fpath.write_text(chunk, encoding="utf-8")

        sid = f"{base_sid}_ch{i:03d}"
        if sid not in reg:
            reg[sid] = {
                "source_id": sid,
                "source_type": "local_translated",
                "title": f"{safe_name} (chunk {i+1}/{len(chunks)})",
                "url": f"local://{filepath.name}#chunk{i}",
                "original_file": str(filepath),
                "parent_source": base_sid,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "cache_path": str(fpath),
                "content_hash": hashlib.md5(chunk.encode()).hexdigest()[:12],
                "content_length": len(chunk),
                "keywords": keywords or [],
                "llm_relevance": 10,
                "used_by": [],
            }
        results.append((sid, str(fpath), i))

    REG_FILE.write_text(json.dumps(reg, indent=2, ensure_ascii=False))
    return results


def main():
    parser = argparse.ArgumentParser(description="将本地文档转换为 markdown 并注册")
    parser.add_argument("--dry-run", action="store_true", help="只预览，不改")
    args = parser.parse_args()

    if not LOCAL_DIR.exists():
        LOCAL_DIR.mkdir(parents=True)
        print(f"📁 已创建 {LOCAL_DIR}，请放入文档后重试")
        return

    files = sorted(LOCAL_DIR.iterdir())
    files = [f for f in files if f.is_file() and f.suffix.lower() not in (".json", ".yml", ".yaml")]

    if not files:
        print(f"📭 {LOCAL_DIR} 中没有文档")
        return

    print(f"📄 发现 {len(files)} 个文件:\n")
    for f in files:
        ext = f.suffix.lower()
        icon = "📝" if ext in TEXT_EXTS else "🌐" if ext in HTML_EXTS else "📎" if ext in OFFICE_EXTS else "📕" if ext == ".pdf" else "❓"
        print(f"  {icon} {f.name}")

    if args.dry_run:
        print(f"\n⏸️  dry-run 模式，未做任何修改")
        return

    SHARED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n🔄 开始转换...\n")
    for filepath in files:
        print(f"  📖 {filepath.name}...", end=" ", flush=True)
        try:
            raw_text = extract_text(filepath)
            if len(raw_text) < 100:
                print(f"⏭️  内容过短 ({len(raw_text)} chars)")
                continue

            formatted, keywords = format_with_llm(raw_text, filepath.name)
            kw_str = ", ".join(keywords[:8]) if keywords else "(LLM 未提取)"
            chunks_count = len(chunk_text(formatted))
            print(f"✅ LLM 格式化 ({len(formatted)} chars → {chunks_count} chunks) | kw: {kw_str}")

            results = save_and_register(filepath, formatted, keywords)
            for sid, cache_path, ci in results:
                print(f"     ch{ci:02d} → {cache_path} [{sid}]")

        except Exception as e:
            print(f"❌ 失败: {e}")

    print(f"\n✅ 转换完成")


if __name__ == "__main__":
    main()
