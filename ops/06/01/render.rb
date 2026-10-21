#!/usr/bin/env ruby
require_relative "../lib/config"
items = base
role = object("rbac.authorization.k8s.io/v1","Role","pod-reader").merge("rules"=>[{"apiGroups"=>[""],"resources"=>["pods","pods/log"],"verbs"=>["get","list","watch"]}])
binding = object("rbac.authorization.k8s.io/v1","RoleBinding","developers-read").merge("subjects"=>[{"kind"=>"Group","name"=>required("identity","group"),"apiGroup"=>"rbac.authorization.k8s.io"}],"roleRef"=>{"kind"=>"Role","name"=>"pod-reader","apiGroup"=>"rbac.authorization.k8s.io"})
items += [role,binding,deployment("identity-demo"),service("identity-demo")]
emit(items)
