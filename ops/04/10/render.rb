#!/usr/bin/env ruby
require_relative "../lib/config"
mode=ARGV.fetch(0,"flux")
items=[]
case mode
when "flux"
  ns="flux-lab"
  items << {"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>ns,"labels"=>{"pod-security.kubernetes.io/enforce"=>"restricted"}}}
  items << {"apiVersion"=>"v1","kind"=>"ServiceAccount","metadata"=>{"name"=>"flux-reconciler","namespace"=>ns},"automountServiceAccountToken"=>false}
  items << {"apiVersion"=>"rbac.authorization.k8s.io/v1","kind"=>"Role","metadata"=>{"name"=>"flux-reconciler","namespace"=>ns},"rules"=>[{"apiGroups"=>[""],"resources"=>%w[configmaps services],"verbs"=>%w[get list watch create update patch delete]},{"apiGroups"=>["apps"],"resources"=>["deployments"],"verbs"=>%w[get list watch create update patch delete]}]}
  items << {"apiVersion"=>"rbac.authorization.k8s.io/v1","kind"=>"RoleBinding","metadata"=>{"name"=>"flux-reconciler","namespace"=>ns},"roleRef"=>{"apiGroup"=>"rbac.authorization.k8s.io","kind"=>"Role","name"=>"flux-reconciler"},"subjects"=>[{"kind"=>"ServiceAccount","name"=>"flux-reconciler","namespace"=>ns}]}
  path=required("comparison","flux_path")
  abort "Flux路径必须在独立experiments/flux目录" unless path.match?(%r{\A\./experiments/flux/[a-z0-9_-]+\z})
  items << {"apiVersion"=>"source.toolkit.fluxcd.io/v1","kind"=>"GitRepository","metadata"=>{"name"=>"comparison","namespace"=>ns},"spec"=>{"interval"=>"1m","url"=>required("repositories","gitops"),"ref"=>{"commit"=>required("comparison","git_revision")},"secretRef"=>{"name"=>required("comparison","flux_secret")}}}
  items << {"apiVersion"=>"kustomize.toolkit.fluxcd.io/v1","kind"=>"Kustomization","metadata"=>{"name"=>"comparison","namespace"=>ns},"spec"=>{"interval"=>"1m","path"=>path,"prune"=>false,"wait"=>true,"timeout"=>"3m","targetNamespace"=>ns,"serviceAccountName"=>"flux-reconciler","sourceRef"=>{"kind"=>"GitRepository","name"=>"comparison"}}}
when "tekton", "tekton-run"
  ns="tekton-lab"
  tools=digest_image(required("render_images","release_tools"))
  builder=digest_image(required("render_images","builder_java"))
  items << {"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>ns,"labels"=>{"pod-security.kubernetes.io/enforce"=>"restricted"}}}
  items << {"apiVersion"=>"v1","kind"=>"ServiceAccount","metadata"=>{"name"=>"comparison","namespace"=>ns}}
  steps=[
    {"name"=>"fetch","image"=>tools,"env"=>[{"name"=>"SOURCE_URL","value"=>required("repositories","source")},{"name"=>"SOURCE_REVISION","value"=>required("release","source_revision")}],"script"=>File.read(File.join(__dir__,"tekton-fetch.sh"))},
    {"name"=>"verify","image"=>builder,"workingDir"=>"$(workspaces.source.path)/repository","env"=>[{"name"=>"SOURCE_REVISION","value"=>required("release","source_revision")}],"script"=>"#!/usr/bin/env bash\nset -euo pipefail\nbash ops/04/05/build.sh java\n"},
    {"name"=>"package","image"=>tools,"workingDir"=>"$(workspaces.source.path)/repository","env"=>[{"name"=>"CI_FLAVOR","value"=>"tekton"},{"name"=>"LANGUAGE","value"=>"java"},{"name"=>"SOURCE_DIR","value"=>"ops/04/05/examples/java"},{"name"=>"SOURCE_REVISION","value"=>required("release","source_revision")}],"envFrom"=>[{"configMapRef"=>{"name"=>"comparison-build-config"}},{"secretRef"=>{"name"=>"comparison-build-auth"}}],"script"=>"#!/usr/bin/env bash\nset -euo pipefail\nbash ops/04/03/shared/package.sh\nbash ops/04/08/supply-chain.sh\n"}
  ]
  steps.each { |s| s["computeResources"]={"requests"=>{"cpu"=>"100m","memory"=>"256Mi"},"limits"=>{"cpu"=>"1","memory"=>"2Gi"}};s["securityContext"]={"runAsNonRoot"=>true,"runAsUser"=>1000,"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}} }
  steps.last.delete("envFrom")
  steps.last["envFrom"]=[{"configMapRef"=>{"name"=>"comparison-build-config"}}]
  steps.last["env"] << {"name"=>"BUILD_ATTEMPT_ID","value"=>required("comparison","pipeline_run")}
  steps.last["volumeMounts"]=[{"name"=>"build-auth","mountPath"=>"/build-auth","readOnly"=>true}]
  steps.last["script"]=File.read(File.join(__dir__,"tekton-package.sh"))
  steps.first["volumeMounts"]=[{"name"=>"source-auth","mountPath"=>"/source-auth","readOnly"=>true}]
  steps << {"name"=>"deploy-smoke","image"=>tools,"workingDir"=>"$(workspaces.source.path)/repository","env"=>[{"name"=>"RUN_ID","value"=>required("run_id")}],"script"=>File.read(File.join(__dir__,"tekton-smoke.sh")),"computeResources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"500m","memory"=>"512Mi"}},"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>1000,"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}}}
  items << {"apiVersion"=>"tekton.dev/v1","kind"=>"Task","metadata"=>{"name"=>"dual-ci-contract","namespace"=>ns},"spec"=>{"workspaces"=>[{"name"=>"source"}],"steps"=>steps}}
  items.last["spec"]["volumes"]=[{"name"=>"build-auth","secret"=>{"secretName"=>"comparison-build-auth","defaultMode"=>288}},{"name"=>"source-auth","secret"=>{"secretName"=>"comparison-source-auth","defaultMode"=>288}}]
  items << {"apiVersion"=>"tekton.dev/v1","kind"=>"Pipeline","metadata"=>{"name"=>"comparison","namespace"=>ns},"spec"=>{"workspaces"=>[{"name"=>"source"}],"tasks"=>[{"name"=>"build","taskRef"=>{"name"=>"dual-ci-contract"},"workspaces"=>[{"name"=>"source","workspace"=>"source"}]}]}}
  items << {"apiVersion"=>"rbac.authorization.k8s.io/v1","kind"=>"Role","metadata"=>{"name"=>"comparison-deploy","namespace"=>ns},"rules"=>[{"apiGroups"=>["apps"],"resources"=>["deployments","replicasets"],"verbs"=>%w[get list watch create update patch]},{"apiGroups"=>[""],"resources"=>["pods","services"],"verbs"=>%w[get list watch create update patch]}]}
  items << {"apiVersion"=>"rbac.authorization.k8s.io/v1","kind"=>"RoleBinding","metadata"=>{"name"=>"comparison-deploy","namespace"=>ns},"roleRef"=>{"apiGroup"=>"rbac.authorization.k8s.io","kind"=>"Role","name"=>"comparison-deploy"},"subjects"=>[{"kind"=>"ServiceAccount","name"=>"comparison","namespace"=>ns}]}
  if mode=="tekton-run"
    run=required("comparison","pipeline_run")
    abort "PipelineRun必须为本批唯一名称" unless run.match?(/\Acnpl04-#{Regexp.escape(required('run_id'))}-[a-z0-9-]+\z/)
    items=[{"apiVersion"=>"tekton.dev/v1","kind"=>"PipelineRun","metadata"=>{"name"=>run,"namespace"=>ns},"spec"=>{"pipelineRef"=>{"name"=>"comparison"},"timeouts"=>{"pipeline"=>"1h"},"taskRunTemplate"=>{"serviceAccountName"=>"comparison","podTemplate"=>{"nodeSelector"=>{"kubernetes.io/hostname"=>required("build","node")},"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"seccompProfile"=>{"type"=>"RuntimeDefault"}}}},"workspaces"=>[{"name"=>"source","volumeClaimTemplate"=>{"spec"=>{"accessModes"=>["ReadWriteOnce"],"storageClassName"=>required("build","storage_class"),"resources"=>{"requests"=>{"storage"=>"5Gi"}}}}}]}}]
  end
else abort "未知对照渲染模式"
end
puts JSON.pretty_generate(label(items))
