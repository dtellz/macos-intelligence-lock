#!/bin/bash
#
# apple-pcc-block.sh
#
# Purpose:
#   Locally block Apple's currently published Private Cloud Compute (PCC)
#   hostnames while leaving the on-device Foundation Model available.
#
# Source checked 2026-09-16:
#   Apple Support: "Use Apple products on enterprise networks"
#   https://support.apple.com/101555
#
# Apple currently documents these as Private Cloud Compute endpoints:
#   apple-relay.cloudflare.com      TCP/UDP 443
#   apple-relay.fastly-edge.com    TCP/UDP 443
#   cp4.cloudflare.com              TCP/UDP 443
#
# This script deliberately DOES NOT block:
#   apple-relay.apple.com           Apple Intelligence Extensions
#   guzzoni.apple.com               Siri / dictation
#   *.smoot.apple.com               Search / Spotlight / Lookup etc.
#
# Commands:
#   ./apple-pcc-block.sh status
#   ./apple-pcc-block.sh enable
#   ./apple-pcc-block.sh disable
#   ./apple-pcc-block.sh show
#
# Notes:
# - "enable" and "disable" require sudo and create a timestamped backup.
# - This is an auditable hostname-resolution block, not a mathematically
#   absolute firewall guarantee. Apple could add/change endpoints later.
# - Any Apple feature that specifically requests PCC may fail or fall back.
#

set -euo pipefail

HOSTS_FILE="/etc/hosts"
BEGIN_MARKER="# >>> APPLE PRIVATE CLOUD COMPUTE BLOCK >>>"
END_MARKER="# <<< APPLE PRIVATE CLOUD COMPUTE BLOCK <<<"

PCC_HOSTS=(
  "apple-relay.cloudflare.com"
  "apple-relay.fastly-edge.com"
  "cp4.cloudflare.com"
)

usage() {
  cat <<'EOF'
Usage:
  apple-pcc-block.sh enable    Install/update the PCC hostname block
  apple-pcc-block.sh disable   Remove only the block managed by this script
  apple-pcc-block.sh status    Show whether the managed block is installed
  apple-pcc-block.sh show      Show the exact block this script would install
EOF
}

print_block() {
  echo "$BEGIN_MARKER"
  echo "# Managed by apple-pcc-block.sh"
  echo "# Apple-published Private Cloud Compute endpoints."
  for host in "${PCC_HOSTS[@]}"; do
    printf "0.0.0.0\t%s\n" "$host"
    printf "::\t%s\n" "$host"
  done
  echo "$END_MARKER"
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    exec sudo -- "$0" "$@"
  fi
}

strip_managed_block() {
  # Copy stdin to stdout, excluding the exact managed marker block.
  awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
    $0 == begin { inblock=1; next }
    $0 == end   { inblock=0; next }
    !inblock    { print }
  '
}

backup_hosts() {
  local backup
  backup="${HOSTS_FILE}.before-pcc-block.$(date '+%Y%m%d-%H%M%S')"
  cp -p "$HOSTS_FILE" "$backup"
  echo "Backup: $backup"
}

flush_dns() {
  /usr/bin/dscacheutil -flushcache 2>/dev/null || true
  /usr/bin/killall -HUP mDNSResponder 2>/dev/null || true
}

enable_block() {
  require_root enable

  local tmp
  tmp="$(mktemp /tmp/apple-pcc-hosts.XXXXXX)"
  # Capture and shell-quote the path now; the EXIT trap outlives local tmp.
  trap "$(printf 'rm -f -- %q' "$tmp")" EXIT

  backup_hosts

  {
    strip_managed_block < "$HOSTS_FILE"
    echo
    print_block
  } > "$tmp"

  cat "$tmp" > "$HOSTS_FILE"
  chmod 644 "$HOSTS_FILE"
  flush_dns

  echo
  echo "PCC hostname block enabled."
  status_block
}

disable_block() {
  require_root disable

  local tmp
  tmp="$(mktemp /tmp/apple-pcc-hosts.XXXXXX)"
  # Capture and shell-quote the path now; the EXIT trap outlives local tmp.
  trap "$(printf 'rm -f -- %q' "$tmp")" EXIT

  if ! grep -Fqx "$BEGIN_MARKER" "$HOSTS_FILE"; then
    echo "Managed PCC block is not present. Nothing to do."
    exit 0
  fi

  backup_hosts
  strip_managed_block < "$HOSTS_FILE" > "$tmp"
  cat "$tmp" > "$HOSTS_FILE"
  chmod 644 "$HOSTS_FILE"
  flush_dns

  echo
  echo "PCC hostname block disabled."
}

status_block() {
  echo
  if grep -Fqx "$BEGIN_MARKER" "$HOSTS_FILE" &&
     grep -Fqx "$END_MARKER" "$HOSTS_FILE"; then
    echo "Managed block: INSTALLED"
  else
    echo "Managed block: NOT INSTALLED"
  fi

  echo
  echo "Resolution seen by macOS:"
  local host
  for host in "${PCC_HOSTS[@]}"; do
    echo "--- $host"
    /usr/bin/dscacheutil -q host -a name "$host" 2>/dev/null || true
  done

  echo
  echo "Expected when enabled: addresses should resolve locally to"
  echo "0.0.0.0 and/or :: rather than a public Internet address."
}

case "${1:-}" in
  enable)
    enable_block
    ;;
  disable)
    disable_block
    ;;
  status)
    status_block
    ;;
  show)
    print_block
    ;;
  *)
    usage
    exit 2
    ;;
esac
