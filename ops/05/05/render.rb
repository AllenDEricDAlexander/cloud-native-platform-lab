#!/usr/bin/env ruby
require_relative "../lib/config"
run = required("run_id")
ns = required("namespaces","logging")
prefix = "cnpl05-#{run}"
mode = ARGV.fetch(0,"resources")
case mode
when "ilm"
  puts JSON.pretty_generate({"policy"=>{"_meta"=>{"cnpl_run"=>run},"phases"=>{"hot"=>{"actions"=>{}},"delete"=>{"min_age"=>"3d","actions"=>{"delete"=>{}}}}}})
when "index-template"
  props = %w[service_name environment version severity namespace trace_id span_id error_type tags].to_h { |k| [k,{"type"=>"keyword","ignore_above"=>256}] }
  props.merge!({"@timestamp"=>{"type"=>"date"},"message"=>{"type"=>"text"}})
  puts JSON.pretty_generate({"index_patterns"=>["#{prefix}-*"],"priority"=>200,"_meta"=>{"cnpl_run"=>run},"template"=>{"settings"=>{"index.lifecycle.name"=>prefix,"number_of_shards"=>1,"number_of_replicas"=>1,"index.mapping.total_fields.limit"=>32},"mappings"=>{"dynamic"=>"strict","properties"=>props}}})
when "query"
  id = required("otel","trace_id"); abort "trace_id 无效" unless id.match?(/\A[a-f0-9]{32}\z/)
  puts JSON.pretty_generate({"size"=>100,"query"=>{"term"=>{"trace_id"=>id}},"sort"=>[{"@timestamp"=>"asc"}]})
when "saved-objects"
  puts JSON.generate({"type"=>"index-pattern","id"=>prefix,"attributes"=>{"title"=>"#{prefix}-*","timeFieldName"=>"@timestamp"},"references"=>[]})
  puts JSON.generate({"type"=>"search","id"=>"#{prefix}-errors","attributes"=>{"title"=>"#{prefix} errors / database / release / access denied","columns"=>["service_name","environment","version","trace_id","error_type","message"],"sort"=>[["@timestamp","desc"]],"kibanaSavedObjectMeta"=>{"searchSourceJSON"=>JSON.generate({"query"=>{"language"=>"kuery","query"=>'severity: "ERROR" or error_type: *'},"filter"=>[],"indexRefName"=>"kibanaSavedObjectMeta.searchSourceJSON.index"})}},"references"=>[{"type"=>"index-pattern","id"=>prefix,"name"=>"kibanaSavedObjectMeta.searchSourceJSON.index"}]})
