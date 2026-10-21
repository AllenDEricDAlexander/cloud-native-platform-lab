#!/usr/bin/env ruby
require_relative "../lib/config"
# 本地 render 是管理作用域；provider 模板只有在现场锁定后才作为 bundle 应用。
plan = object("v1","ConfigMap","secondary-plan").merge("data"=>{"pod_cidr"=>required("capi","pod_cidr"),"service_cidr"=>required("capi","service_cidr"),"ownership"=>"CAPI owns only a new cnpl06-<run_id> secondary cluster; primary remains kubeadm"})
emit(base+[plan])
