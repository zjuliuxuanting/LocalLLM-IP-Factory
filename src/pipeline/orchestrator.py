"""流水线协调器 (V3)

纯循环 daemon：取 ready → 7阶段 → 写 output → 更新 status → 下一张。
无自主决策，不重试，不重置，不改配置。
"""
import asyncio
import time
from typing import Optional

from src.io.store import get_queue_store
from src.pipeline.card_state import CardContext, CardState, GPU_STAGES
from src.utils.logging import get_logger, setup as setup_logging
from config.settings import LOGS_DIR

logger = get_logger("orchestrator")


class Orchestrator:
    """V3 流水线——只做纯循环，不越权"""

    def __init__(self):
        self._gpu_lock = asyncio.Lock()
        self._running = False

    async def run(self, max_cards: int = 0, daemon: bool = False) -> dict:
        setup_logging(log_dir=LOGS_DIR)
        self._running = True

        if daemon:
            logger.info("V3 daemon 启动（单端口串行，纯循环）")
            while self._running:
                ctx = self._next_ready()
                if ctx is None:
                    await asyncio.sleep(60)
                    continue
                await self._process_one(ctx)
                self._maybe_generate_dashboard()
        else:
            processed = 0
            while self._running:
                ctx = self._next_ready()
                if ctx is None:
                    break
                await self._process_one(ctx)
                processed += 1
                if 0 < max_cards <= processed:
                    break

        return self._get_queue_stats()

    async def _process_one(self, ctx: CardContext):
        cid = ctx.card_id
        t_start = time.monotonic()
        logger.info(f"▶ {cid} 开始")

        while ctx.state not in (CardState.COMPLETE, CardState.FAILED):
            next_state = ctx.advance_target()
            if next_state in GPU_STAGES:
                async with self._gpu_lock:
                    await self._execute_stage(ctx)
            else:
                await self._execute_stage(ctx)

            if ctx.state == CardState.FAILED:
                logger.warning(f"✗ {cid} 失败: {ctx.error}")
                break

        elapsed = time.monotonic() - t_start
        if ctx.state == CardState.COMPLETE:
            logger.info(f"✓ {cid} 完成 ({elapsed:.0f}s)")
            self._save_card_file(ctx)
        self._update_queue(ctx)

    async def _execute_stage(self, ctx: CardContext):
        from src.pipeline.card_state import TRANSITIONS
        next_state = TRANSITIONS.get(ctx.state)

        stage_map = {
            CardState.RESEARCHING:  ("src.pipeline.stages.research", "execute"),
            CardState.OUTLINING:    ("src.pipeline.stages.outline", "execute"),
            CardState.DRAFTING:     ("src.pipeline.stages.draft", "execute"),
            CardState.REVIEWING:    ("src.pipeline.stages.review", "execute"),
            CardState.REVISING:     ("src.pipeline.stages.revise", "execute"),
            CardState.POLISHING:    ("src.pipeline.stages.polish", "execute"),
            CardState.FACTCHECKING: ("src.pipeline.stages.factcheck", "execute"),
        }

        if next_state in stage_map:
            mod, func = stage_map[next_state]
            import importlib
            m = importlib.import_module(mod)
            await getattr(m, func)(ctx)

        elif next_state == CardState.COMPLETE:
            ctx.state = CardState.COMPLETE
            ctx.final = ctx.polished or ctx.revised or ctx.draft

        if ctx.state != CardState.FAILED and next_state is not None:
            ctx.advance()

    def _next_ready(self) -> Optional[CardContext]:
        store = get_queue_store()
        for c in store.read().get("cards", []):
            if c.get("status") == "ready":
                return CardContext(card=c)
        return None

    def _save_card_file(self, ctx: CardContext):
        from config.settings import CARDS_DIR
        CARDS_DIR.mkdir(parents=True, exist_ok=True)
        final_text = ctx.final or ctx.polished or ctx.revised or ctx.draft
        if final_text:
            (CARDS_DIR / f"{ctx.card_id}.md").write_text(final_text, encoding="utf-8")
            ctx.quality_score = 7.0

    def _update_queue(self, ctx: CardContext):
        store = get_queue_store()
        def updater(q):
            for c in q.get("cards", []):
                if c.get("id") == ctx.card_id:
                    c["status"] = "done" if ctx.state == CardState.COMPLETE else "failed"
                    if ctx.error:
                        c["_error"] = ctx.error[:200]
                    break
            return q
        store.update(updater)

    def _maybe_generate_dashboard(self):
        """每完成一张卡片更新 dashboard"""
        try:
            import subprocess
            subprocess.run(
                ["python3", "scripts/generate_dashboard.py"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    def _get_queue_stats(self) -> dict:
        cards = get_queue_store().read().get("cards", [])
        from collections import Counter
        return {"total": len(cards), **dict(Counter(c["status"] for c in cards))}

    def stop(self):
        self._running = False
