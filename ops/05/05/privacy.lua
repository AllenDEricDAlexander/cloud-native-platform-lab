-- 字段白名单与测试秘密遮盖；原始记录不复制到失败索引。
function sanitize(tag, timestamp, record)
    local labels = (record.kubernetes or {}).labels or {}
    local message = tostring(record.message or record.log or '')
    message = string.gsub(message, 'CNPL_TEST_SECRET_[%w_-]+', '[REDACTED]')
    for _, key in ipairs({'password', 'token', 'authorization', 'cookie'}) do
        local pattern = string.gsub(key, '%a', function(letter) return '[' .. string.lower(letter) .. string.upper(letter) .. ']' end)
        message = string.gsub(message, pattern .. '%s*[=:]%s*[^%s,;]+', '[REDACTED]')
    end
    local out = {
        message = message,
        service_name = tostring(record.service_name or labels['app.kubernetes.io/name'] or 'unknown'),
        environment = tostring(record.environment or labels.environment or 'unknown'),
        version = tostring(record.version or labels.version or 'unknown'),
        severity = tostring(record.severity or 'INFO'),
        namespace = tostring((record.kubernetes or {}).namespace_name or 'unknown')
    }
    if string.match(tostring(record.trace_id or ''), '^%x+$') and string.len(record.trace_id) == 32 then out.trace_id = record.trace_id end
    if string.match(tostring(record.span_id or ''), '^%x+$') and string.len(record.span_id) == 16 then out.span_id = record.span_id end
    return 1, timestamp, out
end
