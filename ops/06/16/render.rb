#!/usr/bin/env ruby
require_relative "../lib/config"
ns = required("backup","velero_namespace")
source = required("backup","source_namespace")
abort "备份源不能是系统/整个集群" if %w[default kube-system kube-public kube-node-lease].include?(source) || !source.match?(/\A[a-z0-9][a-z0-9-]{0,62}\z/)
mode = required("backup","data_movement")
abort "必须选择 csi 或 filesystem，不能仅备份快照引用" unless %w[csi filesystem].include?(mode)
location = required("backup","location")
if ARGV[0] == "location"
  url = required("backup","s3_url")
  abort "独立备份入口必须 HTTPS" unless url.match?(%r{\Ahttps://[a-z0-9.-]+(?::\d+)?\z})
  emit([object("velero.io/v1","BackupStorageLocation",location,{"provider"=>"aws","credential"=>{"name"=>required("backup","credential_secret"),"key"=>"cloud"},"objectStorage"=>{"bucket"=>required("backup","bucket"),"prefix"=>"cnpl06/#{run}"},"config"=>{"region"=>required("backup","region"),"s3ForcePathStyle"=>"true","s3Url"=>url}},ns)]); exit
end
name = "cnpl06-#{run}"
if ARGV[0] == "restore"
  emit([object("velero.io/v1","Restore","#{name}-restore",{"backupName"=>name,"includedNamespaces"=>[source],"includeClusterResources"=>false,"namespaceMapping"=>{source=>"cnpl06-16-restored-#{run}"}},ns)]); exit
end
spec = {"includedNamespaces"=>[source],"includeClusterResources"=>false,"storageLocation"=>location,"ttl"=>"168h0m0s","snapshotVolumes"=>mode == "csi","defaultVolumesToFsBackup"=>mode == "filesystem"}
spec["snapshotMoveData"] = true if mode == "csi"
emit([object("velero.io/v1","Backup",name,spec,ns)])
