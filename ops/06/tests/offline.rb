#!/usr/bin/env ruby
# 不开监听端口，不运行组件。外部客户端由 fail-fast 替身拦截。
require "json"
require "tmpdir"
require "fileutils"
require "open3"
require "digest"
root = File.expand_path("..",__dir__)
checks = 0
Dir.mktmpdir("cnpl06-offline-") do |temp|
  audit = File.join(temp,"external-calls")
  bin = File.join(temp,"bin"); Dir.mkdir(bin)
  %w[kubectl helm ssh scp curl wget docker podman kind k3d clusterctl cilium velero kcadm.sh vault sops age-keygen virtctl].each do |name|
    File.write(File.join(bin,name),"#!/usr/bin/env bash\nprintf '%s\\n' '#{name}' >> '#{audit}'\nexit 97\n")
    File.chmod(0755,File.join(bin,name))
  end
  input = JSON.parse(File.read(File.join(root,"inputs.json")))
  input["run_id"] = "offline-review"
  input["images"].keys.each { |key| input["images"][key] = "harbor.k8s.internal.egon.top/lab/#{key}@sha256:#{'a'*64}" }
  input["admission"]["psa_version"] = "v1.36"
  input["admission"]["public_key_file"] = File.join(temp,"cosign.pub")
  File.write(input["admission"]["public_key_file"],"fixture-public-material\n")
  input["admission"]["public_key_sha256"] = Digest::SHA256.file(input["admission"]["public_key_file"]).hexdigest
  input["scaling"].merge!({"kafka_bootstrap"=>"kafka.example:9093","kafka_topic"=>"lab","kafka_group"=>"lab","kafka_partitions"=>3,"kafka_auth_secret"=>"kafka-client","rabbit_host"=>"rabbit.example:5671","rabbit_queue"=>"lab","rabbit_auth_secret"=>"rabbit-client"})
  input["secrets"].merge!({"vault_server"=>"https://vault.k8s.internal.egon.top","vault_path"=>"kv","vault_role"=>"lab","vault_ca_secret"=>"vault-ca"})
  input["runtime"]["node"] = "worker01.k8s.internal.egon.top"
  input["serverless"].merge!({"broker_class"=>"MTChannelBasedBroker","stable_revision"=>"hello-stable","canary_revision"=>"hello-canary"})
  input["dapr"].merge!({"redis_host"=>"redis.example:6379","redis_secret"=>"redis-client"})
  input["workflow"].merge!({"artifact_endpoint"=>"s3.example:9000","artifact_bucket"=>"lab-artifacts","artifact_secret"=>"artifact-client","webhook_secret"=>"webhook-auth"})
  input["workflow"].merge!({"jetstream_version"=>"2.12.0","jetstream_storage_class"=>"lab-ceph-rbd"})
  input["multicluster"].merge!({"primary_id"=>1,"secondary_id"=>2,"repository"=>"https://gitlab.svc.internal.egon.top/lab/gitops.git","revision"=>"a"*40,"path"=>"environments/lab","argocd_namespace"=>"argocd-lab","argocd_project"=>"lab"})
  input["multicluster"].merge!({"target"=>"primary","primary_name"=>"lab-primary","secondary_name"=>"lab-secondary","primary_argocd_name"=>"primary","secondary_argocd_name"=>"secondary"})
  input["virtualization"].merge!({"node"=>"worker01.k8s.internal.egon.top","storage_class"=>"lab-ceph-rbd","registry_image"=>input["images"]["http"]})
  input["virtualization"].merge!({"registry_secret"=>"registry-reader","registry_ca_configmap"=>"registry-ca"})
  input["gpu"].merge!({"node"=>"worker01.k8s.internal.egon.top","device_class"=>"lab-gpu"})
  input["ai"].merge!({"storage_uri"=>"s3://models/fixture","runtime_name"=>"lab-sklearn","model_pvc"=>"lab-model","model_name"=>"lab-model"})
  input["ai"].merge!({"deployment_mode"=>"RawDeployment","model_secret"=>"model-reader","storage_class"=>"lab-ceph-rbd"})
  input["backup"].merge!({"velero_namespace"=>"velero-lab","location"=>"independent","source_namespace"=>"cnpl06-data-offline-review","data_movement"=>"csi"})
  input["backup"].merge!({"credential_secret"=>"backup-credentials","bucket"=>"independent-lab","region"=>"lab","s3_url"=>"https://backup.example.internal.egon.top"})
  fixture = File.join(temp,"inputs.json"); File.write(fixture,JSON.generate(input))
  env = {"CNPL06_INPUTS"=>fixture,"PATH"=>bin+":"+ENV.fetch("PATH")}
  Dir.glob(File.join(root,"[0-1][0-9]","render.rb")).sort.each do |file|
    stage = File.basename(File.dirname(file))
    out,err,status = Open3.capture3(env.merge("STAGE"=>stage),"ruby",file)
    abort "render #{stage} 失败：#{err}" unless status.success?
    list = JSON.parse(out)
    abort "render #{stage} 非 List" unless list["kind"] == "List" && list["items"].is_a?(Array) && !list["items"].empty?
    list["items"].each do |d|
      abort "缺少归属 #{stage}" unless d.dig("metadata","labels","cnpl.io/run") == "offline-review"
      abort "明文 Secret 入清单" if d["kind"] == "Secret"
    end
    checks += 1
  end
  Dir.glob(File.join(root,"[0-1][0-9]","run.sh")).sort.each do |file|
    _out,_err,status = Open3.capture3(env,"bash",file,"invalid-action")
    abort "非法动作未拒绝：#{file}" if status.success?
    checks += 1
  end
  # 待填配置应在任何真实外部客户端调用前失败。
  empty = File.join(temp,"pending.json"); File.write(empty,File.read(File.join(root,"inputs.json")))
  _out,_err,status = Open3.capture3(env.merge("CNPL06_INPUTS"=>empty),"bash",File.join(root,"01/run.sh"),"apply")
  abort "未填目标未拒绝" if status.success?
  secret = File.join(temp,"private"); File.write(secret,"local-fixture")
  File.chmod(0644,secret)
  _out,_err,status = Open3.capture3(env,"ruby",File.join(root,"lib/config.rb"),"private",secret)
  abort "宽权限秘密未拒绝" if status.success?
  File.chmod(0600,secret)
  _out,err,status = Open3.capture3(env,"ruby",File.join(root,"lib/config.rb"),"private",secret)
  abort "受控秘密误拒绝 #{err}" unless status.success?
  link = File.join(temp,"link"); File.symlink(secret,link)
  _out,_err,status = Open3.capture3(env,"ruby",File.join(root,"lib/config.rb"),"private",link)
  abort "秘密软链接未拒绝" if status.success?
  scope = File.join(temp,"scope.json"); File.write(scope,JSON.generate({"namespaces"=>["cnpl06-01-offline-review"],"cluster_resources"=>[]}))
  malicious = File.join(temp,"object.yaml")
  [{"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>"kube-system"}},{"apiVersion"=>"v1","kind"=>"Secret","metadata"=>{"name"=>"bad","namespace"=>"cnpl06-01-offline-review"},"data"=>{"token"=>"ZmFrZQ=="}},{"apiVersion"=>"v1","kind"=>"Pod","metadata"=>{"name"=>"bad","namespace"=>"cnpl06-01-offline-review"},"spec"=>{"containers"=>[{"image"=>"nginx:latest"}]}}].each do |obj|
    File.write(malicious,JSON.generate(obj))
    _out,_err,status = Open3.capture3(env.merge("STAGE"=>"01"),"ruby",File.join(root,"lib/config.rb"),"prepare",malicious,scope)
    abort "危险清单未拒绝" if status.success?
    checks += 1
  end
  File.write(malicious,"apiVersion: v1\nkind: Pod\nkind: Service\n")
  _out,_err,status = Open3.capture3(env.merge("STAGE"=>"01"),"ruby",File.join(root,"lib/config.rb"),"prepare",malicious,scope)
  abort "重复键未拒绝" if status.success?
  abort "离线检查误调用外部客户端：#{File.read(audit)}" if File.exist?(audit)
  checks += 6
end
puts "PASS #{checks} 组离线构造/拒绝路径检查；外部客户端调用为零"
