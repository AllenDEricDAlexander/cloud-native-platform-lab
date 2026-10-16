#!/usr/bin/env python3
"""把 node-readiness 采集结果汇总为十节点矩阵（Markdown，输出到 stdout）。

只读取输入目录中的 <id>.expect（期望值，由 collect-node-readiness.sh 从台账与版本锁生成）
与 <id>.txt（节点只读检查输出）。不连接节点、不修改文件。

用法：python3 -I summarize-node-readiness.py <采集目录> > <采集目录>/matrix.md
退出码：0 全部通过；1 有未通过项、重复身份或缺失采集。
"""
import datetime
import pathlib
import sys

NETWORK_READY_NOTE = "00 未安装 CNI，NetworkReady=false 为阶段边界"


def load(path):
    data = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                data[key.strip()] = value.strip()
    return data


def bare(version):
    return version[1:] if version.startswith("v") else version


def to_int(value, default=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def checks(e, f):
    """返回 [(检查项, 是否通过, 实际值说明)]。"""
    mem_expect = to_int(e.get("expect_mem_gib")) * 1024
    mem = to_int(f.get("mem_mib"))
    ipv4s = [a for a in f.get("ipv4", "").split(",") if a]
    want_ip = f'{e.get("expect_ip")}/{e.get("expect_prefix")}'
    images = f.get("cri_images", "").split(",")
    versions = [
        ("containerd", "containerd_version", "expect_containerd"),
        ("runc", "runc_version", "expect_runc"),
        ("crictl", "crictl_version", "expect_crictl"),
        ("kubeadm", "kubeadm_version", "expect_kubeadm"),
        ("kubelet", "kubelet_version", "expect_kubelet"),
        ("kubectl", "kubectl_version", "expect_kubectl"),
    ]
    bad_versions = [
        f'{name}={f.get(got, "")}'
        for name, got, want in versions
        if bare(f.get(got, "")) != bare(e.get(want, ""))
    ]
    return [
        ("采集", f.get("schema") == "node-readiness/v1" and f.get("collect_exit") == "0",
         f'schema={f.get("schema", "无输出")} ssh_exit={f.get("collect_exit", "无")}'),
        ("主机名", f.get("hostname") == e.get("expect_fqdn"), f.get("hostname", "")),
        ("地址", ipv4s == [want_ip], f.get("ipv4", "")),
        ("静态配置", f.get("ipv4_method") == "manual", f.get("ipv4_method", "")),
        ("网关", f.get("gateway") == e.get("expect_gateway"), f.get("gateway", "")),
        ("vCPU", to_int(f.get("vcpu")) == to_int(e.get("expect_vcpu")), f.get("vcpu", "")),
        # MemTotal 扣除内核保留，约为配置值的九成以上，不会超过配置值。
        ("内存", 0.85 * mem_expect <= mem <= mem_expect, f'{mem} MiB'),
        ("VMXNET3", f.get("nic_driver") == "vmxnet3", f.get("nic_driver", "")),
        ("VMware Tools", f.get("vmtoolsd") == "active", f.get("vmtoolsd", "")),
        ("SELinux", f.get("selinux") == "Enforcing", f.get("selinux", "")),
        ("firewalld", f.get("firewalld") == "running", f.get("firewalld", "")),
        ("Swap", f.get("swap_active") == "0", f.get("swap_active", "")),
        ("cgroup v2", f.get("cgroup_fs") == "cgroup2fs", f.get("cgroup_fs", "")),
        ("内核参数", f.get("ip_forward") == "1" and to_int(f.get("overlay_loaded")) >= 1,
         f'ip_forward={f.get("ip_forward", "")} overlay={f.get("overlay_loaded", "")}'),
        ("时间同步", f.get("chrony_leap") == "Normal", f.get("chrony_leap", "")),
        ("运行时盘", f.get("runtime_mount_uuid") == e.get("expect_runtime_uuid")
         and f.get("runtime_mount_fstype") == "xfs",
         f'{f.get("runtime_mount_source", "")} {f.get("runtime_mount_fstype", "")}'),
        ("containerd", f.get("containerd_enabled") == "enabled" and f.get("containerd_active") == "active",
         f'{f.get("containerd_enabled", "")}/{f.get("containerd_active", "")}'),
        ("版本", not bad_versions, ", ".join(bad_versions) or "与版本锁一致"),
        ("RuntimeReady", f.get("runtime_ready") == "true", f.get("runtime_ready", "")),
        ("NetworkReady", f.get("network_ready") == "false", f'{f.get("network_ready", "")}（{NETWORK_READY_NOTE}）'),
        ("sandbox 镜像", e.get("expect_pause") in images, e.get("expect_pause", "")),
        ("kubelet 未启用", f.get("kubelet_enabled") == "disabled", f.get("kubelet_enabled", "")),
        ("无 CNI 配置", f.get("cni_netd_files") == "0", f.get("cni_netd_files", "")),
        ("无失败单元", f.get("failed_units") == "0", f.get("failed_unit_names") or f.get("failed_units", "")),
    ]


def main():
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    base = pathlib.Path(sys.argv[1])
    expects = sorted(base.glob("*.expect"))
    if not expects:
        print(f"{base} 中没有 .expect 文件", file=sys.stderr)
        return 2

    rows, facts, uncollected, failed = [], {}, [], False
    for exp_path in expects:
        node = exp_path.stem
        e, f = load(exp_path), load(base / f"{node}.txt")
        results = checks(e, f)
        collected, detail = results[0][1], results[0][2]
        if collected:
            facts[node] = f
            bad = [f"{name}（{d}）" for name, ok, d in results if not ok]
        else:
            # 未采集到完整输出时只报采集失败，其余检查没有意义。
            uncollected.append(node)
            bad = [f"采集（{detail}），其余检查未执行"]
        failed |= bool(bad)
        passed = len(results) - len(bad) if collected else 0
        rows.append((node, e.get("expect_ip", ""), passed, len(results), bad))

    unique_fields = [
        ("machine-id", "machine_id"), ("BIOS UUID", "product_uuid"), ("MAC", "mac"),
        ("SSH ED25519", "ssh_ed25519_fp"), ("主机名", "hostname"), ("IPv4", "ipv4"),
    ]
    uniq = []
    for label, key in unique_fields:
        seen = {}
        for node, f in facts.items():
            value = f.get(key, "")
            seen.setdefault(value, []).append(node)
        dups = {v: n for v, n in seen.items() if len(n) > 1 or not v}
        failed |= bool(dups)
        uniq.append((label, not dups, "; ".join(f'{v or "空值"}: {",".join(n)}' for v, n in dups.items())))

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    out = [
        "# Phase 00 节点 node-readiness 矩阵",
        "",
        f"采集目录：`{base.name}`；汇总时间：{now}；节点数：{len(rows)}。",
        "只读检查，期望值来自 hosts.yaml、resources.yaml、networks.yaml 与 versions.lock.yaml。",
        f"NetworkReady 期望为 false：{NETWORK_READY_NOTE}；普通 Pod 网络在 01 验收。",
        "",
        "## 结果",
        "",
        "| 节点 | IP | 通过 | 未通过项 |",
        "| --- | --- | --- | --- |",
    ]
    for node, ip, ok, total, bad in rows:
        out.append(f'| {node} | {ip} | {ok}/{total} | {"；".join(bad) or "—"} |')
    out += ["", "## 唯一性", ""]
    if uncollected:
        out += [f'未采集、未参与比对：{", ".join(uncollected)}。', ""]
    out += ["| 字段 | 结果 | 重复或空值 |", "| --- | --- | --- |"]
    for label, ok, detail in uniq:
        out.append(f'| {label} | {"唯一" if ok else "冲突"} | {detail or "—"} |')
    out += [
        "",
        "## 明细",
        "",
        "| 节点 | 主机名 | IPv4 | MAC | machine-id | BIOS UUID | vCPU | 内存 MiB | 磁盘 NAME:SIZE:HCTL | 运行时盘设备 | 采集时间 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for node, f in facts.items():
        out.append(
            f'| {node} | {f.get("hostname", "")} | {f.get("ipv4", "")} | {f.get("mac", "")} '
            f'| {f.get("machine_id", "")} | {f.get("product_uuid", "")} | {f.get("vcpu", "")} '
            f'| {f.get("mem_mib", "")} | {f.get("disks", "")} | {f.get("runtime_mount_source", "")} '
            f'| {f.get("collected_at", "")} |'
        )
    out += ["", f'总体：{"未通过" if failed else "全部通过"}', ""]
    print("\n".join(out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
