#!/bin/bash
set -euo pipefail
iptables -N CNPL-HARBOR 2>/dev/null || iptables -S CNPL-HARBOR >/dev/null
iptables -F CNPL-HARBOR
iptables -A CNPL-HARBOR -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
for address in 10 11 12 13 14 15 16 17 160 101 102 103 104 105 106 107 108 109 110; do
    iptables -A CNPL-HARBOR -i ens33 -s "192.168.9.$address/32" -p tcp -m conntrack --ctorigdst 192.168.9.12 --ctorigdstport 443 -j RETURN
done
iptables -A CNPL-HARBOR -i ens33 -j DROP
for network in 172.30.0.0/16 172.31.0.0/24; do
    iptables -A CNPL-HARBOR -s "$network" -d 172.30.0.0/16 -j RETURN
    iptables -A CNPL-HARBOR -s "$network" -d 172.31.0.0/24 -j RETURN
    iptables -A CNPL-HARBOR -s "$network" -d 192.168.9.10/32 -p tcp --dport 7890 -j RETURN
    for dns in 192.168.9.11 192.168.9.17; do
        for protocol in tcp udp; do
            iptables -A CNPL-HARBOR -s "$network" -d "$dns/32" -p "$protocol" --dport 53 -j RETURN
        done
    done
    iptables -A CNPL-HARBOR -s "$network" -j DROP
done
iptables -A CNPL-HARBOR -j RETURN
iptables -C DOCKER-USER -j CNPL-HARBOR 2>/dev/null || iptables -I DOCKER-USER 1 -j CNPL-HARBOR
