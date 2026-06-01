"""原子 JSON 存储

所有持久化 JSON 文件通过此模块读写，保证事务安全。
写操作: temp → fsync → rename，避免中途崩溃损坏数据。
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional


class AtomicJsonStore:
    """事务性 JSON 持久化

    使用方式:
        store = AtomicJsonStore(Path("data/queue/cards.json"), default={"cards": []})
        queue = store.read()
        queue["cards"].append(new_card)
        store.write(queue)

        # 或者用 update 做原子读-改-写:
        store.update(lambda q: {**q, "cards": q["cards"] + [new_card]})
    """

    def __init__(self, path: Path, default: Any = None):
        self._path = Path(path)
        self._default = default if default is not None else {}
        self._lock = threading.Lock()

    def read(self) -> Any:
        with self._lock:
            return self._read_impl()

    def write(self, data: Any) -> None:
        with self._lock:
            self._write_impl(data)

    def update(self, updater: Callable[[Any], Any]) -> None:
        with self._lock:
            data = self._read_impl()
            data = updater(data)
            self._write_impl(data)

    def exists(self) -> bool:
        return self._path.exists()

    @property
    def path(self) -> Path:
        return self._path

    def _read_impl(self) -> Any:
        if not self._path.exists():
            return self._default
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default

    def _write_impl(self, data: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        tmp.rename(self._path)


# ── 预创建的全局 store 实例 ──

def _store(path: str, default: Any) -> AtomicJsonStore:
    from config.settings import PROJECT_ROOT
    return AtomicJsonStore(PROJECT_ROOT / path, default)


queue_store: Optional[AtomicJsonStore] = None
nodes_store: Optional[AtomicJsonStore] = None
edges_store: Optional[AtomicJsonStore] = None
semantic_state_store: Optional[AtomicJsonStore] = None


def get_queue_store() -> AtomicJsonStore:
    global queue_store
    if queue_store is None:
        queue_store = _store("data/queue/cards.json", {"cards": [], "meta": {"total_cards": 0}})
    return queue_store


def get_nodes_store() -> AtomicJsonStore:
    global nodes_store
    if nodes_store is None:
        nodes_store = _store("data/knowledge_graph/nodes.json", [])
    return nodes_store


def get_edges_store() -> AtomicJsonStore:
    global edges_store
    if edges_store is None:
        edges_store = _store("data/knowledge_graph/edges.json", [])
    return edges_store


def get_semantic_state_store() -> AtomicJsonStore:
    global semantic_state_store
    if semantic_state_store is None:
        semantic_state_store = _store(
            "data/knowledge_graph/semantic_state.json",
            {"processed_pairs": [], "total_semantic": 0},
        )
    return semantic_state_store


def load_seed_pool() -> dict:
    from config.settings import SEED_POOL_FILE
    store = AtomicJsonStore(SEED_POOL_FILE, {})
    return store.read()


def save_seed_pool(pool: dict) -> None:
    from config.settings import SEED_POOL_FILE
    store = AtomicJsonStore(SEED_POOL_FILE, {})
    store.write(pool)
