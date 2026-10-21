#!/usr/bin/env ruby
require "json"
d = JSON.parse(File.read(ARGV.fetch(0)))
%w[gpu_hours gpu_hour_rate idle_gpu_hours power_kwh electricity_rate successful_requests output_tokens].each do |k|
  abort "缺少非负实测值/明确费率：#{k}" unless d[k].is_a?(Numeric) && d[k].finite? && d[k]>=0
end
abort "空闲 GPU 小时超出总时长" if d["idle_gpu_hours"]>d["gpu_hours"]
cost = d["gpu_hours"]*d["gpu_hour_rate"]+d["power_kwh"]*d["electricity_rate"]
puts JSON.pretty_generate({"estimated_cost"=>cost,"idle_allocation"=>d["idle_gpu_hours"]*d["gpu_hour_rate"],"per_request"=>(d["successful_requests"]>0 ? cost/d["successful_requests"] : nil),"per_million_output_tokens"=>(d["output_tokens"]>0 ? cost/d["output_tokens"]*1_000_000 : nil),"currency"=>d.fetch("currency"),"assumptions"=>d.fetch("assumptions"),"billing_exact"=>false})
