#!/usr/bin/env python3
"""手动 SDK 适配参考：只承载 W3C 关联，不代表已对七语言自动插桩。"""
import re
import secrets

PATTERN = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def extract(carrier):
    headers = {str(k).lower(): str(v) for k, v in carrier.items()}
    match = PATTERN.fullmatch(headers.get("traceparent", ""))
    if not match or int(match[1], 16) == 0 or int(match[2], 16) == 0:
        return None
    return {"trace_id": match[1], "span_id": match[2], "flags": match[3]}


def inject(context):
    value = f"00-{context['trace_id']}-{context['span_id']}-{context['flags']}"
    if extract({"traceparent": value}) is None:
        raise ValueError("invalid trace context")
    return {"traceparent": value}


def start(parent=None, asynchronous=False):
    current = {"trace_id": secrets.token_hex(16) if parent is None or asynchronous else parent["trace_id"], "span_id": secrets.token_hex(8), "flags": "01"}
    return {"context": current, "parent_span_id": parent["span_id"] if parent and not asynchronous else None, "links": [parent] if parent and asynchronous else []}
