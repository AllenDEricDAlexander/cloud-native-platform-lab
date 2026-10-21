#!/usr/bin/env ruby
require_relative "../lib/config"
items = base
redis = required("dapr","redis_host")
secret = required("dapr","redis_secret")
%w[state pubsub].each do |kind|
  component = object("dapr.io/v1alpha1","Component","lab-#{kind}",{"type"=>"#{kind}.redis","version"=>"v1","metadata"=>[{"name"=>"redisHost","value"=>redis},{"name"=>"redisPassword","secretKeyRef"=>{"name"=>secret,"key"=>"password"}},{"name"=>"enableTLS","value"=>"true"}]})
  component["auth"] = {"secretStore"=>"kubernetes"}
  component["scopes"] = ["orders-python","orders-java"]
  items << component
end
config = object("dapr.io/v1alpha1","Configuration","bounded-apps",{"tracing"=>{"samplingRate"=>"1"},"secrets"=>{"scopes"=>[{"storeName"=>"kubernetes","defaultAccess"=>"deny","allowedSecrets"=>[secret]}]},"accessControl"=>{"defaultAction"=>"deny","trustDomain"=>"public","policies"=>[{"appId"=>"orders-python","defaultAction"=>"allow","trustDomain"=>"public","namespace"=>namespace},{"appId"=>"orders-java","defaultAction"=>"allow","trustDomain"=>"public","namespace"=>namespace}]}})
items << config
%w[python java].each do |language|
  name = "orders-#{language}"
  app = deployment(name,"worker",1)
  app["spec"]["template"]["metadata"]["annotations"] = {"dapr.io/enabled"=>"true","dapr.io/app-id"=>name,"dapr.io/app-port"=>"8080","dapr.io/app-protocol"=>"http","dapr.io/config"=>"bounded-apps","dapr.io/sidecar-cpu-request"=>"100m","dapr.io/sidecar-memory-request"=>"128Mi","dapr.io/sidecar-cpu-limit"=>"500m","dapr.io/sidecar-memory-limit"=>"256Mi","dapr.io/enable-api-logging"=>"false"}
  app["spec"]["template"]["spec"]["containers"][0]["args"] = ["serve","--language",language,"--backend","dapr","--run-id",run]
  # 短期 Sentry 身份由锁定 injector 注入；check 核对实际 sidecar 投影，应用仍不自动挂载 API Token。
  items << app
  items << service(name)
end
emit(items)
