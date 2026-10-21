#!/usr/bin/env ruby
# 外部客户端均替换成本地文件替身，专测归属、UID、并发与恢复退出码。
require "json"
require "tmpdir"
require "open3"
root = File.expand_path("..",__dir__)
count = 0
Dir.mktmpdir("cnpl05-guards-") do |dir|
  bin = File.join(dir,"bin"); Dir.mkdir(bin)
  stub = <<'PY'
#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as out: out.write(json.dumps(args)+'\n')
if os.environ.get('CLIENT_FAIL'): sys.exit(44)
with open(os.environ['FIXTURE']) as stream: obj = json.load(stream)
if 'get' in args:
    print(json.dumps(obj))
elif 'patch' in args:
    with open(args[args.index('--patch-file')+1]) as stream: patch = json.load(stream)
    for op in patch:
        value = obj
        keys = op['path'].strip('/').split('/')
        for key in keys[:-1]: value = value[key]
        if op['op']=='test' and value[keys[-1]]!=op['value']: sys.exit(42)
        if op['op']=='replace': value[keys[-1]]=op['value']
    with open(os.environ['FIXTURE'], 'w') as out: json.dump(obj, out)
    print('patched local fixture')
elif 'apply' in args:
    print('applied local fixture')
else: sys.exit(43)
PY
  File.write(File.join(bin,"kubectl"),stub); File.chmod(0700,File.join(bin,"kubectl"))
  File.write(File.join(bin,"curl"),"#!/usr/bin/env bash\nprintf 'curl-called\\n' >> \"$CALLS\"\nexit 44\n"); File.chmod(0700,File.join(bin,"curl"))
  fixture = File.join(dir,"object.json"); calls = File.join(dir,"calls.jsonl")
  input = JSON.parse(File.read(File.join(root,"inputs.json")))
  input["run_id"]="offline-review"; input["kubernetes"].merge!({"context"=>"offline","kubeconfig"=>File.join(dir,"dummy-kubeconfig")})
  input_path=File.join(dir,"input.json"); File.write(input_path,JSON.generate(input))
  env={"PATH"=>bin+":"+ENV.fetch("PATH"),"CNPL05_INPUTS"=>input_path,"FIXTURE"=>fixture,"CALLS"=>calls}
  initial={"apiVersion"=>"apps/v1","kind"=>"Deployment","metadata"=>{"name"=>"test","namespace"=>"telemetry","uid"=>"fixture-uid","resourceVersion"=>"5","labels"=>{"cnpl.io/phase"=>"05","cnpl.io/run"=>"offline-review"}},"spec"=>{"replicas"=>0}}
  snapshot=File.join(dir,"target.json"); File.write(snapshot,JSON.generate({"namespace"=>"telemetry","name"=>"test","uid"=>"fixture-uid","replicas"=>3}))
  recover=lambda do |object,success,extra={}|
    File.write(fixture,JSON.generate(object)); File.write(calls,"")
    attempt=Dir.mktmpdir("attempt-",dir)
    _,status=Open3.capture2e(env.merge(extra),"bash",File.join(root,"lib/recover.sh"),input_path,snapshot,attempt,"0")
    abort "恢复拒绝路径不符" unless status.success? == success
    if success
      abort "未恢复原副本" unless JSON.parse(File.read(fixture)).dig("spec","replicas")==3 && File.file?(File.join(attempt,"restored.json"))
    else
      abort "失败恢复产生成功回执" if File.file?(File.join(attempt,"restored.json"))
      abort "应拒绝变更却调用 patch" if File.read(calls).lines.any? { |l| JSON.parse(l).include?("patch") }
    end
    count+=1
  end
  recover.call(initial,true)
  changed=Marshal.load(Marshal.dump(initial)); changed["metadata"]["uid"]="replacement"; recover.call(changed,false)
  changed=Marshal.load(Marshal.dump(initial)); changed["metadata"]["labels"]["cnpl.io/run"]="other"; recover.call(changed,false)
  changed=Marshal.load(Marshal.dump(initial)); changed["metadata"]["annotations"]={"argocd.argoproj.io/tracking-id"=>"other"}; recover.call(changed,false)
  recover.call(initial,false,{"CLIENT_FAIL"=>"1"})
  # 并发外部缩放只能由 JSON Patch test 拒绝，不能覆盖为原值。
  changed=Marshal.load(Marshal.dump(initial)); changed["spec"]["replicas"]=2
  File.write(fixture,JSON.generate(changed)); attempt=Dir.mktmpdir("concurrent-",dir)
  _,status=Open3.capture2e(env,"bash",File.join(root,"lib/recover.sh"),input_path,snapshot,attempt,"0")
  abort "并发副本被覆盖" if status.success? || JSON.parse(File.read(fixture)).dig("spec","replicas")!=2
  count+=1
  (1..9).each do |stage|
    File.write(calls,"")
    _,status=Open3.capture2e(env,"bash",File.join(root,format("%02d",stage),"run.sh"),"invalid-offline-action")
    abort "非法动作应在客户端调用前失败" if status.success? || !File.read(calls).empty?
    count+=1
  end
  output=File.join(dir,"results"); Dir.mkdir(output)
  script='source "$1"; P05="$2"; start 09 guard; RECOVERY_FUNCTION=false; exit 17'
  _,status=Open3.capture2e(env,"bash","-c",script,"_",File.join(root,"lib/common.sh"),output)
  result=JSON.parse(File.read(Dir.glob(File.join(output,"09/records/offline-review/*/result.json")).fetch(0)))
  abort "原失败码被恢复失败覆盖" unless status.exitstatus==17 && result["exit_code"]==17 && result["recovery_failed"]==true && result["phase_complete"]==false
  count+=1
  # 条件调用不能绕过秘密权限/配置/内部 URL 检查。
  config=File.join(dir,"curl.conf")
  [[0644,"header = \"X-Test: fixture\"\n","https://grafana.k8s.internal.egon.top"],[0600,"insecure\n","https://grafana.k8s.internal.egon.top"],[0600,"header = \"X-Test: fixture\"\n","https://public.invalid"]].each do |mode,content,url|
    File.write(config,content); File.chmod(mode,config); File.write(calls,"")
    script='source "$1"; value=$(http "$2" "$3") || exit 99'
    _,status=Open3.capture2e(env,"bash","-c",script,"_",File.join(root,"lib/common.sh"),config,url)
    abort "条件调用绕过 HTTP 防护" unless status.exitstatus==99 && File.read(calls).empty?
    count+=1
  end
end
puts "PASS #{count} 项本地客户端替身防护/恢复检查；真实 kubectl/网络调用为零"
