"""pytest 配置与共享 fixtures"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_dir():
    """临时目录，测试后自动清理"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_card():
    """一张示例卡片定义"""
    return {
        "id": "B1-1-1",
        "section": "B",
        "subsection": "1. 驯化的起点",
        "topic": "B1 沟通简史",
        "goal": "讲述狼驯化为狗的15000年历程",
        "style": "科普叙事，有温度",
        "status": "pending",
        "retries": 0,
        "search": [
            {"engine": "web", "query": "dog domestication history"}
        ],
        "min_chars": 300,
        "max_chars": 600,
        "forbidden": ["在本文中", "值得注意的是"],
        "node_type": "card",
        "related_nodes": [],
    }


@pytest.fixture
def sample_queue(sample_card):
    """一条示例队列"""
    return {
        "meta": {"total_cards": 3},
        "cards": [
            {**sample_card, "id": "B1-1-1", "subsection": "1. 驯化的起点"},
            {**sample_card, "id": "B1-1-2", "subsection": "2. 为什么是狗",
             "status": "pending"},
            {**sample_card, "id": "B1-1-3", "subsection": "3. 基因的证据",
             "status": "done"},
        ],
    }


@pytest.fixture
def mock_gateway():
    """Mock 模型 Gateway，返回预设内容"""
    with patch("src.models.client.HttpClient") as mock:
        client = MagicMock()
        client.generate.return_value = "这是一段生成的测试文本，字数足够通过质控检查。"
        client.generate_structured.return_value = {"outline": {"sections": []}}
        mock.return_value = client
        yield mock
