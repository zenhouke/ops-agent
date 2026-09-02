#!/bin/sh
set -eu

install -d -m 0700 /tmp/ops-agent-tls
install -m 0400 /run/tls/tls.crt /tmp/ops-agent-tls/tls.crt
install -m 0400 /run/tls/tls.key /tmp/ops-agent-tls/tls.key
chown -R 101:101 /tmp/ops-agent-tls
chown 101:101 /proc/self/fd/1 /proc/self/fd/2

exec su -s /bin/sh nginx -c 'exec /docker-entrypoint.sh nginx -g "daemon off;"'
