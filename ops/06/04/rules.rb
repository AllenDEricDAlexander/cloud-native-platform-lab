#!/usr/bin/env ruby
require_relative "../lib/config"
if ARGV.fetch(0) == "falco"
  puts YAML.dump([{"rule"=>"CnplAuthorizedShell","desc"=>"Observe authorized shell execution in one experiment namespace","condition"=>"spawned_process and container and proc.name = sh and k8s.ns.name = #{namespace}","output"=>"Cnpl shell (pod=%k8s.pod.name namespace=%k8s.ns.name container=%container.id proc=%proc.name)","priority"=>"NOTICE","tags"=>["cnpl06",run]}])
else
  emit([object("cilium.io/v1alpha1","TracingPolicyNamespaced","authorized-exec",{"kprobes"=>[{"call"=>"sys_execve","syscall"=>true,"args"=>[{"index"=>0,"type"=>"string"}]}]})])
end
