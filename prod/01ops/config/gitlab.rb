# /etc/gitlab/gitlab.rb
external_url 'https://gitlab.svc.internal.egon.top'
letsencrypt['enable'] = false
nginx['listen_addresses'] = ['192.168.9.13']
nginx['listen_port'] = 443
nginx['listen_https'] = true
nginx['ssl_certificate'] = '/etc/gitlab/ssl/gitlab.svc.internal.egon.top.crt'
nginx['ssl_certificate_key'] = '/etc/gitlab/ssl/gitlab.svc.internal.egon.top.key'
nginx['redirect_http_to_https'] = false
gitlab_rails['gitlab_shell_ssh_port'] = 22
gitlab_rails['initial_root_password'] = File.read('/etc/cnpl/secrets/gitlab-root.password').strip
gitlab_rails['env'] = {
  'http_proxy' => 'http://192.168.9.10:7890',
  'https_proxy' => 'http://192.168.9.10:7890',
  'no_proxy' => 'localhost,127.0.0.1,::1,192.168.9.12,192.168.9.13,192.168.9.14,192.168.9.15,.internal.egon.top,.cluster.local'
}
gitlab_workhorse['env'] = {
  'http_proxy' => 'http://192.168.9.10:7890',
  'https_proxy' => 'http://192.168.9.10:7890',
  'no_proxy' => 'localhost,127.0.0.1,::1,192.168.9.12,192.168.9.13,192.168.9.14,192.168.9.15,.internal.egon.top,.cluster.local'
}
gitaly['env'] = {
  'http_proxy' => 'http://192.168.9.10:7890',
  'https_proxy' => 'http://192.168.9.10:7890',
  'no_proxy' => 'localhost,127.0.0.1,::1,192.168.9.12,192.168.9.13,192.168.9.14,192.168.9.15,.internal.egon.top,.cluster.local'
}
