#!/usr/bin/env ruby
require_relative "../lib/config"
items = base+[deployment("resident"),service("resident"),deployment("dead-letter"),service("dead-letter")]
ksvc = object("serving.knative.dev/v1","Service","hello",{"template"=>{"metadata"=>{"labels"=>labels,"annotations"=>{"autoscaling.knative.dev/min-scale"=>"0","autoscaling.knative.dev/max-scale"=>"3"}},"spec"=>podspec([container("app",image("http"))]).merge("containerConcurrency"=>10)},"traffic"=>[{"latestRevision"=>true,"percent"=>100}]})
ksvc["spec"]["template"]["spec"]["containers"][0]["ports"] = [{"containerPort"=>8080}]
broker = object("eventing.knative.dev/v1","Broker","lab-broker",{"delivery"=>{"retry"=>3,"backoffPolicy"=>"exponential","backoffDelay"=>"PT1S","deadLetterSink"=>{"ref"=>{"apiVersion"=>"v1","kind"=>"Service","name"=>"dead-letter"}}}})
broker["metadata"]["annotations"] = {"eventing.knative.dev/broker.class"=>required("serverless","broker_class")}
trigger = object("eventing.knative.dev/v1","Trigger","orders",{"broker"=>"lab-broker","filter"=>{"attributes"=>{"type"=>"cnpl.lab"}},"subscriber"=>{"ref"=>{"apiVersion"=>"serving.knative.dev/v1","kind"=>"Service","name"=>"hello"}}})
emit(items+[ksvc,broker,trigger])
