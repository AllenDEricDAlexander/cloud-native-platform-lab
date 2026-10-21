#!/usr/bin/env ruby
require "fileutils"
require_relative "../lib/config"
lang, destination = ARGV
abort "用法 export.rb <language> <仓库外全新目录>" unless %w[java rust c cpp csharp jsts python].include?(lang) && destination && destination.start_with?("/")
abort "目标已存在或在仓库worktree内" if File.exist?(destination) || !outside_repository?(destination)
FileUtils.mkdir_p(destination)
FileUtils.mkdir_p(File.join(destination,"ops/04"))
Dir.glob(File.join(ROOT,"**","*"),File::FNM_DOTMATCH).each do |source|
  relative=source.sub(ROOT+"/","")
  next if relative.split("/").any? { |p| %w[. .. records build build-sanitize target node_modules dist bin obj .venv __pycache__].include?(p) }
  abort "源码导出拒绝软链" if File.symlink?(source)
  target=File.join(destination,"ops/04",relative)
  if File.directory?(source) then FileUtils.mkdir_p(target)
  else FileUtils.cp(source,target)
  end
end
revision=required("repositories","template_revision")
abort "模板需固定完整 SHA" unless revision.match?(/\A[a-f0-9]{40}\z/)
project=required("repositories","platform").sub(%r{\Ahttps://gitlab\.svc\.internal\.egon\.top/},"").sub(/\.git\z/,"")
abort "平台仓库格式无效" unless project.match?(%r{\A[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)+\z})
ci={"include"=>[{"project"=>project,"ref"=>revision,"file"=>"/ops/04/03/gitlab-ci.yml"}],"variables"=>{"LANGUAGE"=>lang,"SOURCE_DIR"=>"ops/04/05/examples/#{lang}"}}
File.write(File.join(destination,".gitlab-ci.yml"),YAML.dump(ci))
%w[verify release].each do |kind|
  text=File.read(File.join(ROOT,"04/Jenkinsfile.#{kind}")).gsub("__LANGUAGE__",lang).gsub("__TEMPLATE_REVISION__",revision).gsub("__SOURCE_URL__",required("repositories","source"))
  File.write(File.join(destination,kind=="verify" ? "Jenkinsfile" : "Jenkinsfile.release"),text)
end
File.write(File.join(destination,"README.md"),"# #{lang} 交付样例\n\n工具链和凭据由受控 CI 配置。源码位于 ops/04/05/examples/#{lang}。普通 Jenkinsfile 只验证；release 从受信平台任务加载。\n")
puts "已导出源码；未创建远端仓库、提交、推送或触发 CI：#{destination}"
