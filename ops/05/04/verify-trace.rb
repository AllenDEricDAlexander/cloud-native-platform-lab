#!/usr/bin/env ruby
require "json"
spans = []
services = []
ARGV.each do |path|
  data = JSON.parse(File.read(path))
  batches = data["resourceSpans"] || data["batches"] || []
  batches.each do |batch|
    attrs = batch.dig("resource","attributes") || []
    service = attrs.find { |a| a["key"]=="service.name" }.to_h.dig("value","stringValue")
    services << service if service
    (batch["scopeSpans"] || batch["instrumentationLibrarySpans"] || []).each do |scope|
      scope.fetch("spans",[]).each { |s| spans << s }
    end
  end
end
abort "跨语言服务不足" unless services.compact.uniq.length>=2
abort "缺少真实同步父子关系" unless spans.any? { |s| spans.any? { |p| p["spanId"]==s["parentSpanId"] && p["traceId"]==s["traceId"] } }
abort "缺少独立异步 consumer/link" unless spans.any? { |s| [5,"SPAN_KIND_CONSUMER"].include?(s["kind"]) && s.fetch("parentSpanId","").empty? && s.fetch("links",[]).any? { |l| spans.any? { |p| p["traceId"]==l["traceId"] && p["spanId"]==l["spanId"] } } }
serialized = JSON.generate(spans)
abort "Trace 含测试秘密或禁止属性" if serialized.include?("CNPL_TEST_SECRET_") || spans.any? { |s| s.fetch("attributes",[]).any? { |a| %w[password authorization cookie token db.statement http.request.body http.response.body].include?(a["key"].downcase) } }
puts "PASS 多语言同步父子与异步 link；未替代七语言分别验收"
