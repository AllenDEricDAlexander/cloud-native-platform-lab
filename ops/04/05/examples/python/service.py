"""标准库 HTTP/计算样例；配置仅在运行期从环境读取。"""
import json
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def calculate(value: int) -> int:
    return value * value


class Handler(BaseHTTPRequestHandler):
    good = 0
    bad = 0
    lock = threading.Lock()

    def do_GET(self):
        status, kind = 200, "application/json"
        if self.path in ("/health", "/ready"):
            body = '{"status":"ok"}'
        elif self.path == "/version":
            body = json.dumps({"revision": Path("/app/revision").read_text().strip()})
        elif self.path == "/compute":
            failed = os.getenv("FAIL_REQUESTS") == "true"
            status = 500 if failed else 200
            with self.lock:
                if failed:
                    Handler.bad += 1
                else:
                    Handler.good += 1
            body = json.dumps({"value": calculate(7)})
        elif self.path == "/metrics":
            kind = "text/plain"
            with self.lock:
                body = f'http_requests_total{{status="200"}} {self.good}\nhttp_requests_total{{status="500"}} {self.bad}\n'
        else:
            status, body = 404, "{}"
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format, *args):
        print(json.dumps({"event": "request", "status": args[1] if len(args) > 1 else "unknown"}), flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    server.serve_forever()
    server.server_close()
