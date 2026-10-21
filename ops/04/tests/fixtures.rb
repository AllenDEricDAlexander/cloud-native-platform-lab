#!/usr/bin/env ruby
require "json"
require "digest"
root=File.expand_path("..",__dir__)
output=ARGV.fetch(0)
d=JSON.parse(File.read(File.join(root,"inputs.json")))
d["run_id"]="review-"+File.basename(output).gsub(/[^a-z0-9]/,"")[-6,6]
d["build"].merge!({"node"=>"worker01.k8s.internal.egon.top","storage_class"=>"fixture-rbd","tls_secret"=>"fixture-tls"})
d["repositories"]={"source"=>"https://gitlab.svc.internal.egon.top/cnpl-apps/fixture.git","platform"=>"https://gitlab.svc.internal.egon.top/cnpl/platform.git","gitops"=>"https://gitlab.svc.internal.egon.top/cnpl/gitops.git","template_revision"=>"b"*40}
d["release"].merge!({"name"=>"fixture-app","language"=>"java","source_revision"=>"c"*40,"image"=>"harbor.k8s.internal.egon.top/fixture/app@sha256:"+"a"*64})
d["gitops"].merge!({"revision"=>"main","gateway_name"=>"fixture-gateway","gateway_namespace"=>"fixture-gateway","hostnames"=>{"dev"=>"fixture-dev.k8s.internal.egon.top","staging"=>"fixture-staging.k8s.internal.egon.top","prod-like"=>"fixture-prod.k8s.internal.egon.top"}})
d["render_images"]={}
%w[buildkit jenkins_agent release_tools prometheus_minimal probe_python crossplane_function postgresql_cnpg builder_java builder_rust builder_c builder_cpp builder_csharp builder_jsts builder_python].each { |key| d["render_images"][key]="harbor.k8s.internal.egon.top/fixture/#{key}@sha256:"+"a"*64 }
d["network"]={"api_service_ip"=>"10.96.0.1","gitlab_manager_selector"=>{"app"=>"gitlab-runner"},"jenkins_controller_selector"=>{"app"=>"jenkins"},"gateway_namespace"=>"fixture-gateway","gateway_selector"=>{"app"=>"gateway"}}
d["progressive"].merge!({"hostname"=>"fixture.k8s.internal.egon.top","url"=>"https://fixture.k8s.internal.egon.top","ca_secret"=>"fixture-ca","preview_metrics_job"=>"preview-fixture","preview_metrics_target"=>"preview-probe:9091"})
key=File.join(output,"fixture.pub");File.write(key,"OFFLINE FIXTURE ONLY; NOT A SIGNING KEY\n")
d["supply_chain"].merge!({"public_key_file"=>key,"public_key_sha256"=>Digest::SHA256.file(key).hexdigest})
d["portal"]["crossplane_service_account"]="crossplane"
d["comparison"].merge!({"flux_path"=>"./experiments/flux/fixture","git_revision"=>"d"*40,"flux_secret"=>"fixture-git","pipeline_run"=>"cnpl04-#{d['run_id']}-fixture"})
d["iac"].merge!({"provider_source"=>"registry.opentofu.org/hashicorp/vsphere","provider_version"=>"2.0.0","allowed_addresses"=>["vsphere_virtual_machine.test"]})
File.write(File.join(output,"inputs.json"),JSON.pretty_generate(d))
File.write(File.join(output,"materials.json"),JSON.generate({"schema_version"=>1,"components"=>{}}))
