#!/usr/bin/env ruby
require "json"
family, image, storage, tls, run = ARGV
abort "未知缓存模式" unless %w[redis redis-sentinel redis-cluster valkey].include?(family)
namespace = "cnpl03-08"
def service(name, ports)
  {apiVersion: "v1", kind: "Service", metadata: {name: name}, spec: {clusterIP: "None", publishNotReadyAddresses: true, selector: {"cache-group" => name}, ports: ports.map { |p| {name: "tcp-#{p}", port: p} }}}
end
base = <<~CONF
  bind 0.0.0.0
  port 0
  tls-port 6379
  tls-cert-file /tls/tls.crt
  tls-key-file /tls/tls.key
  tls-ca-cert-file /tls/ca.crt
  tls-auth-clients yes
  tls-replication yes
  appendonly yes
  appendfsync everysec
  save 60 1
  dir /data
  maxmemory 64mb
  maxmemory-policy allkeys-lru
CONF
items = []
groups = family == "redis-cluster" ? ("a".."f").map { |n| "redis-cluster-#{n}" } : [family]
groups.each_with_index do |name, index|
  replicas = family == "redis-sentinel" ? 3 : 1
  script = <<~SH
    set -eu
    umask 077
    if [ ! -f /data/redis.conf ]; then
      cp /config/redis.conf /data/redis.conf
      printf 'requirepass %s\nmasterauth %s\n' "$(cat /auth/password)" "$(cat /auth/password)" >> /data/redis.conf
  SH
  if family == "redis-sentinel"
    script += "  case \"$HOSTNAME\" in *-0) ;; *) printf 'replicaof redis-sentinel-0.redis-sentinel.#{namespace}.svc.cluster.local 6379\\n' >> /data/redis.conf ;; esac\n"
  elsif family == "redis-cluster"
    script += "  printf 'cluster-enabled yes\\ncluster-config-file /data/nodes.conf\\ncluster-node-timeout 5000\\ntls-cluster yes\\ncluster-announce-hostname %s.#{name}.#{namespace}.svc.cluster.local\\ncluster-preferred-endpoint-type hostname\\n' \"$HOSTNAME\" >> /data/redis.conf\n"
  end
  script += "fi\nexec #{family == 'valkey' ? 'valkey-server' : 'redis-server'} /data/redis.conf\n"
  items << {apiVersion: "v1", kind: "ConfigMap", metadata: {name: name}, data: {"redis.conf" => base, "start.sh" => script}}
  items << service(name, family == "redis-cluster" ? [6379, 16379] : [6379])
  pod = {
    securityContext: {runAsUser: 999, runAsGroup: 999, fsGroup: 999},
    tolerations: [{operator: "Exists", effect: "NoSchedule"}],
    containers: [{name: "cache", image: image, command: ["sh", "/config/start.sh"],
      ports: [{name: "tls", containerPort: 6379}], resources: {requests: {cpu: "50m", memory: "128Mi"}, limits: {memory: "256Mi"}},
      readinessProbe: {exec: {command: ["sh", "-ceu", "export REDISCLI_AUTH=\"$(cat /auth/password)\"; #{family == 'valkey' ? 'valkey-cli' : 'redis-cli'} --tls --cacert /tls/ca.crt --cert /tls/tls.crt --key /tls/tls.key -h \"$HOSTNAME.#{name}.#{namespace}.svc.cluster.local\" ping | grep -Fx PONG"]}, initialDelaySeconds: 5, periodSeconds: 5},
      volumeMounts: [{name: "data", mountPath: "/data"}, {name: "config", mountPath: "/config", readOnly: true}, {name: "auth", mountPath: "/auth", readOnly: true}, {name: "tls", mountPath: "/tls", readOnly: true}]}],
    volumes: [{name: "config", configMap: {name: name}}, {name: "auth", secret: {secretName: "cache-auth", defaultMode: 288}}, {name: "tls", secret: {secretName: tls, defaultMode: 288}}]
  }
  if family == "redis-cluster"
    # 前三个为主，后三个依次放到另一物理域，bootstrap 再按明确关系加入 replica。
    node = %w[storage01 storage02 storage03 storage02 storage03 storage01][index]
    pod[:nodeSelector] = {"kubernetes.io/hostname" => node}
  else
    pod[:nodeSelector] = {"cnpl.io/phase03-data" => "true"}
    pod[:affinity] = {podAntiAffinity: {requiredDuringSchedulingIgnoredDuringExecution: [{topologyKey: "cnpl.io/esxi", labelSelector: {matchLabels: {"cache-group" => name}}}]}}
  end
  items << {apiVersion: "apps/v1", kind: "StatefulSet", metadata: {name: name}, spec: {
    serviceName: name, replicas: replicas, selector: {matchLabels: {"cache-group" => name}},
    persistentVolumeClaimRetentionPolicy: {whenDeleted: "Retain", whenScaled: "Retain"},
    template: {metadata: {labels: {"cache-group" => name, "cnpl.io/run" => run}}, spec: pod},
    volumeClaimTemplates: [{metadata: {name: "data"}, spec: {storageClassName: storage, accessModes: ["ReadWriteOnce"], resources: {requests: {storage: "1Gi"}}}}]
  }}
end
if family == "redis-sentinel"
  script = <<~SH
    set -eu
    umask 077
    if [ ! -f /data/sentinel.conf ]; then
      printf 'port 0\ntls-port 26379\ntls-cert-file /tls/tls.crt\ntls-key-file /tls/tls.key\ntls-ca-cert-file /tls/ca.crt\ntls-auth-clients yes\ntls-replication yes\nsentinel resolve-hostnames yes\nsentinel announce-hostnames yes\nsentinel monitor lab redis-sentinel-0.redis-sentinel.#{namespace}.svc.cluster.local 6379 2\nsentinel down-after-milliseconds lab 5000\nsentinel failover-timeout lab 30000\nsentinel parallel-syncs lab 1\nsentinel auth-pass lab %s\nrequirepass %s\n' "$(cat /auth/password)" "$(cat /auth/password)" > /data/sentinel.conf
    fi
    exec redis-server /data/sentinel.conf --sentinel
  SH
  sentinel = Marshal.load(Marshal.dump(items.find { |x| x[:kind] == "StatefulSet" }))
  sentinel[:metadata][:name] = "sentinel"
  sentinel[:spec][:serviceName] = "sentinel"
  sentinel[:spec][:selector][:matchLabels] = {"cache-group" => "sentinel"}
  sentinel[:spec][:template][:metadata][:labels]["cache-group"] = "sentinel"
  spec = sentinel[:spec][:template][:spec]
  spec[:containers][0][:command] = ["sh", "-ceu", script]
  spec[:containers][0][:readinessProbe][:exec][:command] = ["sh", "-ceu", 'export REDISCLI_AUTH="$(cat /auth/password)"; redis-cli --tls --cacert /tls/ca.crt --cert /tls/tls.crt --key /tls/tls.key -p 26379 ping | grep -Fx PONG']
  spec[:affinity][:podAntiAffinity][:requiredDuringSchedulingIgnoredDuringExecution][0][:labelSelector][:matchLabels] = {"cache-group" => "sentinel"}
  items << service("sentinel", [26379]) << sentinel
end
puts JSON.pretty_generate({apiVersion: "v1", kind: "List", items: items})
