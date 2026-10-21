#!/usr/bin/env ruby
# 对真实业务回执校验去重/缺失；不读取消息系统、不生成成功回执。
require "json"
data = JSON.parse(File.read(ARGV.fetch(0)))
sent = data.fetch("published_ids")
acked = data.fetch("acknowledged_ids")
effects = data.fetch("effect_ids")
abort "输入 ID 必须为非空字符串数组" unless [sent,acked,effects].all? { |a| a.is_a?(Array) && a.all? { |x| x.is_a?(String) && !x.empty? } } && !sent.empty?
abort "发送 ID 重复" unless sent.uniq == sent
missing_ack = sent - acked
missing_effect = sent - effects
extra = (acked+effects).uniq - sent
duplicates = effects.size-effects.uniq.size
result = {"published"=>sent.size,"missing_ack"=>missing_ack,"missing_effect"=>missing_effect,"unexpected_ids"=>extra,"duplicate_effects"=>duplicates,"duplicate_deliveries"=>acked.size-acked.uniq.size,"runtime_accepted"=>false}
puts JSON.pretty_generate(result)
exit(missing_ack.empty? && missing_effect.empty? && extra.empty? && duplicates == 0 ? 0 : 1)
