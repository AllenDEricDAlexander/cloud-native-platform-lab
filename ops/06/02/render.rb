#!/usr/bin/env ruby
require_relative "../lib/config"
require "openssl"
mode = required("admission","mode")
abort "策略模式只能是 Audit/Enforce" unless %w[Audit Enforce].include?(mode)
version = required("admission","psa_version")
abort "PSA 版本必须明确到次版本" unless version.match?(/\Av1\.\d+\z/)
verified(required("admission","public_key_file"),required("admission","public_key_sha256"))
public_pem = File.read(required("admission","public_key_file"))
abort "签名文件必须为公钥，禁止把私钥写入策略" unless public_pem.start_with?("-----BEGIN PUBLIC KEY-----") && !public_pem.include?("PRIVATE KEY")
public_key = OpenSSL::PKey.read(public_pem)
abort "禁止私钥进入准入策略" if public_key.respond_to?(:private?) && public_key.private?
items = base
items.first["metadata"]["labels"].merge!({"pod-security.kubernetes.io/enforce"=>(mode == "Audit" ? "baseline" : "restricted"),"pod-security.kubernetes.io/enforce-version"=>version,"pod-security.kubernetes.io/audit-version"=>version,"pod-security.kubernetes.io/warn-version"=>version})
match = {"any"=>[{"resources"=>{"kinds"=>["Pod"],"namespaces"=>[namespace]}}]}
policy = object("kyverno.io/v1","ClusterPolicy","cnpl06-#{run}-baseline",{"validationFailureAction"=>mode,"background"=>true,"failurePolicy"=>"Fail","rules"=>[{"name"=>"bounded-trusted-pods","match"=>match,"validate"=>{"message"=>"cnpl06 requires owned labels, digest images and requests/limits","pattern"=>{"metadata"=>{"labels"=>{"cnpl.io/run"=>run}},"spec"=>{"containers"=>[{"name"=>"*","image"=>"harbor.k8s.internal.egon.top/*@sha256:*","resources"=>{"requests"=>{"cpu"=>"?*","memory"=>"?*"},"limits"=>{"cpu"=>"?*","memory"=>"?*"}}}]}}}},{"name"=>"signed-images","match"=>match,"verifyImages"=>[{"imageReferences"=>["harbor.k8s.internal.egon.top/*"],"mutateDigest"=>false,"verifyDigest"=>true,"required"=>true,"attestors"=>[{"count"=>1,"entries"=>[{"keys"=>{"publicKeys"=>File.read(required("admission","public_key_file"))}}]}]}]}]},nil)
items += [policy,deployment("restricted-demo"),service("restricted-demo")]
emit(items)
