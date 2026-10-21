#!/usr/bin/env ruby
require_relative "../lib/config"
items = base+[deployment("hpa-demo"),service("hpa-demo"),deployment("vpa-demo")]
hpa = object("autoscaling/v2","HorizontalPodAutoscaler","hpa-demo",{"scaleTargetRef"=>{"apiVersion"=>"apps/v1","kind"=>"Deployment","name"=>"hpa-demo"},"minReplicas"=>2,"maxReplicas"=>4,"behavior"=>{"scaleUp"=>{"stabilizationWindowSeconds"=>30},"scaleDown"=>{"stabilizationWindowSeconds"=>120}},"metrics"=>[{"type"=>"Resource","resource"=>{"name"=>"cpu","target"=>{"type"=>"Utilization","averageUtilization"=>60}}},{"type"=>"Pods","pods"=>{"metric"=>{"name"=>"lab_http_requests_per_second"},"target"=>{"type"=>"AverageValue","averageValue"=>"20"}}}]})
vpa = object("autoscaling.k8s.io/v1","VerticalPodAutoscaler","recommend-only",{"targetRef"=>{"apiVersion"=>"apps/v1","kind"=>"Deployment","name"=>"vpa-demo"},"updatePolicy"=>{"updateMode"=>"Off"},"resourcePolicy"=>{"containerPolicies"=>[{"containerName"=>"*","minAllowed"=>{"cpu"=>"50m","memory"=>"64Mi"},"maxAllowed"=>{"cpu"=>"1","memory"=>"512Mi"}}]}})
items += [hpa,vpa,object("policy/v1","PodDisruptionBudget","online-minimum",{"minAvailable"=>1,"selector"=>{"matchLabels"=>{"app"=>"hpa-demo"}}})]
partitions = required("scaling","kafka_partitions")
abort "Kafka 分区数须为 1-4" unless partitions.is_a?(Integer) && (1..4).include?(partitions)
%w[kafka rabbit].each do |kind|
  dep = deployment("#{kind}-worker","worker",1)
  c = dep["spec"]["template"]["spec"]["containers"][0]
  c["args"] = ["consume","--backend",kind,"--run-id",run]
  dep["spec"]["template"]["spec"]["volumes"] = [{"name"=>"connection","secret"=>{"secretName"=>required("scaling","#{kind}_auth_secret")}}]
  c["volumeMounts"] = [{"name"=>"connection","mountPath"=>"/var/run/connection","readOnly"=>true}]
  c["env"] = [{"name"=>"LAB_RUN_ID","value"=>run},{"name"=>"LAB_TOPIC_OR_QUEUE","value"=>required("scaling",kind == "kafka" ? "kafka_topic" : "rabbit_queue")}]
  c["env"] << {"name"=>"LAB_CONNECTION_DIRECTORY","value"=>"/var/run/connection"}
  items << dep
  secret = required("scaling","#{kind}_auth_secret")
  auth = object("keda.sh/v1alpha1","TriggerAuthentication","#{kind}-auth",{"secretTargetRef"=>kind == "kafka" ? [{"parameter"=>"username","name"=>secret,"key"=>"username"},{"parameter"=>"password","name"=>secret,"key"=>"password"},{"parameter"=>"ca","name"=>secret,"key"=>"ca.crt"}] : [{"parameter"=>"host","name"=>secret,"key"=>"uri"}]})
  metadata = if kind == "kafka"
    {"bootstrapServers"=>required("scaling","kafka_bootstrap"),"consumerGroup"=>required("scaling","kafka_group"),"topic"=>required("scaling","kafka_topic"),"lagThreshold"=>"10","activationLagThreshold"=>"0","offsetResetPolicy"=>"earliest","allowIdleConsumers"=>"false","tls"=>"enable","sasl"=>"scram_sha512"}
  else
    {"queueName"=>required("scaling","rabbit_queue"),"mode"=>"QueueLength","value"=>"5","activationValue"=>"0","protocol"=>"amqp"}
  end
  scaled = object("keda.sh/v1alpha1","ScaledObject","#{kind}-worker",{"scaleTargetRef"=>{"name"=>"#{kind}-worker"},"pollingInterval"=>15,"cooldownPeriod"=>120,"minReplicaCount"=>0,"maxReplicaCount"=>(kind == "kafka" ? partitions : 4),"advanced"=>{"horizontalPodAutoscalerConfig"=>{"behavior"=>{"scaleDown"=>{"stabilizationWindowSeconds"=>120}}}},"triggers"=>[{"type"=>(kind == "rabbit" ? "rabbitmq" : "kafka"),"metadata"=>metadata,"authenticationRef"=>{"name"=>"#{kind}-auth"}}]})
  items += [auth,scaled]
end
emit(items)
