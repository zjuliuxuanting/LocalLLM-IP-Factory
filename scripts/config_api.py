#!/usr/bin/env python3
"""配置 API 服务 — 读取/写入 config/.env

挂载在 dashboard 端口上，提供 /api/config 端点。

用法:
  python3 scripts/config_api.py [--port 8899] [--dir .]
"""
import argparse, json, os, re, urllib.parse, urllib.request, ssl
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SCRIPT_DIR / "config" / ".env"
DIRECTION_FILE = SCRIPT_DIR / "data" / "direction.txt"

# .env 中可编辑的字段
EDITABLE_FIELDS = {
    "GATEWAY_URL": {"label": "LLM 地址", "placeholder": "http://192.168.31.236:8080", "type": "url"},
    "XIANKA_MODEL": {"label": "主模型", "placeholder": "qwen35b", "type": "text"},
    "DOUHUA_MODEL": {"label": "事实核查模型", "placeholder": "qwen35b", "type": "text"},
    "GATEWAY_AUTH": {"label": "API 密钥（可选）", "placeholder": "sk-...", "type": "password"},
    "PROXY": {"label": "代理地址", "placeholder": "http://127.0.0.1:7897", "type": "url"},
}


def parse_env() -> dict:
    """读取 .env 文件，返回 {key: value}"""
    if not ENV_FILE.exists():
        return {}
    result = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def write_env(config: dict) -> bool:
    """将配置写回 .env，保留注释和排版"""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    updated_keys = set()
    output = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in config:
                output.append(f"{k}={config[k]}")
                updated_keys.add(k)
            else:
                output.append(line)
        else:
            output.append(line)
    for k, v in config.items():
        if k not in updated_keys:
            output.append(f"{k}={v}")
    ENV_FILE.write_text("\n".join(output) + "\n")
    return True


def _test_llm(url: str, key: str) -> dict:
    """服务端代理检测 LLM 连通性（避免浏览器 CORS 限制）"""
    if not url:
        return {"ok": False, "status": "no_url", "message": "未配置 LLM 地址"}
    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for ep in ["/v1/models", "/v1/chat/completions", "/models"]:
        try:
            req = urllib.request.Request(base + ep, method="GET")
            req.add_header("User-Agent", "Mozilla/5.0")
            if key:
                req.add_header("Authorization", "Bearer " + key if not key.startswith("Bearer ") else key)
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                if resp.status == 200:
                    return {"ok": True, "status": "online", "message": f"已连接 · {base.replace('https://', '').replace('http://', '').split('/')[0]}", "endpoint": ep}
                if resp.status in (401, 403):
                    return {"ok": False, "status": "auth_error", "message": "认证失败，请检查 API 密钥"}
        except Exception as e:
            err = str(e)[:100]
            continue
    return {"ok": False, "status": "offline", "message": f"无法连接 {base}", "detail": err}


class ConfigHandler(SimpleHTTPRequestHandler):
    """同时处理静态文件和 /api/config"""

    def do_GET(self):
        if self.path == "/api/config":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            env = parse_env()
            resp = {"fields": EDITABLE_FIELDS, "values": env}
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode())
            return
        if self.path == "/api/direction":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            text = DIRECTION_FILE.read_text().strip() if DIRECTION_FILE.exists() else ""
            self.wfile.write(json.dumps({"text": text}, ensure_ascii=False).encode())
            return
        # 静态文件菜单栏重定向到 config.html
        if self.path == "/config" or self.path == "/config/":
            self.path = "/output/config.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "无效 JSON"})
                return
            # 只允许更新可编辑字段
            allowed = set(EDITABLE_FIELDS.keys())
            config = {}
            for k in allowed:
                if k in data:
                    config[k] = str(data[k]).strip()
            if not config:
                self._json_response(400, {"error": "没有可更新字段"})
                return
            write_env(config)
            self._json_response(200, {"ok": True, "updated": list(config.keys())})
            return
        if self.path == "/api/direction":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try: data = json.loads(body)
            except json.JSONDecodeError: self._json_response(400, {"error": "无效 JSON"}); return
            DIRECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
            DIRECTION_FILE.write_text(data.get("text", "").strip())
            self._json_response(200, {"ok": True})
            return
        if self.path == "/api/test-llm":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "无效 JSON"})
                return
            self._json_response(200, _test_llm(data.get("url", ""), data.get("key", "")))
            return
        self._json_response(404, {"error": "Not Found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _json_response(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def main():
    parser = argparse.ArgumentParser(description="配置 API 服务")
    parser.add_argument("--port", type=int, default=8899, help="端口")
    parser.add_argument("--dir", default=str(SCRIPT_DIR), help="静态文件根目录")
    args = parser.parse_args()

    os.chdir(args.dir)
    server = HTTPServer(("0.0.0.0", args.port), ConfigHandler)
    print(f"📡 配置 API: http://localhost:{args.port}/api/config")
    print(f"📊 Dashboard: http://localhost:{args.port}/output/dashboard.html")
    print(f"⚙️  配置页:   http://localhost:{args.port}/output/config.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 停止")


if __name__ == "__main__":
    main()
