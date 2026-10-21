#!/usr/bin/env ruby
require_relative "../lib/config"
node = required("build","node")
sc = required("build","storage_class")
image = digest_image(required("render_images","buildkit"))
items = []
%w[trusted untrusted].each do |trust|
  name = "buildkit-#{trust}"
  labels = {"app.kubernetes.io/name"=>name}
  items << {"apiVersion"=>"v1","kind"=>"ServiceAccount","metadata"=>{"name"=>name,"namespace"=>"ci-build"},"automountServiceAccountToken"=>false}
  items << {"apiVersion"=>"v1","kind"=>"Service","metadata"=>{"name"=>name,"namespace"=>"ci-build"},"spec"=>{"selector"=>labels,"ports"=>[{"name"=>"buildkit","port"=>1234,"targetPort"=>1234}]}}
  items << {"apiVersion"=>"apps/v1","kind"=>"StatefulSet","metadata"=>{"name"=>name,"namespace"=>"ci-build"},"spec"=>{"serviceName"=>name,"replicas"=>1,"selector"=>{"matchLabels"=>labels},"template"=>{"metadata"=>{"labels"=>labels},"spec"=>{"serviceAccountName"=>name,"automountServiceAccountToken"=>false,"nodeSelector"=>{"kubernetes.io/hostname"=>node},"securityContext"=>{"runAsUser"=>1000,"runAsGroup"=>1000,"fsGroup"=>1000,"runAsNonRoot"=>true,"seccompProfile"=>{"type"=>"RuntimeDefault"}},"containers"=>[{"name"=>"buildkit","image"=>image,"args"=>["--addr","tcp://0.0.0.0:1234","--tlscacert","/tls/ca.crt","--tlscert","/tls/tls.crt","--tlskey","/tls/tls.key"],"securityContext"=>{"allowPrivilegeEscalation"=>false,"capabilities"=>{"drop"=>["ALL"]}},"ports"=>[{"containerPort"=>1234}],"readinessProbe"=>{"tcpSocket"=>{"port"=>1234},"initialDelaySeconds"=>5},"resources"=>{"requests"=>{"cpu"=>"250m","memory"=>"512Mi","ephemeral-storage"=>"1Gi"},"limits"=>{"cpu"=>"1","memory"=>"2Gi","ephemeral-storage"=>"4Gi"}},"volumeMounts"=>[{"name"=>"state","mountPath"=>"/home/user/.local/share/buildkit"},{"name"=>"tls","mountPath"=>"/tls","readOnly"=>true}]}],"volumes"=>[{"name"=>"tls","secret"=>{"secretName"=>required("build","tls_secret")}}]}},"volumeClaimTemplates"=>[{"metadata"=>{"name"=>"state"},"spec"=>{"accessModes"=>["ReadWriteOnce"],"storageClassName"=>sc,"resources"=>{"requests"=>{"storage"=>"10Gi"}}}}]}}
  items << {"apiVersion"=>"networking.k8s.io/v1","kind"=>"NetworkPolicy","metadata"=>{"name"=>name,"namespace"=>"ci-build"},"spec"=>{"podSelector"=>{"matchLabels"=>labels},"policyTypes"=>["Ingress"],"ingress"=>[{"from"=>%w[ci-gitlab ci-jenkins tekton-lab].map { |ns| {"namespaceSelector"=>{"matchLabels"=>{"kubernetes.io/metadata.name"=>ns}},"podSelector"=>{"matchLabels"=>{"cnpl.io/trust"=>trust}}} },"ports"=>[{"port"=>1234,"protocol"=>"TCP"}]}]}}
end
puts JSON.pretty_generate(label(items))
