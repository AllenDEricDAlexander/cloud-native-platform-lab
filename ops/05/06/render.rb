#!/usr/bin/env ruby
require_relative "../lib/config"
ns = required("namespaces","backends")
run = required("run_id")
uri = URI(required("backends","rgw_endpoint"))
abort "RGW 必须是经 CA 验证的 HTTPS" unless uri.scheme=="https" && !uri.userinfo && ["","/"].include?(uri.path)
buckets = %w[loki tempo pyroscope].map { |k| required("backends","#{k}_bucket") }
abort "三种信号必须使用不同 bucket" unless buckets.uniq.size==3
secrets = %w[loki tempo pyroscope].map { |k| required("backends","#{k}_s3_secret") }
abort "三后端必须使用各自受限凭据" unless secrets.uniq.size==3
server_tls = {"cert_file"=>"/tls/tls.crt","key_file"=>"/tls/tls.key","client_ca_file"=>"/tls/ca.crt","client_auth_type"=>"RequireAndVerifyClientCert"}
region = required("backends","region")
loki = {"auth_enabled"=>true,"server"=>{"http_listen_port"=>3100,"http_tls_config"=>server_tls,"grpc_tls_config"=>server_tls},"common"=>{"path_prefix"=>"/data","replication_factor"=>1,"ring"=>{"kvstore"=>{"store"=>"inmemory"}}},"schema_config"=>{"configs"=>[{"from"=>"2024-04-01","store"=>"tsdb","object_store"=>"s3","schema"=>"v13","index"=>{"prefix"=>"cnpl05_","period"=>"24h"}}]},"storage_config"=>{"aws"=>{"endpoint"=>uri.host+":"+uri.port.to_s,"region"=>region,"bucketnames"=>buckets[0],"access_key_id"=>"${S3_ACCESS_KEY}","secret_access_key"=>"${S3_SECRET_KEY}","s3forcepathstyle"=>true,"insecure"=>false}},"compactor"=>{"working_directory"=>"/data/compactor","retention_enabled"=>true,"delete_request_store"=>"s3"},"limits_config"=>{"retention_period"=>"72h","ingestion_rate_mb"=>1,"ingestion_burst_size_mb"=>2,"max_global_streams_per_user"=>1000,"allow_structured_metadata"=>true}}
tempo = {"multitenancy_enabled"=>true,"server"=>{"http_listen_port"=>3200,"http_tls_config"=>server_tls,"grpc_tls_config"=>server_tls},"distributor"=>{"receivers"=>{"otlp"=>{"protocols"=>{"grpc"=>{"endpoint"=>"0.0.0.0:4317","tls"=>{"cert_file"=>"/tls/tls.crt","key_file"=>"/tls/tls.key","client_ca_file"=>"/tls/ca.crt"}}}}}},"ingester"=>{"max_block_duration"=>"5m"},"compactor"=>{"compaction"=>{"block_retention"=>"24h"}},"storage"=>{"trace"=>{"backend"=>"s3","wal"=>{"path"=>"/data/wal"},"s3"=>{"bucket"=>buckets[1],"endpoint"=>uri.host+":"+uri.port.to_s,"region"=>region,"access_key"=>"${S3_ACCESS_KEY}","secret_key"=>"${S3_SECRET_KEY}","forcepathstyle"=>true,"insecure"=>false}}}}
pyroscope = {"multitenancy_enabled"=>true,"server"=>{"http_listen_port"=>4040,"http_tls_config"=>server_tls},"pyroscopedb"=>{"data_path"=>"/data"},"storage"=>{"backend"=>"s3","s3"=>{"bucket_name"=>buckets[2],"endpoint"=>uri.host+":"+uri.port.to_s,"region"=>region,"access_key_id"=>"${S3_ACCESS_KEY}","secret_access_key"=>"${S3_SECRET_KEY}","insecure"=>false}},"limits"=>{"compactor_blocks_retention_period"=>"24h"}}
loki["limits_config"]["otlp_config"] = {"resource_attributes"=>{"ignore_defaults"=>true,"attributes_config"=>[{"action"=>"index_label","attributes"=>["service.name","deployment.environment.name","service.version"]},{"action"=>"structured_metadata","attributes"=>["service.instance.id"]}]}}
configs = {"loki"=>loki,"tempo"=>tempo,"pyroscope"=>pyroscope}
if configs.key?(ARGV[0])
  puts YAML.dump(configs.fetch(ARGV[0])); exit
