#!/usr/bin/env ruby
require_relative "../lib/config"
mode = ARGV[0] || "cpu"
items = base
case mode
when "cpu"
  runtime = required("ai","runtime_name")
  c = container("kserve-container",image("sklearn"))
  c["args"] = ["--model_name={{.Name}}","--model_dir=/mnt/models","--http_port=8080"]
  serving = object("serving.kserve.io/v1alpha1","ServingRuntime",runtime,{"supportedModelFormats"=>[{"name"=>"sklearn","version"=>"1","autoSelect"=>false}],"protocolVersions"=>["v1"],"containers"=>[c]})
  service = object("serving.kserve.io/v1beta1","InferenceService","cpu-model",{"predictor"=>{"serviceAccountName"=>"app","minReplicas"=>1,"maxReplicas"=>2,"model"=>{"runtime"=>runtime,"modelFormat"=>{"name"=>"sklearn"},"storageUri"=>required("ai","storage_uri")}}})
  deploy_mode = required("ai","deployment_mode")
  abort "CPU 首例选择已支持的普通 Deployment 模式" unless %w[RawDeployment Standard].include?(deploy_mode)
  service["metadata"]["annotations"] = {"serving.kserve.io/deploymentMode"=>deploy_mode}
  items.find { |d| d["kind"] == "ServiceAccount" }["secrets"] = [{"name"=>required("ai","model_secret")}]
  items += [serving,service]
when "vllm"
  length = required("ai","max_model_len"); fraction = required("ai","gpu_memory_utilization")
  abort "模型长度/显存预算无效" unless length.is_a?(Integer) && (128..4096).include?(length) && fraction.is_a?(Numeric) && fraction>0 && fraction<=0.8
  app = deployment("vllm","vllm",1)
  pod = app["spec"]["template"]["spec"]
  pod["nodeSelector"] = {"kubernetes.io/hostname"=>required("gpu","node")}
  pod["volumes"] = [{"name"=>"models","persistentVolumeClaim"=>{"claimName"=>required("ai","model_pvc"),"readOnly"=>true}},{"name"=>"cache","emptyDir"=>{"sizeLimit"=>"1Gi"}},{"name"=>"shm","emptyDir"=>{"medium"=>"Memory","sizeLimit"=>"512Mi"}}]
  c = pod["containers"][0]
  c["command"] = ["vllm","serve","/models"]
  c["args"] = ["--host","0.0.0.0","--port","8000","--served-model-name",required("ai","model_name"),"--max-model-len",length.to_s,"--gpu-memory-utilization",fraction.to_s,"--disable-log-requests"]
  c["ports"] = [{"containerPort"=>8000}]
  c["env"] = [{"name"=>"HF_HUB_OFFLINE","value"=>"1"},{"name"=>"TRANSFORMERS_OFFLINE","value"=>"1"},{"name"=>"HF_HOME","value"=>"/tmp/hf"},{"name"=>"VLLM_CACHE_ROOT","value"=>"/tmp/vllm"}]
  c["volumeMounts"] = [{"name"=>"models","mountPath"=>"/models","readOnly"=>true},{"name"=>"cache","mountPath"=>"/tmp"},{"name"=>"shm","mountPath"=>"/dev/shm"}]
  c["resources"] = {"requests"=>{"cpu"=>"1","memory"=>"2Gi","nvidia.com/gpu"=>1},"limits"=>{"cpu"=>"2","memory"=>"4Gi","nvidia.com/gpu"=>1}}
  c["readinessProbe"]["httpGet"]["port"] = 8000
  c["livenessProbe"]["httpGet"]["port"] = 8000
  c["startupProbe"] = {"httpGet"=>{"path"=>"/health","port"=>8000},"periodSeconds"=>5,"failureThreshold"=>60}
  svc = service("vllm"); svc["spec"]["ports"] = [{"port"=>8000,"targetPort"=>8000}]
  items += [app,svc]
when "training"
  # 训练与 08 使用同一个受限队列，不竞争 GPU 在线推理。
  items << object("kueue.x-k8s.io/v1beta1","LocalQueue","training",{"clusterQueue"=>"cnpl06-#{run}-cpu"})
  items << object("v1","PersistentVolumeClaim","training-artifacts",{"accessModes"=>["ReadWriteOnce"],"storageClassName"=>required("ai","storage_class"),"resources"=>{"requests"=>{"storage"=>"1Gi"}}})
  task = job("cpu-training",["python3","-c","import json,pathlib; x=list(range(10)); y=[2*v+1 for v in x]; n=len(x); w=(n*sum(a*b for a,b in zip(x,y))-sum(x)*sum(y))/(n*sum(a*a for a in x)-sum(x)**2); b=(sum(y)-w*sum(x))/n; assert w==2 and b==1; pathlib.Path('/artifacts/model.json').write_text(json.dumps({'weight':w,'bias':b})); print('training-ok')"])
  task["metadata"]["labels"]["kueue.x-k8s.io/queue-name"] = "training"
  task["spec"]["suspend"] = true
  pod = task["spec"]["template"]["spec"]
  pod["volumes"] = [{"name"=>"artifacts","persistentVolumeClaim"=>{"claimName"=>"training-artifacts"}}]
  pod["containers"][0]["volumeMounts"] = [{"name"=>"artifacts","mountPath"=>"/artifacts"}]
  pod["containers"][0]["resources"] = {"requests"=>{"cpu"=>"1","memory"=>"256Mi"},"limits"=>{"cpu"=>"1","memory"=>"256Mi"}}
  items << task
else abort "只支持 cpu/vllm/training"
end
emit(items)
