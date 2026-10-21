#!/usr/bin/env ruby
require_relative "../lib/config"
server = required("secrets","vault_server")
abort "Vault 必须为内网 HTTPS" unless server.match?(%r{\Ahttps://[a-z0-9.-]+\.internal\.egon\.top(?::\d+)?\z})
items = base
store = object("external-secrets.io/v1beta1","SecretStore","vault-lab",{"provider"=>{"vault"=>{"server"=>server,"path"=>required("secrets","vault_path"),"version"=>"v2","caProvider"=>{"type"=>"Secret","name"=>required("secrets","vault_ca_secret"),"key"=>required("secrets","vault_ca_key")},"auth"=>{"kubernetes"=>{"mountPath"=>"kubernetes","role"=>required("secrets","vault_role"),"serviceAccountRef"=>{"name"=>"app"}}}}}})
external = object("external-secrets.io/v1beta1","ExternalSecret","lab-reference",{"refreshInterval"=>"1m","secretStoreRef"=>{"name"=>"vault-lab","kind"=>"SecretStore"},"target"=>{"name"=>"lab-synced","creationPolicy"=>"Owner"},"data"=>[{"secretKey"=>"value","remoteRef"=>{"key"=>"cnpl06/#{run}/sample","property"=>"value"}}]})
emit(items+[store,external])
