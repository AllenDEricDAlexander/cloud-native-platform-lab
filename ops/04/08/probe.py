"""真实请求采样与Prometheus指标；不以固定数值模拟灰度结果。"""
import os
import signal
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BUCKETS = (0.1, 0.25, 0.5, 1.0, 5.0, float("inf"))


class Measurements:
    def __init__(self):
        self.lock = threading.Lock()
        self.good = self.bad = 0
        self.total = 0.0
        self.buckets = [0] * len(BUCKETS)

    def record(self, status, duration):
        with self.lock:
            if status == 200:
                self.good += 1
            else:
                self.bad += 1
            self.total += duration
            for i, boundary in enumerate(BUCKETS):
                if duration <= boundary:
                    self.buckets[i] += 1

    def render(self):
        with self.lock:
            rows = [f'http_requests_total{{status="200"}} {self.good}', f'http_requests_total{{status="500"}} {self.bad}']
            for i, boundary in enumerate(BUCKETS):
                label = "+Inf" if boundary == float("inf") else str(boundary)
                rows.append(f'http_request_duration_seconds_bucket{{le="{label}"}} {self.buckets[i]}')
            rows.extend([f"http_request_duration_seconds_sum {self.total}", f"http_request_duration_seconds_count {self.good + self.bad}"])
            return "\n".join(rows) + "\n"


def sample(target, ca, stop, measurements):
    context = ssl.create_default_context(cafile=ca)
    # 不接受重定向到未批准目标；避免代理环境把灰度流量引向其他出口。
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    while not stop.is_set():
        started = time.monotonic()
        try:
            with opener.open(target, timeout=5) as response:
                status = response.status
                response.read(65536)
        except (urllib.error.URLError, TimeoutError, OSError):
            status = 500
        measurements.record(status, time.monotonic() - started)
        stop.wait(0.2)


if __name__ == "__main__":
    target = os.environ["TARGET_URL"]
    if not target.startswith("https://") or ".internal.egon.top/" not in target:
        raise ValueError("Internal HTTPS target required")
    measurements = Measurements()
    stop = threading.Event()
    worker = threading.Thread(target=sample, args=(target, "/ca/ca.crt", stop, measurements))
    worker.start()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            data = measurements.render().encode()
            self.send_response(200 if self.path == "/metrics" else 404)
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 9091), Handler)
    def shutdown(*_args):
        stop.set()
        threading.Thread(target=server.shutdown).start()
    signal.signal(signal.SIGTERM, shutdown)
    server.serve_forever()
    stop.set()
    worker.join(6)
    server.server_close()
