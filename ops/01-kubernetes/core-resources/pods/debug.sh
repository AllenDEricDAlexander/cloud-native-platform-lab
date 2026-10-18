set -eu
wget -q -T 3 -O - http://127.0.0.1:18080/health
ps
ps | grep '[c]oredns' >/dev/null
nslookup -timeout=2 -retry=1 -type=A kubernetes.default.svc.cluster.local 192.168.20.10
if nslookup -timeout=2 -retry=1 -type=A absent.p04.invalid. 192.168.20.10; then exit 1; fi
if wget -q -T 2 -O - http://127.0.0.1:18082/; then exit 1; fi
if wget -q -T 1 -O - 'http://p04-entry:8080/cgi-bin/check?delay'; then exit 1; fi
wget -q -T 5 -O - 'http://p04-entry:8080/cgi-bin/check?delay'
echo DEBUG_COMPLETE
