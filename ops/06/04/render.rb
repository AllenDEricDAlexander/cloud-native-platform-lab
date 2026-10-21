#!/usr/bin/env ruby
require_relative "../lib/config"
node = required("runtime","node")
workers = YAML.load_file(File.join(REPO,"ops/inventory/hosts.yaml")).fetch("kubernetes_nodes").select { |n| n["role"] == "worker" }.map { |n| n["fqdn"] }
abort "探针样例仅允许登记的 Worker" unless workers.include?(node)
app = deployment("runtime-demo")
app["spec"]["template"]["spec"]["nodeSelector"] = {"kubernetes.io/hostname"=>node}
emit(base+[app,service("runtime-demo")])
