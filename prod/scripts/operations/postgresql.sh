#!/usr/bin/env bash
source "$(dirname "$0")/../lib/common.sh"
root; expect_host nexus; need psql
mountpoint -q /srv/nexus || die 'Nexus 数据盘未挂载'
case "${1:-}" in
  init)
    [[ ! -e /var/lib/pgsql/data/PG_VERSION ]] || die '检测到默认目录中的数据库，先人工核对，不能新建第二套'
    install -d -o postgres -g postgres -m 0700 /srv/nexus/postgres
    fcontext '/srv/nexus/postgres(/.*)?' postgresql_db_t
    restorecon -RF /srv/nexus/postgres
    if [[ ! -f /srv/nexus/postgres/PG_VERSION ]]; then
        [[ -z $(find /srv/nexus/postgres -mindepth 1 -maxdepth 1 -print -quit) ]] || die 'PGDATA 非空且未初始化'
        sudo -u postgres /usr/bin/initdb -D /srv/nexus/postgres --encoding=UTF8 --locale=C.UTF-8 --auth-local=peer --auth-host=scram-sha-256
        CNPL_CHANGED=1
    fi
    expected=$(rpm -q --qf '%{VERSION}' postgresql-server | cut -d. -f1)
    [[ $(cat /srv/nexus/postgres/PG_VERSION) == "$expected" ]] || die 'PGDATA major 与已安装 RPM 不符'
    conf=$(mktemp); trap 'rm -f "$conf"' EXIT
    printf "listen_addresses = '127.0.0.1'\npassword_encryption = 'scram-sha-256'\nshared_buffers = '1GB'\nmax_connections = 120\n" > "$conf"
    put "$conf" /srv/nexus/postgres/cnpl.conf 0600; chown postgres:postgres /srv/nexus/postgres/cnpl.conf
    if ! grep -Fxq "include_if_exists = 'cnpl.conf'" /srv/nexus/postgres/postgresql.conf; then
        printf "\ninclude_if_exists = 'cnpl.conf'\n" >> /srv/nexus/postgres/postgresql.conf; CNPL_CHANGED=1
    fi
    if ! grep -Fxq 'host nexus nexus 127.0.0.1/32 scram-sha-256' /srv/nexus/postgres/pg_hba.conf; then
        printf '\nhost nexus nexus 127.0.0.1/32 scram-sha-256\n' >> /srv/nexus/postgres/pg_hba.conf; CNPL_CHANGED=1
    fi
    ;;
  database)
    exists=$(sudo -u postgres psql -XAt -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_roles WHERE rolname='nexus'")
    if [[ $exists == 0 ]]; then
        secret_hex /etc/cnpl/secrets/nexus-db.password
        password=$(cat /etc/cnpl/secrets/nexus-db.password)
        [[ $password =~ ^[0-9a-f]{64}$ ]] || die '密码格式异常'
        printf "CREATE ROLE nexus LOGIN PASSWORD '%s';\n" "$password" | sudo -u postgres psql -X -v ON_ERROR_STOP=1 >/dev/null
        unset password; CNPL_CHANGED=1
    else
        [[ -s /etc/cnpl/secrets/nexus-db.password ]] || die '已有角色缺少原连接秘密，停止而不自动改密码'
    fi
    [[ $(sudo -u postgres psql -XAt -c "SELECT rolsuper OR rolcreatedb OR rolcreaterole FROM pg_roles WHERE rolname='nexus'") == f ]] || die 'Nexus 数据库角色权限过大'
    if [[ $(sudo -u postgres psql -XAt -c "SELECT count(*) FROM pg_database WHERE datname='nexus'") == 0 ]]; then
        sudo -u postgres createdb -O nexus --encoding=UTF8 --template=template0 nexus; CNPL_CHANGED=1
    fi
    [[ $(sudo -u postgres psql -XAt -c "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='nexus'") == nexus ]] || die '数据库所有者不符'
    sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d nexus <<'SQL' >/dev/null
SET ROLE nexus;
CREATE SCHEMA IF NOT EXISTS nexus AUTHORIZATION nexus;
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA nexus;
SQL
    ;;
  env)
    [[ -s /etc/cnpl/secrets/nexus-db.password ]] || die '缺少连接秘密'
    temp=$(mktemp); trap 'rm -f "$temp"' EXIT; chmod 0600 "$temp"
    password=$(cat /etc/cnpl/secrets/nexus-db.password)
    [[ $password =~ ^[0-9a-f]{64}$ ]] || die '数据库密码格式异常'
    printf 'NEXUS_DATASTORE_NEXUS_JDBCURL=jdbc:postgresql://127.0.0.1:5432/nexus?currentSchema=nexus\nNEXUS_DATASTORE_NEXUS_USERNAME=nexus\nNEXUS_DATASTORE_NEXUS_PASSWORD=%s\nINSTALL4J_ADD_VM_PARAMS=-Xms4g -Xmx8g -XX:MaxDirectMemorySize=4g -Djava.util.prefs.userRoot=/nexus-data/javaprefs\n' "$password" > "$temp"
    unset password
    put "$temp" /etc/cnpl/secrets/nexus.env 0600
    ;;
  verify)
    [[ $(sudo -u postgres psql -XAt -d nexus -c 'SHOW listen_addresses') == 127.0.0.1 ]] || die '数据库监听错误'
    sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d nexus -c 'SELECT extname FROM pg_extension WHERE extname = '\''pg_trgm'\'';'
    ;;
  *) die '用法：postgresql.sh init|database|env|verify';;
esac
result
