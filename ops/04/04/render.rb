#!/usr/bin/env ruby
require_relative "../lib/config"
templates = []
%w[verify release].each do |trust|
  %w[java rust c cpp csharp jsts python].each do |lang|
    labels = {"cnpl.io/trust"=>(trust=="release" ? "trusted" : "untrusted"),"cnpl.io/phase"=>"04","cnpl.io/run"=>required("run_id"),"cnpl.io/purpose"=>"ci-job"}
    security = {"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}}
    containers = [
      {"name"=>"jnlp","image"=>digest_image(required("render_images","jenkins_agent")),"securityContext"=>security,"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"250m","memory"=>"256Mi"}}},
      {"name"=>"builder","image"=>digest_image(required("render_images","builder_#{lang}")),"command"=>["sleep"],"args"=>["3600"],"securityContext"=>security,"resources"=>{"requests"=>{"cpu"=>"250m","memory"=>"512Mi","ephemeral-storage"=>"1Gi"},"limits"=>{"cpu"=>"1","memory"=>"2Gi","ephemeral-storage"=>"4Gi"}}}
    ]
    if trust=="release"
      containers << {"name"=>"tools","image"=>digest_image(required("render_images","release_tools")),"command"=>["sleep"],"args"=>["3600"],"securityContext"=>security,"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"256Mi"},"limits"=>{"cpu"=>"1","memory"=>"1Gi"}}}
    end
    pod = {"apiVersion"=>"v1","kind"=>"Pod","metadata"=>{"labels"=>labels},"spec"=>{"serviceAccountName"=>"application","automountServiceAccountToken"=>false,"nodeSelector"=>{"kubernetes.io/hostname"=>required("build","node")},"securityContext"=>{"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"runAsNonRoot"=>true,"seccompProfile"=>{"type"=>"RuntimeDefault"}},"containers"=>containers}}
    templates << {"name"=>"#{trust}-#{lang}","label"=>"cnpl-#{trust}-#{lang}","namespace"=>"ci-jenkins","instanceCap"=>1,"idleMinutes"=>0,"yaml"=>YAML.dump(pod)}
  end
end
puts YAML.dump({"jenkins"=>{"clouds"=>[{"kubernetes"=>{"name"=>"cnpl","namespace"=>"ci-jenkins","jenkinsUrl"=>"http://jenkins.ci-jenkins.svc:8080","webSocket"=>true,"containerCapStr"=>"2","templates"=>templates}}]}})
