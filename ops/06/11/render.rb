#!/usr/bin/env ruby
require_relative "../lib/config"
items = base
# 专用 VM 空间的权限例外必须单独授权，不扩展到普通业务空间。
items.first["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] = "privileged"
size = required("virtualization","disk_gib")
abort "磁盘必须为 1-10 GiB" unless size.is_a?(Integer) && (1..10).include?(size)
ref = digest_image(required("virtualization","registry_image"))
volume = object("cdi.kubevirt.io/v1beta1","DataVolume","vm-root",{"source"=>{"registry"=>{"url"=>"docker://#{ref}","secretRef"=>required("virtualization","registry_secret"),"certConfigMap"=>required("virtualization","registry_ca_configmap")}},"storage"=>{"accessModes"=>["ReadWriteOnce"],"volumeMode"=>"Filesystem","storageClassName"=>required("virtualization","storage_class"),"resources"=>{"requests"=>{"storage"=>"#{size}Gi"}}}})
vm = object("kubevirt.io/v1","VirtualMachine","vm-demo",{"runStrategy"=>"Halted","template"=>{"metadata"=>{"labels"=>labels.merge("app"=>"vm-demo")},"spec"=>{"nodeSelector"=>{"kubernetes.io/hostname"=>required("virtualization","node")},"domain"=>{"cpu"=>{"cores"=>1},"resources"=>{"requests"=>{"cpu"=>"1","memory"=>"1Gi"},"limits"=>{"cpu"=>"1","memory"=>"1Gi"}},"devices"=>{"disks"=>[{"name"=>"root","disk"=>{"bus"=>"virtio"}}],"interfaces"=>[{"name"=>"default","masquerade"=>{}}]}},"networks"=>[{"name"=>"default","pod"=>{}}],"volumes"=>[{"name"=>"root","dataVolume"=>{"name"=>"vm-root"}}]}}})
emit(items+[volume,vm])