end
items = []
configs.each_with_index do |(name,config),index|
  port = {"loki"=>3100,"tempo"=>3200,"pyroscope"=>4040}.fetch(name)
  items << object("ConfigMap",name,ns,{"data"=>{"config.yaml"=>YAML.dump(config)}})
  items << object("PersistentVolumeClaim","#{name}-wal",ns,{"spec"=>{"storageClassName"=>required("backends","storage_class"),"accessModes"=>["ReadWriteOnce"],"resources"=>{"requests"=>{"storage"=>"2Gi"}}}})
  labels = {"app"=>name,"cnpl.io/phase"=>"05","cnpl.io/run"=>run}
  args = ["-config.file=/config/config.yaml","-config.expand-env=true"]
  items << object("Deployment",name,ns,{"spec"=>{"replicas"=>1,"strategy"=>{"type"=>"Recreate"},"selector"=>{"matchLabels"=>{"app"=>name}},"template"=>{"metadata"=>{"labels"=>labels},"spec"=>{"automountServiceAccountToken"=>false,"securityContext"=>{"runAsNonRoot"=>true,"runAsUser"=>10001,"fsGroup"=>10001},"containers"=>[{"name"=>name,"image"=>image(name),"args"=>args,"env"=>[{"name"=>"S3_ACCESS_KEY","valueFrom"=>{"secretKeyRef"=>{"name"=>secrets[index],"key"=>"access_key"}}},{"name"=>"S3_SECRET_KEY","valueFrom"=>{"secretKeyRef"=>{"name"=>secrets[index],"key"=>"secret_key"}}},{"name"=>"SSL_CERT_FILE","value"=>"/ca/ca.crt"}],"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"256Mi"},"limits"=>{"cpu"=>"1","memory"=>"768Mi"}},"securityContext"=>{"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}},"ports"=>[{"name"=>"https","containerPort"=>port}]+(name=="tempo" ? [{"name"=>"otlp","containerPort"=>4317}] : []),"volumeMounts"=>[{"name"=>"config","mountPath"=>"/config","readOnly"=>true},{"name"=>"data","mountPath"=>"/data"},{"name"=>"tls","mountPath"=>"/tls","readOnly"=>true},{"name"=>"ca","mountPath"=>"/ca","readOnly"=>true}]}],"volumes"=>[{"name"=>"config","configMap"=>{"name"=>name}},{"name"=>"data","persistentVolumeClaim"=>{"claimName"=>"#{name}-wal"}},{"name"=>"tls","secret"=>{"secretName"=>required("backends","tls_secret")}},{"name"=>"ca","secret"=>{"secretName"=>required("backends","ca_secret")}}]}}}},"apps/v1")
  items << object("Service",name,ns,{"spec"=>{"selector"=>{"app"=>name},"ports"=>[{"name"=>"https","port"=>port,"targetPort"=>port}]+(name=="tempo" ? [{"name"=>"otlp","port"=>4317,"targetPort"=>4317}] : [])}})
end
items << object("NetworkPolicy","authorized-telemetry",ns,{"spec"=>{"podSelector"=>{},"policyTypes"=>["Ingress"],"ingress"=>[{"from"=>%w[telemetry metrics].map { |key| {"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>required("namespaces",key)}}} }+[{"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>required("backends","gateway_namespace")}}}],"ports"=>[3100,3200,4040,4317].map { |p| {"protocol"=>"TCP","port"=>p} }}]}},"networking.k8s.io/v1")
datasources = [
  {"name"=>"Loki","type"=>"loki","uid"=>"cnpl05-loki","url"=>required("backends","loki_url"),"access"=>"proxy","jsonData"=>{"derivedFields"=>[{"name"=>"TraceID","matcherRegex"=>'"trace_id"\s*:\s*"([a-f0-9]{32})"',"datasourceUid"=>"cnpl05-tempo","url"=>'${__value.raw}'}]}},
  {"name"=>"Tempo","type"=>"tempo","uid"=>"cnpl05-tempo","url"=>required("backends","tempo_url"),"access"=>"proxy","jsonData"=>{"nodeGraph"=>{"enabled"=>true},"tracesToLogsV2"=>{"datasourceUid"=>"cnpl05-loki","spanStartTimeShift"=>"-1m","spanEndTimeShift"=>"1m","filterByTraceID"=>true},"tracesToMetrics"=>{"datasourceUid"=>"prometheus","tags"=>[{"key"=>"service.name","value"=>"service"}],"queries"=>[{"name"=>"Request rate","query"=>'sum(rate(cnpl_http_requests_total{$$__tags}[5m]))'}]}}},
  {"name"=>"Pyroscope","type"=>"grafana-pyroscope-datasource","uid"=>"cnpl05-pyroscope","url"=>required("backends","pyroscope_url"),"access"=>"proxy"}
]
cm = object("ConfigMap","cnpl05-datasources",required("namespaces","metrics"),{"data"=>{"backends.yaml"=>YAML.dump({"apiVersion"=>1,"datasources"=>datasources})}})
cm["metadata"]["labels"] = {"grafana_datasource"=>"1"}; items << cm
puts JSON.pretty_generate(labeled(items))
