#!/bin/bash
# Cloudflare DDNS Updater for app.zamintwin.ai
# Updates the DNS A record when your public IP changes

# Load config from .env file
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/.env"

LOG_FILE="$SCRIPT_DIR/cloudflare-ddns.log"
IP_CACHE="/tmp/cloudflare-ddns-ip.txt"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

# Get current public IP
CURRENT_IP=$(curl -s --max-time 10 https://ifconfig.me || curl -s --max-time 10 https://api.ipify.org)

if [ -z "$CURRENT_IP" ]; then
    log "ERROR: Could not determine public IP"
    exit 1
fi

# Check if IP has changed (compare with cached IP)
if [ -f "$IP_CACHE" ]; then
    CACHED_IP=$(cat "$IP_CACHE")
    if [ "$CURRENT_IP" = "$CACHED_IP" ]; then
        # IP hasn't changed, nothing to do
        exit 0
    fi
fi

# Get the DNS record ID for app.zamintwin.ai
RECORD_INFO=$(curl -s --max-time 10 \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records?name=$CF_RECORD_NAME&type=A")

RECORD_ID=$(echo "$RECORD_INFO" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['result'][0]['id'])" 2>/dev/null)
OLD_IP=$(echo "$RECORD_INFO" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['result'][0]['content'])" 2>/dev/null)

if [ -z "$RECORD_ID" ]; then
    log "ERROR: Could not find DNS record for $CF_RECORD_NAME"
    exit 1
fi

# Update the DNS record
RESPONSE=$(curl -s --max-time 10 -X PUT \
    "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records/$RECORD_ID" \
    -H "Authorization: Bearer $CF_API_TOKEN" \
    -H "Content-Type: application/json" \
    --data "{\"type\":\"A\",\"name\":\"$CF_RECORD_NAME\",\"content\":\"$CURRENT_IP\",\"ttl\":60,\"proxied\":false}")

SUCCESS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['success'])" 2>/dev/null)

if [ "$SUCCESS" = "True" ]; then
    echo "$CURRENT_IP" > "$IP_CACHE"
    log "SUCCESS: Updated $CF_RECORD_NAME from $OLD_IP to $CURRENT_IP"
else
    log "ERROR: Failed to update DNS record. Response: $RESPONSE"
    exit 1
fi
