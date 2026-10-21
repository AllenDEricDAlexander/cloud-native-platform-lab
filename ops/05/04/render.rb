#!/usr/bin/env ruby
require_relative "../lib/config"
ns = required("namespaces","telemetry")
tls = {"ca_file"=>"/client/ca.crt","cert_file"=>"/client/tls.crt","key_file"=>"/client/tls.key"}
receiver = {"otlp"=>{"protocols"=>{"grpc"=>{"endpoint"=>"0.0.0.0:4317","tls"=>{"cert_file"=>"/server/tls.crt","key_file"=>"/server/tls.key","client_ca_file"=>"/server/ca.crt"}},"http"=>{"endpoint"=>"0.0.0.0:4318","tls"=>{"cert_file"=>"/server/tls.crt","key_file"=>"/server/tls.key","client_ca_file"=>"/server/ca.crt"}}}}}
processors = {"memory_limiter"=>{"check_interval"=>"1s","limit_mib"=>192,"spike_limit_mib"=>48},"batch"=>{"send_batch_size"=>256,"send_batch_max_size"=>512,"timeout"=>"2s"},"transform/privacy"=>{"error_mode"=>"propagate","trace_statements"=>[{"context"=>"resource","statements"=>['keep_keys(attributes, ["service.name", "service.namespace", "service.version", "service.instance.id", "deployment.environment.name"])']},{"context"=>"span","statements"=>['keep_keys(attributes, ["http.request.method", "http.route", "http.response.status_code", "error.type", "messaging.system", "messaging.operation.type", "messaging.destination.name"])']}],"log_statements"=>[{"context"=>"resource","statements"=>['keep_keys(attributes, ["service.name", "service.namespace", "service.version", "deployment.environment.name"])']},{"context"=>"log","statements"=>['keep_keys(attributes, ["severity", "error.type", "service_name", "environment", "version"])','replace_pattern(body, "CNPL_TEST_SECRET_[A-Za-z0-9_-]+", "[REDACTED]") where IsString(body)','replace_pattern(body, "(?i)(password|token|authorization|cookie)[=:][^ ,;]+", "[REDACTED]") where IsString(body)']}]}}
queue = {"sending_queue"=>{"enabled"=>true,"num_consumers"=>2,"queue_size"=>256},"retry_on_failure"=>{"enabled"=>true,"initial_interval"=>"1s","max_interval"=>"5s","max_elapsed_time"=>"30s"}}
percent = required("otel","sample_percent")
abort "sample_percent 必须为 0–100" unless percent.is_a?(Numeric) && percent.between?(0,100)
processors["tail_sampling"] = {"decision_wait"=>"10s","num_traces"=>2000,"expected_new_traces_per_sec"=>100,"policies"=>[{"name"=>"errors","type"=>"status_code","status_code"=>{"status_codes"=>["ERROR"]}},{"name"=>"baseline","type"=>"probabilistic","probabilistic"=>{"sampling_percentage"=>percent}}]}
processors["transform/privacy"]["metric_statements"] = [{"context"=>"resource","statements"=>['keep_keys(attributes, ["service.name", "service.namespace", "service.version", "deployment.environment.name"])']},{"context"=>"datapoint","statements"=>['keep_keys(attributes, ["service", "environment", "version", "team", "outcome", "http.request.method", "http.route", "http.response.status_code"])']}]
processors["transform/privacy"]["trace_statements"] << {"context"=>"spanevent","statements"=>['keep_keys(attributes, ["error.type"])','replace_pattern(name, "CNPL_TEST_SECRET_[A-Za-z0-9_-]+", "[REDACTED]")']}
agent = {"receivers"=>receiver,"processors"=>processors.reject { |k,_| k=="tail_sampling" },"exporters"=>{"otlp/gateway"=>queue.merge({"endpoint"=>"otel-gateway.#{ns}.svc:4317","tls"=>tls})},"service"=>{"pipelines"=>{}}}
%w[traces metrics logs].each { |signal| agent["service"]["pipelines"][signal] = {"receivers"=>["otlp"],"processors"=>["memory_limiter","transform/privacy","batch"],"exporters"=>["otlp/gateway"]} }
gateway = {"receivers"=>receiver,"processors"=>processors,"exporters"=>{"otlp/tempo"=>queue.merge({"endpoint"=>required("otel","tempo_endpoint"),"tls"=>tls}),"otlphttp/loki"=>queue.merge({"endpoint"=>INPUT.dig("otel","loki_endpoint"),"tls"=>tls}),"otlphttp/metrics"=>queue.merge({"endpoint"=>required("otel","metrics_endpoint"),"tls"=>tls})},"service"=>{"pipelines"=>{}}}
%w[traces metrics logs].zip(%w[otlp/tempo otlphttp/metrics otlphttp/loki]).each { |signal,exporter| gateway["service"]["pipelines"][signal]={"receivers"=>["otlp"],"processors"=>["memory_limiter","transform/privacy"]+(signal=="traces" ? ["tail_sampling"] : [])+["batch"],"exporters"=>[exporter]} }
[agent,gateway].each { |c| c["service"]["telemetry"]={"metrics"=>{"readers"=>[{"pull"=>{"exporter"=>{"prometheus"=>{"host"=>"0.0.0.0","port"=>8888}}}}]}} }
%w[otlp/tempo otlphttp/loki].each { |key| gateway["exporters"][key]["headers"]={"X-Scope-OrgID"=>required("run_id")} }
logs_backend = required("otel","logs_backend")
abort "otel.logs_backend 只能是 disabled/loki" unless %w[disabled loki].include?(logs_backend)
if logs_backend=="disabled"
  gateway["exporters"].delete("otlphttp/loki")
  [agent,gateway].each { |c| c["service"]["pipelines"].delete("logs") }
