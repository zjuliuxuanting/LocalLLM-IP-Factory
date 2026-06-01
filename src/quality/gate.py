"""质量门禁

分阶段执行质量检查，决定卡片是否可以进入下一阶段。
"""
from pathlib import Path
from typing import Optional

from config.settings import CARDS_DIR, DRAFTS_DIR
from src.quality.metrics import evaluate, QualityResult
from src.quality.checkers import (
    check_empty, check_not_stub, check_code_wrapper,
    check_char_range, check_forbidden_words, check_repetition, check_content_depth,
)
from config.rubric import MAX_STAGE_RETRIES, STAGE_CHECKS


class StageGate:
    """分阶段质量门禁"""

    def check_outline(self, outline: dict) -> tuple[bool, str]:
        """S2 大纲检查：必须有至少一个 section 和 narrative_arc"""
        ol = outline.get("outline", outline)
        sections = ol.get("sections", [])
        if not sections:
            return False, "大纲无 section"
        for s in sections:
            if not s.get("heading"):
                return False, "section 缺少 heading"
            if not s.get("key_points"):
                return False, f"section '{s.get('heading', '')}' 缺少 key_points"
        if not ol.get("narrative_arc"):
            return False, "大纲缺少 narrative_arc"
        return True, "OK"

    def check_draft(self, text: str, card: dict) -> tuple[bool, str]:
        """S3 初稿快速检查（不调模型，纯规则）"""
        if not check_empty(text):
            return False, "内容为空"
        if not check_not_stub(text):
            return False, "包含占位/未完标记"

        wrapper = check_code_wrapper(text)
        if wrapper:
            return False, "; ".join(wrapper)

        # 字数：只拦下限，不再拦上限（模型不遵守字数约束）
        min_c = card.get("min_chars", 300)
        ok, count, msg = check_char_range(text, min_c, 99999)
        if not ok:
            return False, msg

        # 禁词检查
        forbidden = card.get("forbidden", [])
        hits = check_forbidden_words(text, forbidden)
        if hits:
            return False, f"命中禁词: {', '.join(hits)}"

        # 重复内容检查（连续段落/句子重复 >2 次）
        reps = check_repetition(text, threshold=3)
        if reps:
            return False, f"内容重复: {'; '.join(reps[:3])}"

        # 内容深度检查（信息密度过低或空泛套话过多）
        series = card.get("section", "")
        ok_depth, depth_msg = check_content_depth(text, series_key=series)
        if not ok_depth:
            return False, f"内容质量不足: {depth_msg}"

        return True, "OK"

    def check_review(self, review_result: dict) -> tuple[bool, str]:
        """S4 自审结果检查"""
        rv = review_result.get("review", review_result)
        if not rv:
            return False, "自审结果为空"
        verdict = rv.get("verdict", "fail")
        if verdict == "fail":
            return False, f"自审判定为 fail"
        return True, f"自审判定: {verdict}"

    def check_revision(self, original: str, revised: str, issues: list) -> tuple[bool, str]:
        """S5 修订验证：修订版是否解决了问题"""
        if not revised.strip():
            return False, "修订版为空"
        if revised.strip() == original.strip():
            return False, "修订版与原文完全相同"
        # 如果原文有 format 问题而修订版仍有
        orig_wrapper = check_code_wrapper(original)
        rev_wrapper = check_code_wrapper(revised)
        still_bad = set(rev_wrapper) - (set(rev_wrapper) - set(orig_wrapper))
        if still_bad:
            return False, f"修订版仍有格式问题: {', '.join(still_bad)}"
        return True, "OK"

    def check_final(
        self,
        text: str,
        card: dict,
        source_text: str = "",
        prev_card_text: str = "",
        series_texts: list[str] = None,
        factcheck_result: dict = None,
    ) -> QualityResult:
        """最终完整质检"""
        return evaluate(
            text=text,
            card=card,
            source_text=source_text,
            prev_card_text=prev_card_text,
            series_texts=series_texts,
            factcheck_result=factcheck_result,
            stage="final",
        )

    def should_retry_stage(self, retry_count: int) -> bool:
        return retry_count < MAX_STAGE_RETRIES

    def should_retry_card(self, retry_count: int) -> bool:
        from config.rubric import MAX_CARD_RETRIES
        return retry_count < MAX_CARD_RETRIES


# 单例
gate = StageGate()
