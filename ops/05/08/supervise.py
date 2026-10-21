#!/usr/bin/env python3
"""专用测试客户端的有界进程组；每轮安全查询都必须有有限值。"""
import json
import math
import os
import signal
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request


def safe_samples(data, rule):
    if data.get('status') != 'success' or not data.get('data', {}).get('result'):
        raise ValueError('safety query has no data')
    for row in data['data']['result']:
        value = float(row['value'][1])
        if not math.isfinite(value) or ('max' in rule and value > rule['max']) or ('min' in rule and value < rule['min']):
            raise ValueError('safety threshold crossed')


def collect(config, rules):
    target = urllib.parse.urlparse(config['prometheus_url'])
    if target.scheme != 'https' or not target.hostname or not target.hostname.endswith(('.internal.egon.top', '.svc', '.svc.cluster.local')) or target.username or target.password or target.query or target.fragment:
        raise ValueError('invalid internal safety API')
    context = ssl.create_default_context(cafile=config['ca_file'])
    for rule in rules:
        url = config['prometheus_url'].rstrip('/') + '/api/v1/query?' + urllib.parse.urlencode({'query': rule['expr']})
        headers = {'Authorization': 'Bearer ' + config['bearer_token']} if config.get('bearer_token') else {}
        request = urllib.request.Request(url, headers=headers)
        # 不跟随重定向，防止把认证发送至另一站点。
        class RejectRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                raise ValueError('redirect denied')
        opener = urllib.request.build_opener(RejectRedirect, urllib.request.HTTPSHandler(context=context))
        with opener.open(request, timeout=5) as response:
            safe_samples(json.load(response), rule)


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    with open(sys.argv[1]) as stream:
        config = json.load(stream)
    with open(sys.argv[2]) as stream:
        rules = json.load(stream)
    collect(config, rules)
    process = subprocess.Popen(sys.argv[3:], start_new_session=True)
    reason = None
    started = time.monotonic()
    try:
        while process.poll() is None:
            if time.monotonic() - started > int(os.environ['CNPL_DURATION']) + 60:
                raise ValueError('bounded load timeout')
            collect(config, rules)
            time.sleep(2)
    except (Exception, KeyboardInterrupt) as error:
        reason = type(error).__name__  # 不打印可能含认证/查询正文的异常。
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    if reason:
        print('STOP safety supervisor: ' + reason, file=sys.stderr)
        return 1
    return process.returncode


if __name__ == '__main__':
    try:
        result = main()
    except (Exception, KeyboardInterrupt) as error:
        print('STOP preflight: ' + type(error).__name__, file=sys.stderr)
        result = 1
    sys.exit(result)
