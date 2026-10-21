#!/usr/bin/env ruby
require_relative "../lib/config"
verified(required("gpu","evidence_file"),required("gpu","evidence_sha256"))
d = JSON.parse(File.read(required("gpu","evidence_file")))
abort "GPU 回执节点不符" unless d["node"] == required("gpu","node")
mode = required("gpu","driver_mode")
abort "必须选择 operator 或 preinstalled，不能重复安装驱动" unless %w[operator preinstalled].include?(mode) && d["driver_mode"] == mode
abort "GPU 硬件/许可/内核/CUDA/框架组合未核实" unless %w[hardware_visible host_compatible license_verified rocky_kernel_supported cuda_arch_supported framework_supported].all? { |key| d[key] == true } && d["model"].is_a?(String) && !d["model"].empty? && d["vram_mib"].is_a?(Integer) && d["vram_mib"]>0
puts JSON.generate({"node"=>d["node"],"model"=>d["model"],"driver_mode"=>mode,"runtime_accepted"=>false})