else
  required("otel","loki_endpoint")
  abort "ELK/Loki 不能默认同时采集相同 namespace；有限对照需用隔离命名空间" unless (required("otel","authorized_namespaces") & INPUT.dig("elk","selected_namespaces").to_a).empty?
end
if %w[agent-config gateway-config].include?(ARGV[0])
  puts YAML.dump(ARGV[0]=="agent-config" ? agent : gateway)
  exit
end
items = []
%w[agent gateway].each do |role|
  config = role=="agent" ? agent : gateway
  items << object("ConfigMap","otel-#{role}",ns,{"data"=>{"collector.yaml"=>YAML.dump(config)}})
  labels = {"app"=>"otel-#{role}","cnpl.io/phase"=>"05","cnpl.io/run"=>required("run_id")}
  spec = {"automountServiceAccountToken"=>false,"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>10001,"fsGroup"=>10001},"containers"=>[{"name"=>"collector","image"=>image("otel_collector"),"args"=>["--config=/config/collector.yaml"],"ports"=>[{"name"=>"grpc","containerPort"=>4317},{"name"=>"http","containerPort"=>4318}],"resources"=>{"requests"=>{"cpu"=>"50m","memory"=>"96Mi"},"limits"=>{"cpu"=>"500m","memory"=>"256Mi"}},"securityContext"=>{"allowPrivilegeEscalation"=>false,"readOnlyRootFilesystem"=>true,"capabilities"=>{"drop"=>["ALL"]}},"volumeMounts"=>[{"name"=>"config","mountPath"=>"/config","readOnly"=>true},{"name"=>"server","mountPath"=>"/server","readOnly"=>true},{"name"=>"client","mountPath"=>"/client","readOnly"=>true}]}],"volumes"=>[{"name"=>"config","configMap"=>{"name"=>"otel-#{role}"}},{"name"=>"server","secret"=>{"secretName"=>required("otel","tls_secret")}},{"name"=>"client","secret"=>{"secretName"=>required("otel","client_secret")}}]}
  kind = role=="agent" ? "DaemonSet" : "Deployment"
  controller = {"selector"=>{"matchLabels"=>{"app"=>"otel-#{role}"}},"template"=>{"metadata"=>{"labels"=>labels},"spec"=>spec}}
  controller["replicas"] = 1 if kind=="Deployment" # 尾采样同一 Trace 必须进同一实例。
  items << object(kind,"otel-#{role}",ns,{"spec"=>controller},"apps/v1")
  service_spec = {"selector"=>{"app"=>"otel-#{role}"},"ports"=>[{"name"=>"grpc","port"=>4317,"targetPort"=>"grpc"},{"name"=>"http","port"=>4318,"targetPort"=>"http"}]}
  service_spec["internalTrafficPolicy"] = "Local" if role=="agent"
  items << object("Service","otel-#{role}",ns,{"spec"=>service_spec})
  items << object("Service","otel-#{role}-metrics",ns,{"metadata"=>{"name"=>"otel-#{role}-metrics","namespace"=>ns,"labels"=>{"app"=>"otel-#{role}-metrics"}},"spec"=>{"selector"=>{"app"=>"otel-#{role}"},"ports"=>[{"name"=>"metrics","port"=>8888,"targetPort"=>8888}]}})
  items << object("ServiceMonitor","otel-#{role}",required("namespaces","metrics"),{"spec"=>{"namespaceSelector"=>{"matchNames"=>[ns]},"selector"=>{"matchLabels"=>{"app"=>"otel-#{role}-metrics"}},"endpoints"=>[{"port"=>"metrics","interval"=>"30s"}],"sampleLimit"=>10000}},"monitoring.coreos.com/v1")
end
authorized = required("otel","authorized_namespaces")
items << object("NetworkPolicy","otel-ingress",ns,{"spec"=>{"podSelector"=>{},"policyTypes"=>["Ingress"],"ingress"=>[{"from"=>authorized.map { |n| {"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>n}}} }+[{"podSelector"=>{"matchLabels"=>{"app"=>"otel-agent"}}}],"ports"=>[{"protocol"=>"TCP","port"=>4317},{"protocol"=>"TCP","port"=>4318}]}]}},"networking.k8s.io/v1")
items << object("NetworkPolicy","otel-self-metrics",ns,{"spec"=>{"podSelector"=>{},"policyTypes"=>["Ingress"],"ingress"=>[{"from"=>[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>required("namespaces","metrics")}}}],"ports"=>[{"protocol"=>"TCP","port"=>8888}]}]}},"networking.k8s.io/v1")
puts JSON.pretty_generate(labeled(items))
