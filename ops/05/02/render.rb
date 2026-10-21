#!/usr/bin/env ruby
require_relative "../lib/config"
def chart_image(key, field = "sha")
  repo,digest = image(key).split("@sha256:")
  {"registry"=>"","repository"=>repo,"tag"=>"",field=>digest}
end
ns = required("namespaces","metrics")
case ARGV.fetch(0,"resources")
when "values"
  sc = required("metrics","storage_class")
  values = {
    "defaultRules"=>{"create"=>true},
    "prometheusOperator"=>{"image"=>chart_image("prometheus_operator"),"prometheusConfigReloader"=>{"image"=>chart_image("prometheus_config_reloader")},"admissionWebhooks"=>{"enabled"=>false}},
    "prometheus"=>{"prometheusSpec"=>{"image"=>chart_image("prometheus_image"),"replicas"=>1,"retention"=>"7d","retentionSize"=>"8GB","scrapeInterval"=>"30s","serviceMonitorSelectorNilUsesHelmValues"=>false,"podMonitorSelectorNilUsesHelmValues"=>false,"ruleSelectorNilUsesHelmValues"=>false,"serviceMonitorSelector"=>{"matchLabels"=>{"cnpl.io/phase"=>"05","cnpl.io/run"=>required("run_id")}},"podMonitorSelector"=>{"matchLabels"=>{"cnpl.io/phase"=>"05","cnpl.io/run"=>required("run_id")}},"ruleSelector"=>{"matchLabels"=>{"cnpl.io/phase"=>"05","cnpl.io/run"=>required("run_id")}},"resources"=>{"requests"=>{"cpu"=>"250m","memory"=>"512Mi"},"limits"=>{"cpu"=>"1","memory"=>"1Gi"}},"storageSpec"=>{"volumeClaimTemplate"=>{"spec"=>{"storageClassName"=>sc,"accessModes"=>["ReadWriteOnce"],"resources"=>{"requests"=>{"storage"=>"10Gi"}}}}}}},
    "alertmanager"=>{"alertmanagerSpec"=>{"image"=>chart_image("alertmanager"),"replicas"=>1,"configSecret"=>required("metrics","notification_secret"),"secrets"=>["notify"],"resources"=>{"requests"=>{"cpu"=>"50m","memory"=>"64Mi"},"limits"=>{"cpu"=>"250m","memory"=>"256Mi"}},"storage"=>{"volumeClaimTemplate"=>{"spec"=>{"storageClassName"=>sc,"accessModes"=>["ReadWriteOnce"],"resources"=>{"requests"=>{"storage"=>"1Gi"}}}}}}},
    "grafana"=>{"image"=>chart_image("grafana"),"admin"=>{"existingSecret"=>required("metrics","grafana_admin_secret"),"userKey"=>"admin-user","passwordKey"=>"admin-password"},"persistence"=>{"enabled"=>true,"storageClassName"=>sc,"size"=>"2Gi"},"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"128Mi"},"limits"=>{"cpu"=>"500m","memory"=>"512Mi"}},"sidecar"=>{"dashboards"=>{"enabled"=>true,"label"=>"grafana_dashboard"}},"testFramework"=>{"enabled"=>false},"initChownData"=>{"enabled"=>false}},
    "prometheus-node-exporter"=>{"image"=>chart_image("node_exporter","digest")},
    "kube-state-metrics"=>{"image"=>chart_image("kube_state_metrics")},
    "kubeEtcd"=>{"enabled"=>false},"kubeControllerManager"=>{"enabled"=>false},"kubeScheduler"=>{"enabled"=>false},"kubeProxy"=>{"enabled"=>false}
  }
  # Chart 原生采集对象也加相同选择标签，防止自监控被排除。
  values["commonLabels"] = {"cnpl.io/phase"=>"05","cnpl.io/run"=>required("run_id")}
  values["grafana"]["sidecar"]["image"] = chart_image("grafana_sidecar")
  puts YAML.dump(values)
when "resources"
  groups = YAML.load_file(File.join(__dir__,"rules.yaml")).fetch("groups")
  items = [object("PrometheusRule","cnpl05-platform",ns,{"spec"=>{"groups"=>groups}},"monitoring.coreos.com/v1")]
  dashboard = JSON.parse(File.read(File.join(__dir__,"dashboard.json")))
  cm = object("ConfigMap","cnpl05-platform-dashboard",ns,{"data"=>{"platform.json"=>JSON.generate(dashboard)}})
  cm["metadata"]["labels"] = {"grafana_dashboard"=>"1"}; items << cm
  items << object("HTTPRoute","grafana",ns,{"spec"=>{"parentRefs"=>[{"name"=>required("metrics","gateway_name"),"namespace"=>required("metrics","gateway_namespace")}],"hostnames"=>["grafana.k8s.internal.egon.top"],"rules"=>[{"backendRefs"=>[{"name"=>"cnpl05-grafana","port"=>80}]}]}},"gateway.networking.k8s.io/v1")
  puts JSON.pretty_generate(labeled(items))
else abort "未知渲染动作"
end
