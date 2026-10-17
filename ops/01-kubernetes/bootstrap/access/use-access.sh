# 以 source 加载；只切换本终端默认身份，不覆盖 ~/.kube/config 或修改 shell 启动文件。
if ! test -s "$HOME/.cnpl-secrets/access/lab-primary/mac.conf"; then
  printf '%s\n' '尚未生成 Mac 受限 kubeconfig，请先执行 configure-access.yml。' >&2
  return 1
fi
export KUBECONFIG="$HOME/.cnpl-secrets/access/lab-primary/mac.conf"
k() {
  "$HOME/.cnpl/bin/kubectl" --kubeconfig "$HOME/.cnpl-secrets/access/lab-primary/mac.conf" "$@"
}
k config use-context lab-primary-readonly
