#!/usr/bin/env ruby
require_relative "../lib/config"
if ARGV[0] != "fault"
  emit(base+[deployment("chaos-target"),service("chaos-target"),deployment("chaos-peer","http",1),service("chaos-peer")]); exit
end
seconds = required("chaos","duration_seconds")
abort "故障持续 10-60 秒" unless seconds.is_a?(Integer) && (10..60).include?(seconds)
kind = required("chaos","kind")
selector = {"namespaces"=>[namespace],"labelSelectors"=>labels.merge("app"=>(kind == "network" ? "chaos-peer" : "chaos-target"))}
spec = {"mode"=>"one","duration"=>"#{seconds}s","selector"=>selector}
resource = case kind
when "pod" then spec["action"]="pod-failure"; "PodChaos"
when "network"
  spec.merge!({"action"=>"delay","direction"=>"to","delay"=>{"latency"=>"100ms","jitter"=>"10ms","correlation"=>"0"},"target"=>{"mode"=>"all","selector"=>{"namespaces"=>[namespace],"labelSelectors"=>labels.merge("app"=>"chaos-target")}}}); "NetworkChaos"
when "stress" then spec["stressors"]={"cpu"=>{"workers"=>1,"load"=>25},"memory"=>{"workers"=>1,"size"=>"32Mi"}}; "StressChaos"
else abort "仅允许 pod/network/stress"
end
emit([object("chaos-mesh.org/v1alpha1",resource,"bounded-#{kind}",spec)])
