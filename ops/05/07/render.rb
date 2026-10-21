#!/usr/bin/env ruby
require_relative "../lib/config"
service = required("slo","service"); env = required("slo","environment")
abort "SLI 标签格式无效" unless [service,env].all? { |s| s.match?(/\A[a-zA-Z0-9_.-]+\z/) }
objective = required("slo","objective"); latency = required("slo","latency_seconds"); minimum = required("slo","min_requests")
abort "SLO/延迟/最小请求量无效" unless objective.is_a?(Numeric) && objective>0 && objective<1 && latency.is_a?(Numeric) && latency>0 && minimum.is_a?(Integer) && minimum>0
selector = "service=\"#{service}\",environment=\"#{env}\",outcome=~\"success|error\""
eligible = lambda { |window, extra=""| "sum(increase(cnpl_http_requests_total{#{selector}#{extra}}[#{window}]))" }
bad = lambda { |window| "sum(increase(cnpl_http_requests_total{service=\"#{service}\",environment=\"#{env}\",outcome=\"error\"}[#{window}]))" }
rules = []
%w[5m 30m 1h 6h].each do |w|
  rules << {"record"=>"cnpl05:slo_error_ratio:#{w}","labels"=>{"service"=>service,"environment"=>env},"expr"=>"(#{bad.call(w)} / #{eligible.call(w)}) and on() (#{eligible.call(w)} >= #{minimum})"}
  rules << {"record"=>"cnpl05:slo_burn:#{w}","labels"=>{"service"=>service,"environment"=>env},"expr"=>"cnpl05:slo_error_ratio:#{w}{service=\"#{service}\",environment=\"#{env}\"} / #{1-objective}"}
end
latency_total = "sum(increase(cnpl_http_request_duration_seconds_count{#{selector}}[5m]))"
rules << {"record"=>"cnpl05:slo_latency_good_ratio:5m","labels"=>{"service"=>service,"environment"=>env},"expr"=>"(sum(increase(cnpl_http_request_duration_seconds_bucket{#{selector},le=\"#{latency}\"}[5m])) / #{latency_total}) and on() (#{latency_total} >= #{minimum})"}
[["Fast", "1h","5m",14.4,"critical"],["Slow","6h","30m",6.0,"warning"]].each do |name,long,short,threshold,severity|
  rules << {"alert"=>"CNPL05BudgetBurn#{name}","expr"=>"(cnpl05:slo_burn:#{long}{service=\"#{service}\",environment=\"#{env}\"} > #{threshold}) and (cnpl05:slo_burn:#{short}{service=\"#{service}\",environment=\"#{env}\"} > #{threshold})","for"=>"2m","labels"=>{"severity"=>severity,"team"=>"application","service"=>service,"environment"=>env},"annotations"=>{"summary"=>"30-day SLO budget burn: #{name}"}}
end
rules << {"alert"=>"CNPL05SLOInsufficientData","expr"=>"absent(cnpl05:slo_error_ratio:5m{service=\"#{service}\",environment=\"#{env}\"})","for"=>"5m","labels"=>{"severity"=>"info","service"=>service,"environment"=>env,"team"=>"application"},"annotations"=>{"summary"=>"No valid SLI: inspect traffic, counter labels and telemetry; availability unknown"}}
if ARGV[0]=="rules"
  puts YAML.dump({"groups"=>[{"name"=>"cnpl05.slo","rules"=>rules}]}); exit
end
template = "cnpl05-#{required('run_id')}-slo"
version = required("slo","candidate_version")
abort "candidate_version 无效" unless version.match?(/\A[a-zA-Z0-9_.-]+\z/)
canary_selector = 'service="{{args.service}}",environment="{{args.environment}}",version="{{args.version}}",outcome=~"success|error"'
canary_count = "sum(increase(cnpl_http_requests_total{#{canary_selector}}[5m]))"
ratio = "(sum(increase(cnpl_http_requests_total{service=\"{{args.service}}\",environment=\"{{args.environment}}\",version=\"{{args.version}}\",outcome=\"success\"}[5m])) / #{canary_count}) and on() (#{canary_count} >= #{minimum})"
metrics = [{"name"=>"canary-success-rate","interval"=>"30s","count"=>5,"initialDelay"=>"30s","failureLimit"=>1,"consecutiveErrorLimit"=>1,"successCondition"=>"len(result) == 1 && !isNaN(result[0]) && result[0] >= #{objective}","failureCondition"=>"len(result) != 1 || isNaN(result[0]) || result[0] < #{objective}","provider"=>{"prometheus"=>{"address"=>required("metrics","url"),"query"=>ratio,"skipTLSVerify"=>false,"headers"=>[{"key"=>"Authorization","value"=>"Bearer {{args.prometheus-token}}"}]}}}]
latency_query = "histogram_quantile(0.95, sum by(le) (rate(cnpl_http_request_duration_seconds_bucket{#{canary_selector}}[5m]))) and on() (#{canary_count} >= #{minimum})"
latency_metric = Marshal.load(Marshal.dump(metrics[0])); latency_metric["name"]="canary-p95"; latency_metric["provider"]["prometheus"]["query"]=latency_query
latency_metric["successCondition"]="len(result) == 1 && !isNaN(result[0]) && result[0] <= #{latency}"
latency_metric["failureCondition"]="len(result) != 1 || isNaN(result[0]) || result[0] > #{latency}"
metrics << latency_metric
metrics[0]["successCondition"] += " && result[0] <= 1"
metrics[0]["failureCondition"] += " || result[0] > 1"
metrics[1]["successCondition"] += " && result[0] >= 0"
metrics[1]["failureCondition"] += " || result[0] < 0"
args = [{"name"=>"service","value"=>service},{"name"=>"environment","value"=>env},{"name"=>"version","value"=>version},{"name"=>"prometheus-token","valueFrom"=>{"secretKeyRef"=>{"name"=>required("slo","prometheus_secret"),"key"=>"token"}}}]
if ARGV[0]=="rollout-patch"
  puts JSON.pretty_generate({"spec"=>{"strategy"=>{"canary"=>{"analysis"=>{"templates"=>[{"templateName"=>template}],"args"=>args.reject { |a| a["name"]=="prometheus-token" }}}}}}); exit
end
items = [object("PrometheusRule","cnpl05-slo",required("namespaces","metrics"),{"spec"=>{"groups"=>[{"name"=>"cnpl05.slo","rules"=>rules}]}},"monitoring.coreos.com/v1"),object("AnalysisTemplate",template,required("slo","rollout_namespace"),{"spec"=>{"args"=>args,"metrics"=>metrics}},"argoproj.io/v1alpha1")]
puts JSON.pretty_generate(labeled(items))
