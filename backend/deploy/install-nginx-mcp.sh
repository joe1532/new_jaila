#!/usr/bin/env sh
set -eu

SOURCE_SNIPPET="${1:-/home/maestro/nginx-mcp-snippet.conf}"
TARGET_SNIPPET="/etc/nginx/snippets/jaila_mcp_proxy.conf"
SITE_FILE="/etc/nginx/sites-enabled/site"
INCLUDE_LINE="    include /etc/nginx/snippets/jaila_mcp_proxy.conf;"
ANCHOR="    include /etc/nginx/snippets/backend_api_proxy.conf;"

test -f "$SOURCE_SNIPPET"
test -f "$SITE_FILE"

install -o root -g root -m 644 "$SOURCE_SNIPPET" "$TARGET_SNIPPET"

if ! awk '/jaila_mcp_proxy[.]conf/ { found=1 } END { exit(found ? 0 : 1) }' "$SITE_FILE"; then
    backup="${SITE_FILE}.before-mcp"
    cp -p "$SITE_FILE" "$backup"

    awk -v anchor="$ANCHOR" -v include_line="$INCLUDE_LINE" '
        { print }
        $0 == anchor {
            print include_line
            inserted=1
        }
        END {
            if (!inserted) {
                exit 42
            }
        }
    ' "$backup" > "$SITE_FILE"
fi

nginx -t
systemctl reload nginx
