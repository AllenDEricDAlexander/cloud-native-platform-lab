#!/usr/bin/env ruby
require "fileutils"
require_relative "../lib/config"
name=required("release","name")
abort "应用名称无效" unless name.match?(/\A[a-z][a-z0-9-]{2,30}\z/)
repo=required("repositories","gitops")
abort "GitOps仓库必须为内网GitLab HTTPS" unless repo.match?(%r{\Ahttps://gitlab\.svc\.internal\.egon\.top/[a-zA-Z0-9_./-]+\.git\z})
project={"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"AppProject","metadata"=>{"name"=>"cnpl04","namespace"=>"argocd"},"spec"=>{"sourceRepos"=>[repo],"destinations"=>%w[dev staging prod-like].map { |e| {"server"=>"https://kubernetes.default.svc","namespace"=>"apps-#{e}"} },"clusterResourceWhitelist"=>[],"namespaceResourceWhitelist"=>[{"group"=>"apps","kind"=>"Deployment"},{"group"=>"","kind"=>"Service"},{"group"=>"","kind"=>"ConfigMap"},{"group"=>"autoscaling","kind"=>"HorizontalPodAutoscaler"},{"group"=>"gateway.networking.k8s.io","kind"=>"HTTPRoute"},{"group"=>"argoproj.io","kind"=>"Rollout"},{"group"=>"argoproj.io","kind"=>"AnalysisTemplate"},{"group"=>"platform.egon.top","kind"=>"DevApplication"}]}}
appset={"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"ApplicationSet","metadata"=>{"name"=>name,"namespace"=>"argocd"},"spec"=>{"goTemplate"=>true,"goTemplateOptions"=>["missingkey=error"],"generators"=>[{"list"=>{"elements"=>%w[dev staging prod-like].map { |e| {"environment"=>e} }}}],"syncPolicy"=>{"applicationsSync"=>"create-update","preserveResourcesOnDeletion"=>true},"template"=>{"metadata"=>{"name"=>"#{name}-{{.environment}}"},"spec"=>{"project"=>"cnpl04","source"=>{"repoURL"=>repo,"targetRevision"=>required("gitops","revision"),"path"=>"environments/{{.environment}}/#{name}"},"destination"=>{"server"=>"https://kubernetes.default.svc","namespace"=>"apps-{{.environment}}"},"ignoreDifferences"=>[{"group"=>"apps","kind"=>"Deployment","name"=>name,"jsonPointers"=>["/spec/replicas"]}],"syncPolicy"=>{"automated"=>{"prune"=>false,"selfHeal"=>true},"syncOptions"=>["RespectIgnoreDifferences=true","CreateNamespace=false"]}}}}}
if ARGV[0]=="export"
  destination=ARGV.fetch(1)
  abort "目标必须为仓库外新目录" unless destination.start_with?("/") && !File.exist?(destination) && !File.expand_path(destination).start_with?(REPO+"/")
  image=digest_image(required("release","image"))
  base=File.join(destination,"base",name);FileUtils.mkdir_p(base)
  # Chart 是独立对照；主 GitOps 仅使用 Kustomize，避免双工具争写相同字段。
  deployment={"apiVersion"=>"apps/v1","kind"=>"Deployment","metadata"=>{"name"=>name},"spec"=>{"selector"=>{"matchLabels"=>{"app.kubernetes.io/name"=>name}},"template"=>{"metadata"=>{"labels"=>{"app.kubernetes.io/name"=>name}},"spec"=>{"serviceAccountName"=>"application","automountServiceAccountToken"=>false,"terminationGracePeriodSeconds"=>30,"securityContext"=>{"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"runAsNonRoot"=>true,"seccompProfile"=>{"type"=>"RuntimeDefault"}},"containers"=>[{"name"=>"app","image"=>"application","ports"=>[{"name"=>"http","containerPort"=>8080}],"env"=>[{"name"=>"PYTHONDONTWRITEBYTECODE","value"=>"1"}],"securityContext"=>{"allowPrivilegeEscalation"=>false,"readOnlyRootFilesystem"=>true,"capabilities"=>{"drop"=>["ALL"]}},"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"1","memory"=>"512Mi"}},"startupProbe"=>{"httpGet"=>{"path"=>"/health","port"=>"http"},"failureThreshold"=>30,"periodSeconds"=>5},"readinessProbe"=>{"httpGet"=>{"path"=>"/ready","port"=>"http"}},"livenessProbe"=>{"httpGet"=>{"path"=>"/health","port"=>"http"}},"volumeMounts"=>[{"name"=>"tmp","mountPath"=>"/tmp"}]}],"volumes"=>[{"name"=>"tmp","emptyDir"=>{"sizeLimit"=>"128Mi"}}]}}}}
  service={"apiVersion"=>"v1","kind"=>"Service","metadata"=>{"name"=>name},"spec"=>{"selector"=>{"app.kubernetes.io/name"=>name},"ports"=>[{"name"=>"http","port"=>8080,"targetPort"=>"http"}]}}
  hpa={"apiVersion"=>"autoscaling/v2","kind"=>"HorizontalPodAutoscaler","metadata"=>{"name"=>name},"spec"=>{"scaleTargetRef"=>{"apiVersion"=>"apps/v1","kind"=>"Deployment","name"=>name},"minReplicas"=>1,"maxReplicas"=>3,"metrics"=>[{"type"=>"Resource","resource"=>{"name"=>"cpu","target"=>{"type"=>"Utilization","averageUtilization"=>70}}}]}}
  File.write(File.join(base,"resources.yaml"),YAML.dump_stream(deployment,service,hpa))
  File.write(File.join(base,"kustomization.yaml"),YAML.dump({"apiVersion"=>"kustomize.config.k8s.io/v1beta1","kind"=>"Kustomization","resources"=>["resources.yaml"]}))
  %w[dev staging prod-like].each do |env|
    directory=File.join(destination,"environments",env,name);FileUtils.mkdir_p(directory)
    overlay={"apiVersion"=>"kustomize.config.k8s.io/v1beta1","kind"=>"Kustomization","namespace"=>"apps-#{env}","resources"=>["../../../base/#{name}"],"images"=>[{"name"=>"application","newName"=>image.split("@")[0],"digest"=>image.split("@")[1]}]}
    if INPUT.dig("gitops","hostnames",env)
      route={"apiVersion"=>"gateway.networking.k8s.io/v1","kind"=>"HTTPRoute","metadata"=>{"name"=>name},"spec"=>{"parentRefs"=>[{"name"=>required("gitops","gateway_name"),"namespace"=>required("gitops","gateway_namespace")}],"hostnames"=>[required("gitops","hostnames",env)],"rules"=>[{"backendRefs"=>[{"name"=>name,"port"=>8080}]}]}}
      File.write(File.join(directory,"route.yaml"),YAML.dump(route));overlay["resources"]<<"route.yaml"
    end
    File.write(File.join(directory,"kustomization.yaml"),YAML.dump(overlay))
  end
  puts "已生成三个环境；未推送/同步：#{destination}"
else puts JSON.pretty_generate(label([project,appset]))
end
