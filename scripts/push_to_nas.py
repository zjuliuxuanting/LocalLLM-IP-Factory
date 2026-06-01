#!/usr/bin/env python3
"""
推送 NAS：完整性校验 + rsync

检查所有 ready 卡片的信源缓存文件是否存在，缺的留在本地，全的推 NAS。

用法: python3 scripts/push_to_nas.py
"""
import sys, subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from src.io.store import AtomicJsonStore
from config.settings import QUEUE_FILE

NAS_PATH = "/<NAS_MOUNT>/<NAS_PROJECT_PATH>/"


def push():
    store = AtomicJsonStore(QUEUE_FILE, {"cards": []})
    queue = store.read()
    cards = queue.get("cards", [])

    ready = [c for c in cards if c.get("status") == "ready"]
    ok = []
    missing = []

    for c in ready:
        files = c.get("source_files", [])
        all_exist = all(Path(f).exists() for f in files) if files else False
        if all_exist:
            ok.append(c)
        else:
            missing.append(c)
            c["status"] = "pending_source"
            print(f"  ⚠️ {c['id']}: 缺信源文件，留在本地")

    if missing:
        store.write(queue)

    if not ok:
        print(f"\n❌ 无完整卡片可推 (ready={len(ok)}, 缺信源={len(missing)})")
        return

    print(f"\n📦 推送 {len(ok)} 张 ready 卡片 → NAS")
    print(f"   (缺信源 {len(missing)} 张留在本地)")

    # rsync
    src = str(SCRIPT_DIR) + "/"
    try:
        subprocess.run([
            "rsync", "-avz", "--delete",
            "--exclude", "__pycache__", "--exclude", "*.pyc",
            "--exclude", ".DS_Store",
            "--exclude", "output/cards/*", "--exclude", "output/drafts/*",
            src, NAS_PATH,
        ], check=True)
        print(f"✅ 推送完成")
    except subprocess.CalledProcessError as e:
        print(f"❌ rsync 失败: {e}")
        print(f"   NAS 挂载了吗？ mount -t smbfs //<USER>:<PASS>@<NAS>/work_space /tmp/nas_mount")


if __name__ == "__main__":
    push()
