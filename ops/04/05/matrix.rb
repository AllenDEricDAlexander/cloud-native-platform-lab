#!/usr/bin/env ruby
require_relative "../lib/config"
expected=%w[java rust c cpp csharp jsts python].product(%w[gitlab jenkins])
rows=ARGV.map { |p| JSON.parse(File.read(p)) }
abort "需要14份独立观察回执" unless rows.size==14 && rows.map { |r| [r["language"],r["ci"]] }.sort==expected.sort
revisions=rows.map { |r| r["source_revision"] }.uniq
abort "14格需同一固定源码 SHA" unless revisions.size==1 && revisions[0].match?(/\A[a-f0-9]{40}\z/)
rows.each do |r|
  %w[pipeline_url builder_image image native_artifact_sha256 sbom_sha256 provenance_sha256 deployment_observed_at gitops_revision].each { |key| abort "缺少 #{key}" unless r[key].is_a?(String) && !r[key].empty? }
  digest_image(r["image"]); digest_image(r["builder_image"])
  abort "回执未完成测试/签名/部署检查" unless r.dig("tests","unit_tests")=="passed" && r["signature_verified"]==true && r["smoke_result"]=="passed"
end
puts JSON.pretty_generate({"matrix"=>rows,"receipt_set_complete"=>true,"phase_complete"=>false,"boundary"=>"仍需逐格核对原始 CI/Argo/请求/负向证据及其余55步验收"})
