#!/usr/bin/env ruby
# 不开监听端口，不运行组件。外部客户端由 fail-fast 替身拦截。
require "json"
require "tmpdir"
require "fileutils"
require "open3"
require "digest"
require "yaml"
require "openssl"
root = File.expand_path("..",__dir__)
checks = 0
Dir.mktmpdir("cnpl06-offline-") do |temp|
  audit = File.join(temp,"external-calls")
  bin = File.join(temp,"bin"); Dir.mkdir(bin)
  %w[kubectl helm ssh scp curl wget docker podman kind k3d clusterctl cilium velero kcadm.sh vault sops age-keygen virtctl argo argocd dapr kn aws govc kubeadm etcdctl etcdutl ansible ansible-playbook dnf rpm systemctl firewall-cmd].each do |name|
    File.write(File.join(bin,name),"#!/usr/bin/env bash\nprintf '%s\\n' '#{name}' >> '#{audit}'\nexit 97\n")
    File.chmod(0755,File.join(bin,name))
  end
  input = JSON.parse(File.read(File.join(root,"inputs.json")))
  input["run_id"] = "offline-review"
  input["images"].keys.each { |key| input["images"][key] = "harbor.k8s.internal.egon.top/lab/#{key}@sha256:#{'a'*64}" }
  input["admission"]["psa_version"] = "v1.36"
  input["admission"]["public_key_file"] = File.join(temp,"cosign.pub")
  File.write(input["admission"]["public_key_file"],OpenSSL::PKey::RSA.new(1024).public_key.to_pem)
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
  test = lambda do |name, command, success, overrides={}|
    out,err,stat = Open3.capture3(env.merge(overrides),*command)
    abort "#{name} 结果不符：#{err}" unless stat.success? == success
    checks += 1
    out
  end
  write_json = lambda do |name, value|
    file = File.join(temp,name)
    File.write(file,JSON.generate(value)); file
  end
  # 子模式构造：队列、MCS、DRA、CPU/GPU 训练和三种故障都只渲染。
  [["08","queues"],["10","gitops"],["10","mcs"],["12","dra"],["13","vllm"],["13","training"]].each do |stage,mode|
    result = JSON.parse(test.call("render #{stage}/#{mode}",["ruby",File.join(root,stage,"render.rb"),mode],true,{"STAGE"=>stage}))
    if stage == "08"
      queue = result["items"].find { |d| d["kind"]=="ClusterQueue" }
      abort "训练阶段未被队列显式允许" unless queue.dig("spec","namespaceSelector","matchExpressions",0,"values") == ["08","13"]
    end
  end
  %w[pod network stress].each do |kind|
    changed = Marshal.load(Marshal.dump(input)); changed["chaos"]["kind"] = kind
    changed_file = write_json.call("chaos-#{kind}.json",changed)
    result = JSON.parse(test.call("bounded #{kind}",["ruby",File.join(root,"14/render.rb"),"fault"],true,{"STAGE"=>"14","CNPL06_INPUTS"=>changed_file}))
    fault = result["items"].fetch(0)
    abort "故障越界" unless fault.dig("spec","selector","namespaces") == ["cnpl06-14-offline-review"] && fault.dig("spec","mode") == "one" && fault.dig("spec","duration") == "20s"
  end
  [0,61,"30",-1].each do |duration|
    changed = Marshal.load(Marshal.dump(input)); changed["chaos"]["duration_seconds"] = duration
    test.call("bad duration",["ruby",File.join(root,"14/render.rb"),"fault"],false,{"STAGE"=>"14","CNPL06_INPUTS"=>write_json.call("bad-duration.json",changed)})
  end
  File.write(File.join(temp,"duplicates.json"),'{"schema_version":1,"schema_version":2}')
  test.call("duplicate JSON keys",["ruby",File.join(root,"lib/config.rb"),"source"],false,{"CNPL06_INPUTS"=>File.join(temp,"duplicates.json")})
  changed = Marshal.load(Marshal.dump(input)); changed["images"]["http"] = "harbor.k8s.internal.egon.top/lab/demo:latest"
  test.call("tagged app image",["ruby",File.join(root,"01/render.rb")],false,{"STAGE"=>"01","CNPL06_INPUTS"=>write_json.call("tagged.json",changed)})
  message = {"published_ids"=>["a","b"],"acknowledged_ids"=>["a","a","b"],"effect_ids"=>["a","b"]}
  test.call("duplicate delivery allowed",["ruby",File.join(root,"05/messages.rb"),write_json.call("messages.json",message)],true)
  [message.merge("effect_ids"=>["a"]),message.merge("effect_ids"=>["a","b","b"]),message.merge("effect_ids"=>["a","b","unknown"])].each do |data|
    test.call("lost duplicate unknown effects",["ruby",File.join(root,"05/messages.rb"),write_json.call("messages-bad.json",data)],false)
  end
  timeline = {"recovery_route"=>"etcd-restore","failure_started_at"=>"2026-10-21T00:00:00Z","recovery_started_at"=>"2026-10-21T00:00:10Z","infrastructure_ready_at"=>"2026-10-21T00:01:00Z","business_verified_at"=>"2026-10-21T00:02:00Z","source_last_acknowledged_at"=>"2026-10-21T00:00:00Z","latest_recovered_data_time"=>"2026-10-20T23:59:50Z","lost_records"=>0,"duplicate_records"=>0,"rto_target_seconds"=>180,"rpo_target_seconds"=>15}
  result = JSON.parse(test.call("real timeline arithmetic",["ruby",File.join(root,"17/report.rb"),write_json.call("timeline.json",timeline)],true))
  abort "RTO/RPO 计算错误" unless result["rto_seconds"] == 120 && result["rpo_seconds"] == 10 && result["runtime_accepted"] == false
  [{"recovery_route"=>"both"},{"business_verified_at"=>"2026-10-20T23:59:59Z"},{"latest_recovered_data_time"=>"2026-10-21T00:00:01Z"},{"lost_records"=>1},{"failure_started_at"=>"2026-10-21T00:00:00"},{"rto_target_seconds"=>10}].each do |mutation|
    test.call("invalid timeline",["ruby",File.join(root,"17/report.rb"),write_json.call("timeline-bad.json",timeline.merge(mutation))],false)
  end
  cost = {"gpu_hours"=>2,"idle_gpu_hours"=>0.5,"gpu_hour_rate"=>3,"power_kwh"=>1,"electricity_rate"=>0.5,"successful_requests"=>10,"output_tokens"=>100,"currency"=>"fixture","assumptions"=>"fixture rates exclude power"}
  result = JSON.parse(test.call("cost arithmetic",["ruby",File.join(root,"13/cost.rb"),write_json.call("cost.json",cost)],true))
  abort "估算成本错误" unless result["estimated_cost"] == 6.5 && result["billing_exact"] == false
  test.call("invalid idle hours",["ruby",File.join(root,"13/cost.rb"),write_json.call("cost-bad.json",cost.merge("idle_gpu_hours"=>3))],false)
  # 版本路线：纯文件回执 fixture，不表示真实预演。
  changed = Marshal.load(Marshal.dump(input))
  matrix = {"source_version"=>"v1.36.5","target_version"=>"v1.37.1","components"=>%w[etcd containerd cilium ceph rook csi gateway operators api_deprecations].to_h { |key| [key,true] }}
  rehearsal = {"isolated"=>true,"target_version"=>"v1.37.1","business_data_verified"=>true}
  changed["upgrade"].merge!({"source_version"=>"v1.36.5","target_version"=>"v1.37.1"})
  {"matrix"=>matrix,"rehearsal"=>rehearsal,"freeze"=>{"fixture"=>true}}.each do |key,value|
    f = write_json.call("#{key}.json",value)
    changed["upgrade"]["#{key}_file"] = f; changed["upgrade"]["#{key}_sha256"] = Digest::SHA256.file(f).hexdigest
  end
  test.call("adjacent upgrade plan",["ruby",File.join(root,"15/plan.rb")],true,{"CNPL06_INPUTS"=>write_json.call("upgrade.json",changed)})
  changed["upgrade"]["target_version"] = "v1.38.1"
  test.call("skipped minor rejected",["ruby",File.join(root,"15/plan.rb")],false,{"CNPL06_INPUTS"=>write_json.call("upgrade-skip.json",changed)})
  # CAPI 地址与生命周期作用域。所有对象都是临时本地 JSON。
  changed = Marshal.load(Marshal.dump(input))
  changed["capi"].merge!({"cluster_name"=>"cnpl06-offline-review","node_ips"=>["192.168.9.121","192.168.9.122"],"api_ip"=>"192.168.9.120","vm_folder"=>"/lab/cnpl06-offline-review"})
  capacity = %w[primary_minimum_preserved storage_recovery_headroom dhcp_conflicts_absent vsphere_license_verified template_verified vpn_routes_reviewed].to_h { |key| [key,true] }.merge(changed["capi"].slice("node_ips","api_ip","vm_folder"))
  f = write_json.call("capacity.json",capacity); changed["capi"].merge!({"capacity_file"=>f,"capacity_sha256"=>Digest::SHA256.file(f).hexdigest})
  test.call("isolated secondary plan",["ruby",File.join(root,"09/plan.rb")],true,{"CNPL06_INPUTS"=>write_json.call("capi.json",changed)})
  changed["capi"]["pod_cidr"] = "10.244.0.0/16"
  test.call("overlapping primary CIDR",["ruby",File.join(root,"09/plan.rb")],false,{"CNPL06_INPUTS"=>write_json.call("capi-overlap.json",changed)})
  changed["capi"]["pod_cidr"] = "10.245.0.0/16"; changed["capi"]["node_ips"][0] = "192.168.9.101"
  test.call("primary node IP rejected",["ruby",File.join(root,"09/plan.rb")],false,{"CNPL06_INPUTS"=>write_json.call("capi-primary.json",changed)})
  # 主集群节点校验读取唯一台账，拒绝 IP/Ready 漂移。
  nodes = YAML.load_file(File.expand_path("../../ops/inventory/hosts.yaml",root)).fetch("kubernetes_nodes").map { |n| {"metadata"=>{"name"=>n["fqdn"]},"status"=>{"addresses"=>[{"type"=>"InternalIP","address"=>n["ip"]}],"conditions"=>[{"type"=>"Ready","status"=>"True"}]}} }
  test.call("node baseline",["ruby",File.join(root,"lib/config.rb"),"nodes","primary",write_json.call("nodes.json",{"items"=>nodes})],true)
  nodes[0]["status"]["conditions"][0]["status"] = "False"
  test.call("unready node",["ruby",File.join(root,"lib/config.rb"),"nodes","primary",write_json.call("nodes-bad.json",{"items"=>nodes})],false)
  # 归属与 UID 删除使用 shell 函数替身，不调用真实客户端。
  owned_json = {"apiVersion"=>"chaos-mesh.org/v1alpha1","kind"=>"PodChaos","metadata"=>{"name"=>"bounded-pod","namespace"=>"cnpl06-14-offline-review","uid"=>"fixture-uid","labels"=>{"cnpl.io/phase"=>"06","cnpl.io/stage"=>"14","cnpl.io/run"=>"offline-review"}}}
  object_path = write_json.call("owned.json",owned_json)
  private_dir = File.join(temp,"private-temp"); Dir.mkdir(private_dir)
  shell = <<~'SH'
    source "$TEST_ROOT/lib/common.sh"
    export STAGE=14 RUN=offline-review
    PRIVATE_TEMP=$TEST_TEMP
    k() {
      case "$1 $2" in
        "get --raw="*) printf '%s\n' '{"resources":[{"kind":"PodChaos","name":"podchaos","namespaced":true}]}' ;;
        "delete --raw="*) [[ $2 == --raw=/apis/chaos-mesh.org/v1alpha1/namespaces/cnpl06-14-offline-review/podchaos/bounded-pod ]]; jq -e '.preconditions.uid=="fixture-uid"' "$TEST_TEMP/delete.json" >/dev/null ;;
        "-n cnpl06-14-offline-review") cat "$TEST_OBJECT" ;;
        *) return 98 ;;
      esac
    }
    delete_owned podchaos bounded-pod cnpl06-14-offline-review "$TEST_UID"
  SH
  shell_env = {"TEST_ROOT"=>root,"TEST_TEMP"=>private_dir,"TEST_OBJECT"=>object_path,"TEST_UID"=>"fixture-uid"}
  test.call("API resource discovery and UID precondition",["bash","-c",shell],true,shell_env)
  test.call("stale UID deletion rejected",["bash","-c",shell],false,shell_env.merge("TEST_UID"=>"different"))
  owned_json["metadata"]["labels"]["cnpl.io/run"] = "other-run"
  File.write(object_path,JSON.generate(owned_json))
  test.call("foreign ownership rejected",["bash","-c",shell],false,shell_env)
  missing_shell = 'source "$TEST_ROOT/lib/common.sh"; STAGE=14; RUN=offline-review; k() { return 7; }; delete_owned podchaos bounded-pod cnpl06-14-offline-review fixture-uid'
  test.call("API error is not NotFound",["bash","-c",missing_shell],false,{"TEST_ROOT"=>root})
  changed = Marshal.load(Marshal.dump(input)); changed["clusters"]["primary"]["kubeconfig"] = "/fixture/not-a-real-config"
  test.call("missing context before client call",["bash","-c",'source "$TEST_ROOT/lib/common.sh"; k get nodes'],false,{"TEST_ROOT"=>root,"CNPL06_INPUTS"=>write_json.call("missing-context.json",changed)})
  attempt = File.join(temp,"attempt"); lock = File.join(temp,"lock"); Dir.mkdir(attempt); Dir.mkdir(lock)
  finish_shell = 'source "$TEST_ROOT/lib/common.sh"; ACTION=fixture; ATTEMPT=$TEST_ATTEMPT; LOCK=$TEST_LOCK; broken_restore() { return 9; }; RECOVERY_FUNCTION=broken_restore; trap finish EXIT; exit 23'
  test.call("original exit retained after recovery failure",["bash","-c",finish_shell],false,{"TEST_ROOT"=>root,"TEST_ATTEMPT"=>attempt,"TEST_LOCK"=>lock})
  exit_result = JSON.parse(File.read(File.join(attempt,"result.json")))
  abort "恢复失败覆盖原始错误" unless exit_result["exit_code"] == 23 && exit_result["recovery_exit_code"] == 9
  # 静态解析 Python 源码，不导入执行网络客户端。
  test.call("Python source syntax",["python3","-c","import ast,pathlib;ast.parse(pathlib.Path(__import__('sys').argv[1]).read_text())",File.join(root,"07/client.py")],true)
  parent = File.join(temp,"outputs"); Dir.mkdir(parent,0700)
  plain = File.join(temp,"plain"); File.write(plain,"fixture bytes\n")
  destination = File.join(parent,"result")
  test.call("private exclusive output",["ruby",File.join(root,"03/private-write.rb"),plain,destination],true)
  test.call("private output cannot overwrite",["ruby",File.join(root,"03/private-write.rb"),plain,destination],false)
  abort "原私有文件被覆盖/宽权限" unless File.read(destination)=="fixture bytes\n" && (File.stat(destination).mode & 0777)==0600
  File.chmod(0755,parent)
  test.call("wide output directory rejected",["ruby",File.join(root,"03/private-write.rb"),plain,File.join(parent,"other")],false)
  changed = Marshal.load(Marshal.dump(input))
  changed["network"]["ingress"] = [{"stage"=>"01","namespace"=>"gateway-lab","pod_labels"=>{"app"=>"gateway"},"ports"=>[{"port"=>8080,"protocol"=>"TCP"}]}]
  test.call("scoped ingress",["ruby",File.join(root,"01/render.rb")],true,{"STAGE"=>"01","CNPL06_INPUTS"=>write_json.call("ingress.json",changed)})
  changed["network"]["ingress"][0]["pod_labels"] = {}
  test.call("unscoped ingress rejected",["ruby",File.join(root,"01/render.rb")],false,{"STAGE"=>"01","CNPL06_INPUTS"=>write_json.call("ingress-bad.json",changed)})
  changed["network"]["ingress"] = []
  changed["network"]["egress"] = [{"stage"=>"01","cidr"=>"192.168.9.12/32","ports"=>[]}]
  test.call("empty ports cannot mean all ports",["ruby",File.join(root,"01/render.rb")],false,{"STAGE"=>"01","CNPL06_INPUTS"=>write_json.call("egress-bad.json",changed)})
  changed["network"]["egress"][0].merge!({"cidr"=>"0.0.0.0/0","ports"=>[{"port"=>443,"protocol"=>"TCP"}]})
  test.call("internet egress rejected",["ruby",File.join(root,"01/render.rb")],false,{"STAGE"=>"01","CNPL06_INPUTS"=>write_json.call("egress-all.json",changed)})
  changed = Marshal.load(Marshal.dump(input))
  realm_path = write_json.call("realm.json",{"realm"=>"lab","enabled"=>true})
  session_path = write_json.call("session.json",{"serverUrl"=>"https://keycloak.k8s.internal.egon.top"})
  changed["identity"].merge!({"realm_file"=>realm_path,"kcadm_config"=>session_path})
  realm_input = write_json.call("realm-input.json",changed)
  test.call("realm issuer matches session",["ruby",File.join(root,"01/realm-check.rb")],true,{"CNPL06_INPUTS"=>realm_input})
  File.write(session_path,JSON.generate({"serverUrl"=>"https://other.internal.egon.top"}))
  test.call("foreign identity session rejected",["ruby",File.join(root,"01/realm-check.rb")],false,{"CNPL06_INPUTS"=>realm_input})
  File.write(session_path,JSON.generate({"serverUrl"=>"https://keycloak.k8s.internal.egon.top"}))
  File.write(realm_path,JSON.generate({"realm"=>"lab","enabled"=>true,"clients"=>[{"clientSecret"=>"fixture-rejected"}]}))
  test.call("realm embedded credential rejected",["ruby",File.join(root,"01/realm-check.rb")],false,{"CNPL06_INPUTS"=>realm_input})
  # ClusterRole 的伪造 metadata.namespace 必须在第一次写操作前被 API scope 检查拒绝。
  spoof = write_json.call("spoof.json",{"apiVersion"=>"rbac.authorization.k8s.io/v1","kind"=>"ClusterRole","metadata"=>{"name"=>"spoof","namespace"=>"cnpl06-01-offline-review"},"rules"=>[]})
  spoof_shell = <<~'SH'
    source "$TEST_ROOT/lib/common.sh"
    export STAGE=01 RUN=offline-review
    NS=cnpl06-01-offline-review; PRIVATE_TEMP=$TEST_TEMP
    k() { if [[ $1 == get && $2 == --raw=* ]]; then printf '%s\n' '{"resources":[{"kind":"ClusterRole","name":"clusterroles","namespaced":false}]}'; else touch "$TEST_MUTATION"; return 98; fi; }
    apply_file "$TEST_FILE"
  SH
  mutation = File.join(temp,"unexpected-mutation")
  test.call("cluster scope cannot be spoofed",["bash","-c",spoof_shell],false,{"TEST_ROOT"=>root,"TEST_TEMP"=>private_dir,"TEST_MUTATION"=>mutation,"TEST_FILE"=>spoof})
  abort "集群范围检查前发生写操作" if File.exist?(mutation)
  # 先创建 Namespace 后服务端拒绝余下对象，已成功的对象仍须写入归属账本。
  partial_state = File.join(temp,"partial-state"); FileUtils.mkdir_p(File.join(partial_state,"owned"))
  partial_temp = File.join(temp,"partial-temp"); Dir.mkdir(partial_temp)
  created = File.join(temp,"created-namespace.json")
  partial_manifest = write_json.call("partial.json",{"apiVersion"=>"v1","kind"=>"List","items"=>[{"apiVersion"=>"v1","kind"=>"Namespace","metadata"=>{"name"=>"cnpl06-01-offline-review"}},{"apiVersion"=>"v1","kind"=>"ConfigMap","metadata"=>{"name"=>"later","namespace"=>"cnpl06-01-offline-review"},"data"=>{"fixture"=>"public"}}]})
  partial_shell = <<~'SH'
    source "$TEST_ROOT/lib/common.sh"
    export STAGE=01 RUN=offline-review
    NS=cnpl06-01-offline-review; PRIVATE_TEMP=$TEST_TEMP; STATE=$TEST_STATE
    k() {
      if [[ $1 == get && $2 == --raw=* ]]; then
        printf '%s\n' '{"resources":[{"kind":"Namespace","name":"namespaces","namespaced":false},{"kind":"ConfigMap","name":"configmaps","namespaced":true}]}'
      elif [[ $1 == get && $2 == namespaces ]]; then
        if [[ -f $TEST_CREATED ]]; then cat "$TEST_CREATED"; fi
      elif [[ $1 == -n ]]; then return 0
      elif [[ $1 == apply && $2 == --dry-run=server ]]; then return 14
      elif [[ $1 == apply ]]; then
        jq '.metadata.uid="created-fixture-uid"' "$TEST_TEMP/one.json" > "$TEST_CREATED"
      else return 98
      fi
    }
    apply_file "$TEST_FILE"
  SH
  test.call("partial apply retains completed object",["bash","-c",partial_shell],false,{"TEST_ROOT"=>root,"TEST_TEMP"=>partial_temp,"TEST_STATE"=>partial_state,"TEST_CREATED"=>created,"TEST_FILE"=>partial_manifest})
  receipts = Dir.glob(File.join(partial_state,"owned","*.json"))
  abort "部分成功未记归属" unless receipts.size==1 && JSON.parse(File.read(receipts[0])).dig("metadata","uid")=="created-fixture-uid"
  public_file = input["admission"]["public_key_file"]
  File.write(public_file,"-----BEGIN PRIVATE KEY-----\nZmFrZQ==\n-----END PRIVATE KEY-----\n")
  changed = Marshal.load(Marshal.dump(input)); changed["admission"]["public_key_sha256"] = Digest::SHA256.file(public_file).hexdigest
  test.call("private key cannot enter policy",["ruby",File.join(root,"02/render.rb")],false,{"STAGE"=>"02","CNPL06_INPUTS"=>write_json.call("private-key-input.json",changed)})
  redaction_input = write_json.call("redact.json",{"metadata"=>{"name"=>"public-name","annotations"=>{"test"=>"fixture-sensitive"}},"data"=>{"value"=>"fixture-sensitive"},"spec"=>{"containers"=>[{"env"=>[{"value"=>"fixture-sensitive"}],"image"=>"public-ref"}],"volumes"=>[{"projected"=>{"sources"=>[{"serviceAccountToken"=>{"audience"=>"dapr.io/sentry","expirationSeconds"=>3600}}]}}]}})
  output = test.call("evidence redaction retains projection",["bash","-c",'source "$TEST_ROOT/lib/common.sh"; redact_objects < "$TEST_FILE"'],true,{"TEST_ROOT"=>root,"TEST_FILE"=>redaction_input})
  redacted = JSON.parse(output)
  abort "敏感字段未移除/投影证据丢失" if output.include?("fixture-sensitive") || redacted.dig("spec","volumes",0,"projected","sources",0,"serviceAccountToken","audience") != "dapr.io/sentry"
  # 同名 Kind 的两个 API 组必须分别读取/记录，不能将 Knative Service 当原生 Service。
  service_temp = File.join(temp,"service-temp"); Dir.mkdir(service_temp)
  service_state = File.join(temp,"service-state"); FileUtils.mkdir_p(File.join(service_state,"owned"))
  service_manifest = write_json.call("services.json",{"apiVersion"=>"v1","kind"=>"List","items"=>["v1","serving.knative.dev/v1"].map { |api| {"apiVersion"=>api,"kind"=>"Service","metadata"=>{"name"=>"hello","namespace"=>"cnpl06-01-offline-review"},"spec"=>{}} }})
  services_shell = <<~'SH'
    source "$TEST_ROOT/lib/common.sh"
    export STAGE=01 RUN=offline-review
    NS=cnpl06-01-offline-review; PRIVATE_TEMP=$TEST_TEMP; STATE=$TEST_STATE
    k() {
      if [[ $1 == get && $2 == --raw=* ]]; then
        printf '%s\n' '{"resources":[{"kind":"Service","name":"services","namespaced":true}]}'
      elif [[ $1 == -n && $3 == get ]]; then
        case "$4" in services) file=$TEST_TEMP/core.json ;; services.serving.knative.dev) file=$TEST_TEMP/knative.json ;; *) return 98 ;; esac
        if [[ -f $file ]]; then cat "$file"; fi
      elif [[ $1 == apply && $2 == --dry-run=server ]]; then return 0
      elif [[ $1 == apply ]]; then
        api=$(jq -r .apiVersion "$TEST_TEMP/one.json")
        if [[ $api == v1 ]]; then file=$TEST_TEMP/core.json; else file=$TEST_TEMP/knative.json; fi
        jq --arg uid "fixture-$api" '.metadata.uid=$uid' "$TEST_TEMP/one.json" > "$file"
      else return 98
      fi
    }
    apply_file "$TEST_FILE"
  SH
  test.call("same Kind different API groups",["bash","-c",services_shell],true,{"TEST_ROOT"=>root,"TEST_TEMP"=>service_temp,"TEST_STATE"=>service_state,"TEST_FILE"=>service_manifest})
  services = Dir.glob(File.join(service_state,"owned","*.json")).map { |f| JSON.parse(File.read(f))["apiVersion"] }
  abort "同名 Kind 的归属记录混淆" unless services.sort == ["serving.knative.dev/v1","v1"]
  crd_temp = File.join(temp,"crd-temp"); Dir.mkdir(crd_temp)
  crd_state = File.join(temp,"crd-state"); FileUtils.mkdir_p(File.join(crd_state,"owned"))
  crd_manifest = write_json.call("crd-bundle.json",{"apiVersion"=>"v1","kind"=>"List","items"=>[{"apiVersion"=>"apiextensions.k8s.io/v1","kind"=>"CustomResourceDefinition","metadata"=>{"name"=>"demos.fixture.test"},"spec"=>{"group"=>"fixture.test","scope"=>"Namespaced","names"=>{"kind"=>"Demo","plural"=>"demos"},"versions"=>[{"name"=>"v1","served"=>true,"storage"=>true}]}},{"apiVersion"=>"fixture.test/v1","kind"=>"Demo","metadata"=>{"name"=>"demo","namespace"=>"cnpl06-01-offline-review"},"spec"=>{}}]})
  crd_scope = write_json.call("crd-scope.json",{"namespaces"=>["cnpl06-01-offline-review"],"cluster_resources"=>["CustomResourceDefinition/demos.fixture.test"]})
  crd_shell = <<~'SH'
    source "$TEST_ROOT/lib/common.sh"
    export STAGE=01 RUN=offline-review
    NS=cnpl06-01-offline-review; PRIVATE_TEMP=$TEST_TEMP; STATE=$TEST_STATE
    k() {
      if [[ $1 == get && $2 == --raw=* ]]; then
        [[ $2 == --raw=/apis/apiextensions.k8s.io/v1 ]] || return 98
        printf '%s\n' '{"resources":[{"kind":"CustomResourceDefinition","name":"customresourcedefinitions","namespaced":false}]}'
      elif [[ $1 == get ]]; then
        case "$2" in crd|customresourcedefinitions.apiextensions.k8s.io) ;; *) return 98 ;; esac
        if [[ -f $TEST_TEMP/crd.json ]]; then cat "$TEST_TEMP/crd.json"; fi
      elif [[ $1 == -n && $3 == get ]]; then
        [[ -f $TEST_TEMP/served && $4 == demos.fixture.test ]] || return 98
        if [[ -f $TEST_TEMP/demo.json ]]; then cat "$TEST_TEMP/demo.json"; fi
      elif [[ $1 == wait ]]; then touch "$TEST_TEMP/served"
      elif [[ $1 == apply && $2 == --dry-run=server ]]; then [[ -f $TEST_TEMP/served ]]
      elif [[ $1 == apply ]]; then
        kind=$(jq -r .kind "$TEST_TEMP/one.json")
        if [[ $kind == CustomResourceDefinition ]]; then file=$TEST_TEMP/crd.json; else [[ -f $TEST_TEMP/served ]] || return 98; file=$TEST_TEMP/demo.json; fi
        jq '.metadata.uid="fixture-uid"' "$TEST_TEMP/one.json" > "$file"
      else return 98
      fi
    }
    apply_file "$TEST_FILE" "$TEST_SCOPE"
  SH
  test.call("new CRD then CR without premature lookup",["bash","-c",crd_shell],true,{"TEST_ROOT"=>root,"TEST_TEMP"=>crd_temp,"TEST_STATE"=>crd_state,"TEST_FILE"=>crd_manifest,"TEST_SCOPE"=>crd_scope})
  final_attempt = File.join(temp,"stale-recovery-attempt"); final_lock = File.join(temp,"stale-recovery-lock")
  Dir.mkdir(final_attempt); Dir.mkdir(final_lock)
  stale_recovery_shell = 'source "$TEST_ROOT/lib/common.sh"; ACTION=fixture; ATTEMPT=$TEST_ATTEMPT; LOCK=$TEST_LOCK; owned() { printf "%s\n" \'{"apiVersion":"chaos-mesh.org/v1alpha1","kind":"PodChaos","metadata":{"uid":"current-uid"}}\'; }; stale_restore() { delete_owned podchaos bounded-pod lab expected-old-uid; }; RECOVERY_FUNCTION=stale_restore; trap finish EXIT; exit 23'
  test.call("stale cleanup still records original and recovery failure",["bash","-c",stale_recovery_shell],false,{"TEST_ROOT"=>root,"TEST_ATTEMPT"=>final_attempt,"TEST_LOCK"=>final_lock})
  final_result = JSON.parse(File.read(File.join(final_attempt,"result.json")))
  abort "过期 UID 中断恢复结果归档" unless final_result["exit_code"]==23 && final_result["recovery_exit_code"]==1
  abort "离线检查误调用外部客户端：#{File.read(audit)}" if File.exist?(audit)
  checks += 6
end
puts "PASS #{checks} 组离线构造/拒绝路径检查；外部客户端调用为零"