when "resources"
  tls = required("elk","tls_secret"); creds = required("elk","credentials_secret")
  route = required("elk","route"); abort "日志 route 必须是 logstash/direct" unless %w[logstash direct].include?(route)
  selected = required("elk","selected_namespaces")
  abort "namespace 格式无效" unless selected.all? { |n| n.match?(/\A[a-z0-9-]+\z/) }
  config = File.read(File.join(__dir__,"fluent-bit.conf"))
  # 在元数据合并后按明确的 namespace 筛选；不默认为全量双写。
  config += "\n[FILTER]\n    Name grep\n    Match kube.*\n    Regex namespace ^(#{selected.join('|')})$\n"
  if route=="logstash"
    config += "\n[OUTPUT]\n    Name http\n    Match kube.*\n    Host logstash.#{ns}.svc\n    Port 8080\n    URI /\n    Format json\n    tls On\n    tls.verify On\n    tls.ca_file /tls/ca.crt\n    tls.crt_file /tls/tls.crt\n    tls.key_file /tls/tls.key\n    Retry_Limit 5\n    storage.total_limit_size 128M\n"
  else
    uri = URI(required("elk","url")); abort "ES URL 必须 HTTPS 无路径" unless uri.scheme=="https" && ["","/"].include?(uri.path) && !uri.userinfo
    config += "\n[OUTPUT]\n    Name es\n    Match kube.*\n    Host #{uri.host}\n    Port #{uri.port}\n    HTTP_User ${ES_USER}\n    HTTP_Passwd ${ES_PASSWORD}\n    Logstash_Format On\n    Logstash_Prefix #{prefix}-direct\n    Logstash_DateFormat %Y.%m.%d\n    Suppress_Type_Name On\n    Generate_ID On\n    tls On\n    tls.verify On\n    tls.ca_file /es-ca/ca.crt\n    Retry_Limit 5\n    storage.total_limit_size 128M\n"
  end
  items = [object("ConfigMap","fluent-bit",ns,{"data"=>{"fluent-bit.conf"=>config,"privacy.lua"=>File.read(File.join(__dir__,"privacy.lua"))}}),object("ServiceAccount","fluent-bit",ns,{"automountServiceAccountToken"=>true})]
  items << object("ClusterRole","cnpl05-#{run}-logs",nil,{"rules"=>[{"apiGroups"=>[""],"resources"=>["pods","namespaces"],"verbs"=>["get","list","watch"]}]},"rbac.authorization.k8s.io/v1")
  items << object("ClusterRoleBinding","cnpl05-#{run}-logs",nil,{"roleRef"=>{"apiGroup"=>"rbac.authorization.k8s.io","kind"=>"ClusterRole","name"=>"cnpl05-#{run}-logs"},"subjects"=>[{"kind"=>"ServiceAccount","name"=>"fluent-bit","namespace"=>ns}]},"rbac.authorization.k8s.io/v1")
  labels = {"app"=>"fluent-bit","cnpl.io/phase"=>"05","cnpl.io/run"=>run}
  items << object("DaemonSet","fluent-bit",ns,{"spec"=>{"selector"=>{"matchLabels"=>{"app"=>"fluent-bit"}},"template"=>{"metadata"=>{"labels"=>labels},"spec"=>{"serviceAccountName"=>"fluent-bit","containers"=>[{"name"=>"fluent-bit","image"=>image("fluent_bit"),"securityContext"=>{"runAsUser"=>0,"allowPrivilegeEscalation"=>false,"readOnlyRootFilesystem"=>true,"capabilities"=>{"drop"=>["ALL"]}},"resources"=>{"requests"=>{"cpu"=>"25m","memory"=>"64Mi"},"limits"=>{"cpu"=>"200m","memory"=>"128Mi"}},"env"=>%w[ES_USER ES_PASSWORD].map { |k| {"name"=>k,"valueFrom"=>{"secretKeyRef"=>{"name"=>creds,"key"=>k}}} },"volumeMounts"=>[{"name"=>"logs","mountPath"=>"/var/log","readOnly"=>true},{"name"=>"buffers","mountPath"=>"/buffers"},{"name"=>"config","mountPath"=>"/fluent-bit/etc/fluent-bit.conf","subPath"=>"fluent-bit.conf","readOnly"=>true},{"name"=>"config","mountPath"=>"/fluent-bit/etc/privacy.lua","subPath"=>"privacy.lua","readOnly"=>true},{"name"=>"tls","mountPath"=>"/tls","readOnly"=>true},{"name"=>"es-ca","mountPath"=>"/es-ca","readOnly"=>true}]}],"volumes"=>[{"name"=>"logs","hostPath"=>{"path"=>"/var/log","type"=>"Directory"}},{"name"=>"buffers","hostPath"=>{"path"=>"/var/lib/cnpl05/#{run}/fluent-bit","type"=>"DirectoryOrCreate"}},{"name"=>"config","configMap"=>{"name"=>"fluent-bit"}},{"name"=>"tls","secret"=>{"secretName"=>tls}},{"name"=>"es-ca","secret"=>{"secretName"=>required("elk","ca_secret")}}]}}}},"apps/v1")
  if route=="logstash"
    items << object("ConfigMap","logstash",ns,{"data"=>{"logstash.conf"=>File.read(File.join(__dir__,"logstash.conf")),"logstash.yml"=>YAML.dump({"http.host"=>"127.0.0.1","pipeline.workers"=>1,"queue.type"=>"persisted","path.queue"=>"/queue","queue.max_bytes"=>"256mb","dead_letter_queue.enable"=>false,"xpack.monitoring.enabled"=>false})}})
    items << object("PersistentVolumeClaim","logstash-queue",ns,{"spec"=>{"storageClassName"=>required("elk","storage_class"),"accessModes"=>["ReadWriteOnce"],"resources"=>{"requests"=>{"storage"=>"1Gi"}}}})
    items << object("Deployment","logstash",ns,{"spec"=>{"replicas"=>1,"strategy"=>{"type"=>"Recreate"},"selector"=>{"matchLabels"=>{"app"=>"logstash"}},"template"=>{"metadata"=>{"labels"=>{"app"=>"logstash","cnpl.io/phase"=>"05","cnpl.io/run"=>run}},"spec"=>{"automountServiceAccountToken"=>false,"securityContext"=>{"runAsUser"=>1000,"fsGroup"=>1000},"containers"=>[{"name"=>"logstash","image"=>image("logstash"),"env"=>[{"name"=>"ES_URL","value"=>required("elk","url")},{"name"=>"INDEX_PREFIX","value"=>prefix},{"name"=>"LS_JAVA_OPTS","value"=>"-Xms256m -Xmx256m"}]+%w[ES_USER ES_PASSWORD].map { |k| {"name"=>k,"valueFrom"=>{"secretKeyRef"=>{"name"=>creds,"key"=>k}}} },"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"512Mi"},"limits"=>{"cpu"=>"1","memory"=>"1Gi"}},"volumeMounts"=>[{"name"=>"queue","mountPath"=>"/queue"},{"name"=>"config","mountPath"=>"/usr/share/logstash/pipeline/logstash.conf","subPath"=>"logstash.conf"},{"name"=>"config","mountPath"=>"/usr/share/logstash/config/logstash.yml","subPath"=>"logstash.yml"},{"name"=>"tls","mountPath"=>"/tls","readOnly"=>true},{"name"=>"ca","mountPath"=>"/es-ca","readOnly"=>true}]}],"volumes"=>[{"name"=>"queue","persistentVolumeClaim"=>{"claimName"=>"logstash-queue"}},{"name"=>"config","configMap"=>{"name"=>"logstash"}},{"name"=>"tls","secret"=>{"secretName"=>tls}},{"name"=>"ca","secret"=>{"secretName"=>required("elk","ca_secret")}}]}}}},"apps/v1")
    items << object("Service","logstash",ns,{"spec"=>{"selector"=>{"app"=>"logstash"},"ports"=>[{"name"=>"https","port"=>8080,"targetPort"=>8080}]}})
  end
  items << object("Kibana","cnpl05-#{run}",required("elk","namespace"),{"spec"=>{"version"=>material("kibana").fetch("version"),"count"=>1,"elasticsearchRef"=>{"name"=>required("elk","elasticsearch_name")},"http"=>{"tls"=>{"certificate"=>{"secretName"=>required("elk","kibana_tls_secret")}}},"podTemplate"=>{"spec"=>{"containers"=>[{"name"=>"kibana","image"=>image("kibana"),"resources"=>{"requests"=>{"cpu"=>"100m","memory"=>"512Mi"},"limits"=>{"cpu"=>"1","memory"=>"1Gi"}}}]}}}},"kibana.k8s.elastic.co/v1")
  puts JSON.pretty_generate(labeled(items))
else abort "未知渲染动作"
end
