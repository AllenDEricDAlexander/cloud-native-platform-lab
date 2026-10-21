#!/usr/bin/env ruby
require_relative "../lib/config"
perf = INPUT.fetch("performance")
costs = %w[cpu_hourly_cost ram_gib_hourly_cost storage_gib_hourly_cost].map { |k| required("performance",k) }
abort "成本单价必须为正数，不能用缺失/零值表示免费" unless costs.all? { |v| v.is_a?(Numeric) && v.finite? && v>0 }
currency = required("performance","currency")
abort "币种格式无效" unless currency.match?(/\A[A-Z]{3}\z/)
verified(required("performance","assumptions_file"),required("performance","assumptions_sha256"))
repo,digest = image("opencost_image").split("@sha256:")
puts YAML.dump({"opencost"=>{"exporter"=>{"image"=>{"registry"=>"","repository"=>repo,"tag"=>"","digest"=>"sha256:#{digest}"},"resources"=>{"requests"=>{"cpu"=>"50m","memory"=>"128Mi"},"limits"=>{"cpu"=>"500m","memory"=>"512Mi"}}},"prometheus"=>{"internal"=>{"enabled"=>false},"external"=>{"enabled"=>true,"url"=>required("metrics","url")}},"customPricing"=>{"enabled"=>true,"costModel"=>{"description"=>"Lab model estimate; not a bill","provider"=>"custom","CPU"=>costs[0].to_s,"RAM"=>costs[1].to_s,"storage"=>costs[2].to_s,"currencyCode"=>currency}},"ui"=>{"enabled"=>false}}})
