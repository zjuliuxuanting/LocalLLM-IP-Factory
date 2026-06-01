"""HTTP 客户端封装

封装对本地 Gateway 的 HTTP 调用，提供连接复用、超时和重试。

⚠️ 并发保护：模型只支持单线程访问，HttpClient 内部使用 threading.Lock
   确保同一时刻只有一次 HTTP 请求发出。
"""
import json
import threading
import time
from dataclasses import dataclass
from typing import Optional
from urllib import request, error


@dataclass
class ModelResponse:
    content: str
    model: str
    tokens_used: int
    duration_s: float


class HttpClient:
    """本地 Gateway HTTP 客户端（单线程安全）"""

    def __init__(
        self,
        gateway_url: str,
        auth_token: str,
        default_timeout: int = 120,
        max_retries: int = 2,
        retry_delay: float = 5.0,
    ):
        self._url = gateway_url.rstrip("/") + "/v1/chat/completions"
        self._auth = auth_token
        self._timeout = default_timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._lock = threading.Lock()

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.8,
        tool_choice: Optional[str] = "none",
        permission_mode: Optional[str] = "bypassPermissions",
    ) -> Optional[ModelResponse]:
        """发送 prompt 到模型，返回清洗后的文本

        threading.Lock 确保同一时刻只有一个线程能发出请求，
        避免模型因并行请求而拒绝服务。
        """
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if permission_mode is not None:
            payload["permission_mode"] = permission_mode

        body = json.dumps(payload).encode("utf-8")
        last_err = None

        with self._lock:
            for attempt in range(self._max_retries + 1):
                if attempt > 0:
                    time.sleep(self._retry_delay)
                try:
                    req = request.Request(
                        self._url,
                        data=body,
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": self._auth,
                        },
                    )
                    t0 = time.monotonic()
                    with request.urlopen(req, timeout=self._timeout) as resp:
                        raw = json.loads(resp.read().decode("utf-8"))
                    elapsed = time.monotonic() - t0
                    content = raw["choices"][0]["message"]["content"].strip()
                    usage = raw.get("usage", {})
                    return ModelResponse(
                        content=content,
                        model=model,
                        tokens_used=usage.get("total_tokens", 0),
                        duration_s=elapsed,
                    )
                except (error.URLError, OSError, json.JSONDecodeError, KeyError) as e:
                    last_err = e

        return None

    def generate_structured(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> Optional[dict]:
        """生成并尝试提取 JSON

        先尝试直接解析，失败后尝试从返回文本中提取 JSON 块。
        """
        resp = self.generate(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            tool_choice="none",
        )
        if resp is None:
            return None
        try:
            return json.loads(resp.content)
        except json.JSONDecodeError:
            pass
        # 尝试提取 JSON
        import re
        m = re.search(r'\{[\s\S]*\}', resp.content)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None
