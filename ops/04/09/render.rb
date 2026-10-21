#!/usr/bin/env ruby
require_relative "../lib/config"
mode=ARGV.fetch(0,"crossplane")
case mode
when "template"
  revision=required("repositories","template_revision")
  abort "平台模板固定SHA" unless revision.match?(/\A[a-f0-9]{40}\z/)
  platform=required("repositories","platform")
  project=platform.sub(%r{\Ahttps://gitlab\.svc\.internal\.egon\.top/},"").sub(/\.git\z/,"")
  gitops=required("repositories","gitops")
  path=gitops.sub(%r{\Ahttps://gitlab\.svc\.internal\.egon\.top/},"").sub(/\.git\z/,"")
  owner,repo=path.split("/")[0...-1].join("/"),path.split("/").last
  text=File.read(File.join(__dir__,"template.yaml")).gsub("__TEMPLATE_REVISION__",revision).gsub("__PLATFORM_SOURCE_URL__",platform.sub(/\.git\z/,"")+"/-/tree/#{revision}/ops/04").gsub("__PLATFORM_PROJECT__",project).gsub("__GITOPS_URL__",gitops).gsub("__GITOPS_REPO_LOCATOR__","gitlab.svc.internal.egon.top?owner=#{owner}&repo=#{repo}")
  abort "模板未填完整" if text.include?("__")
  documents(text)
  puts text
when "crossplane"
  schema={"type"=>"object","properties"=>{"spec"=>{"type"=>"object","required"=>["parameters"],"properties"=>{"parameters"=>{"type"=>"object","required"=>["serviceName","language","dataService"],"properties"=>{"serviceName"=>{"type"=>"string","pattern"=>"^[a-z][a-z0-9-]{2,30}$"},"language"=>{"type"=>"string","enum"=>%w[java rust c cpp csharp jsts python]},"dataService"=>{"type"=>"string","enum"=>%w[none postgresql]}}}}}}}
  xrd={"apiVersion"=>"apiextensions.crossplane.io/v1","kind"=>"CompositeResourceDefinition","metadata"=>{"name"=>"devapplications.platform.egon.top"},"spec"=>{"scope"=>"Namespaced","group"=>"platform.egon.top","names"=>{"kind"=>"DevApplication","plural"=>"devapplications"},"defaultCompositionRef"=>{"name"=>"cnpl04-service-v1"},"defaultCompositionUpdatePolicy"=>"Manual","versions"=>[{"name"=>"v1alpha1","served"=>true,"referenceable"=>true,"schema"=>{"openAPIV3Schema"=>schema}}]}}
  function={"apiVersion"=>"pkg.crossplane.io/v1beta1","kind"=>"Function","metadata"=>{"name"=>"function-go-templating"},"spec"=>{"package"=>digest_image(required("render_images","crossplane_function"))}}
  template=File.read(File.join(__dir__,"composition.gotmpl")).gsub("__STORAGE_CLASS__",required("build","storage_class")).gsub("__POSTGRES_IMAGE__",digest_image(required("render_images","postgresql_cnpg")))
  composition={"apiVersion"=>"apiextensions.crossplane.io/v1","kind"=>"Composition","metadata"=>{"name"=>"cnpl04-service-v1"},"spec"=>{"compositeTypeRef"=>{"apiVersion"=>"platform.egon.top/v1alpha1","kind"=>"DevApplication"},"mode"=>"Pipeline","pipeline"=>[{"step"=>"service-resources","functionRef"=>{"name"=>"function-go-templating"},"input"=>{"apiVersion"=>"gotemplating.fn.crossplane.io/v1beta1","kind"=>"GoTemplate","source"=>"Inline","inline"=>{"template"=>template}}}]}}
  puts JSON.pretty_generate(label([xrd,function,composition]))
when "catalog-root"
  repo=required("repositories","gitops")
  project={"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"AppProject","metadata"=>{"name"=>"cnpl04-catalog","namespace"=>"argocd"},"spec"=>{"sourceRepos"=>[repo],"destinations"=>[{"server"=>"https://kubernetes.default.svc","namespace"=>"argocd"}],"clusterResourceWhitelist"=>[],"namespaceResourceWhitelist"=>[{"group"=>"argoproj.io","kind"=>"Application"}]}}
  app={"apiVersion"=>"argoproj.io/v1alpha1","kind"=>"Application","metadata"=>{"name"=>"cnpl04-service-catalog","namespace"=>"argocd"},"spec"=>{"project"=>"cnpl04-catalog","source"=>{"repoURL"=>repo,"targetRevision"=>required("gitops","revision"),"path"=>"platform/apps","directory"=>{"recurse"=>false}},"destination"=>{"server"=>"https://kubernetes.default.svc","namespace"=>"argocd"},"syncPolicy"=>{"automated"=>{"prune"=>false,"selfHeal"=>true}}}}
  puts JSON.pretty_generate(label([project,app]))
else abort "未知渲染模式"
end
