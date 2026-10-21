#!/usr/bin/env python3
"""Dapr 状态/发布客户端。只在用户显式运行时连接本 Pod sidecar。"""
import argparse
import json
import pathlib
import urllib.request


def request(path, value=None, token_file=None):
    headers = {"Content-Type": "application/json"}
    if token_file:
        headers["dapr-api-token"] = pathlib.Path(token_file).read_text().strip()
    data = None if value is None else json.dumps(value, separators=(",", ":")).encode()
    req = urllib.request.Request("http://127.0.0.1:3500/v1.0/" + path, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--token-file")
    args = parser.parse_args()
    if not args.id.replace("-", "").isalnum() or len(args.id) > 64:
        parser.error("id must contain 1-64 letters, digits or hyphens")
    value = {"id": args.id, "value": "cnpl06"}
    request("state/lab-state", [{"key": args.id, "value": value}], args.token_file)
    recovered = json.loads(request("state/lab-state/" + args.id, token_file=args.token_file))
    if recovered != value:
        raise RuntimeError("state read-back mismatch")
    request("publish/lab-pubsub/orders", value, args.token_file)
    print(json.dumps({"id": args.id, "state_readback": True, "publish_accepted": True, "effect_verified": False}))


if __name__ == "__main__":
    main()
