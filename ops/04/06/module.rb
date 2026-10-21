#!/usr/bin/env ruby
# 仅生成 JSON 格式 OpenTofu 模块，不调用 Provider 或 vCenter。
require_relative "../lib/config"
directory=ARGV.fetch(0)
abort "模块目标必须为仓库外新目录" unless directory.start_with?("/") && !File.exist?(directory) && !File.expand_path(directory).start_with?(REPO+"/")
provider=required("iac","provider_source")
version=required("iac","provider_version")
abort "Provider 来源/固定版本无效" unless provider.match?(%r{\A[a-zA-Z0-9.-]+/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+\z}) && version.match?(/\A\d+\.\d+\.\d+\z/)
variables={}
%w[vsphere_server vsphere_user vsphere_password datacenter datastore resource_pool network template vm_name test_ip netmask gateway].each { |k| variables[k]={"type"=>"string","sensitive"=>%w[vsphere_user vsphere_password].include?(k)} }
%w[cpus memory_mib runtime_disk_gib].each { |k| variables[k]={"type"=>"number"} }
data={}
%w[datacenter datastore resource_pool network].each do |kind|
  fields={"name"=>"${var.#{kind}}"}
  fields["datacenter_id"]="${data.vsphere_datacenter.target.id}" unless kind=="datacenter"
  data["vsphere_#{kind}"]={"target"=>fields}
end
data["vsphere_virtual_machine"]={"template"=>{"name"=>"${var.template}","datacenter_id"=>"${data.vsphere_datacenter.target.id}"}}
vm={"name"=>"${var.vm_name}","resource_pool_id"=>"${data.vsphere_resource_pool.target.id}","datastore_id"=>"${data.vsphere_datastore.target.id}","num_cpus"=>"${var.cpus}","memory"=>"${var.memory_mib}","guest_id"=>"${data.vsphere_virtual_machine.template.guest_id}","scsi_type"=>"${data.vsphere_virtual_machine.template.scsi_type}","network_interface"=>[{"network_id"=>"${data.vsphere_network.target.id}","adapter_type"=>"vmxnet3"}],"disk"=>[{"label"=>"os","size"=>"${data.vsphere_virtual_machine.template.disks[0].size}","thin_provisioned"=>true},{"label"=>"runtime","size"=>"${var.runtime_disk_gib}","unit_number"=>1,"thin_provisioned"=>true}],"clone"=>{"template_uuid"=>"${data.vsphere_virtual_machine.template.id}","customize"=>{"linux_options"=>{"host_name"=>"${var.vm_name}","domain"=>"svc.internal.egon.top"},"network_interface"=>[{"ipv4_address"=>"${var.test_ip}","ipv4_netmask"=>"${var.netmask}"}],"ipv4_gateway"=>"${var.gateway}"}},"lifecycle"=>{"prevent_destroy"=>true}}
module_data={"terraform"=>{"required_providers"=>{"vsphere"=>{"source"=>provider,"version"=>"= #{version}"}},"backend"=>{"http"=>{}}},"provider"=>{"vsphere"=>{"user"=>"${var.vsphere_user}","password"=>"${var.vsphere_password}","vsphere_server"=>"${var.vsphere_server}","allow_unverified_ssl"=>false}},"variable"=>variables,"data"=>data,"resource"=>{"vsphere_virtual_machine"=>{"test"=>vm}},"output"=>{"test_ip"=>{"value"=>"${var.test_ip}"},"test_id"=>{"value"=>"${vsphere_virtual_machine.test.id}"}}}
Dir.mkdir(directory,0700)
File.write(File.join(directory,"main.tf.json"),JSON.pretty_generate(module_data)+"\n")
puts "已生成受保护测试 VM 模块；未 init/plan/apply"
