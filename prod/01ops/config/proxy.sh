export http_proxy=http://192.168.9.10:7890
export https_proxy=http://192.168.9.10:7890
export HTTP_PROXY="$http_proxy"
export HTTPS_PROXY="$https_proxy"
export no_proxy=localhost,127.0.0.1,::1,192.168.9.0/24,10.244.0.0/16,192.168.20.0/24,.internal.egon.top,.cluster.local
export NO_PROXY="$no_proxy"
