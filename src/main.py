"""LocalLLM-IP-Factory · 统一 CLI"""
import argparse, asyncio, sys

def cmd_pipeline(args):
    from src.pipeline.orchestrator import Orchestrator
    orch = Orchestrator()
    if args.action == "start":
        asyncio.run(orch.run(
            max_cards=getattr(args, "max_cards", 0),
            daemon=getattr(args, "daemon", False),
        ))
    elif args.action == "status":
        from src.io.store import get_queue_store
        from collections import Counter
        q = get_queue_store().read()
        cards = q.get("cards", [])
        s = Counter(c.get("status", "?") for c in cards)
        print(f"📊 队列: {len(cards)} 张 | {dict(s)}")

def cmd_status(args):
    from src.io.store import get_queue_store
    from collections import Counter
    q = get_queue_store().read()
    cards = q.get("cards", [])
    s = Counter(c.get("status", "?") for c in cards)
    print(f"📊 队列: {len(cards)} 张 | {dict(s)}")

def main():
    from config.settings import ensure_dirs
    ensure_dirs()
    parser = argparse.ArgumentParser(description="LocalLLM-IP-Factory")
    sub = parser.add_subparsers(dest="command")
    pp = sub.add_parser("pipeline")
    pp_sub = pp.add_subparsers(dest="action")
    pps = pp_sub.add_parser("start")
    pps.add_argument("--max-cards", type=int, default=0)
    pps.add_argument("--daemon", action="store_true")
    pp_sub.add_parser("status")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "pipeline": cmd_pipeline(args)
    elif args.command == "status": cmd_status(args)

if __name__ == "__main__": main()
