#!/usr/bin/env ruby
require_relative "../lib/config"
command = ["python3","-c","import torch; assert torch.cuda.is_available(); x=torch.arange(1000,device='cuda',dtype=torch.float32); assert x.sum().item()==499500; print('gpu-compute-ok')"]
task = job("gpu-smoke",command,"cuda")
spec = task["spec"]["template"]["spec"]
spec["nodeSelector"] = {"kubernetes.io/hostname"=>required("gpu","node")}
c = spec["containers"][0]
c["resources"] = {"requests"=>{"cpu"=>"500m","memory"=>"1Gi"},"limits"=>{"cpu"=>"1","memory"=>"2Gi"}}
items = base
if ARGV[0] == "dra"
  claim = object("resource.k8s.io/v1","ResourceClaim","gpu-claim",{"devices"=>{"requests"=>[{"name"=>"gpu","exactly"=>{"deviceClassName"=>required("gpu","device_class"),"allocationMode"=>"ExactCount","count"=>1}}]}})
  spec["resourceClaims"] = [{"name"=>"gpu","resourceClaimName"=>"gpu-claim"}]
  c["resources"]["claims"] = [{"name"=>"gpu"}]
  items << claim
else
  c["resources"]["requests"]["nvidia.com/gpu"] = 1
  c["resources"]["limits"]["nvidia.com/gpu"] = 1
end
emit(items+[task])
