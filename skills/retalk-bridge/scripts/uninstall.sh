#!/usr/bin/env bash
# uninstall.sh — remove the retalk bridge for the current user.
#
# Stops and removes the systemd user timer and service, removes only the
# bridge's hook entries from the Claude Code settings and ~/.codex/hooks.json
# (deleting hooks.json if install.sh created it and nothing else is left in it)
# and removes ~/.local/share/retalk-bridge/. The config and the state directory
# (which holds received message text) are kept unless --purge is given; --purge
# deletes the state directory only when it is the default
# ~/.local/state/retalk-bridge. Backups made by install.sh are never deleted.
#
# Usage: skills/retalk-bridge/scripts/uninstall.sh [--purge] [--dry-run]
# Environment: CLAUDE_SETTINGS, CODEX_HOME, RETALK_BRIDGE_CONFIG (as install.sh).
set -euo pipefail

purge=0 dry_run=0
for arg in "$@"; do
    case "$arg" in
        --purge) purge=1 ;;
        --dry-run) dry_run=1 ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "uninstall.sh: unknown argument $arg" >&2; exit 2 ;;
    esac
done

here="$(cd "$(dirname "$0")" && pwd)"
share="$HOME/.local/share/retalk-bridge"
config="${RETALK_BRIDGE_CONFIG:-$HOME/.config/retalk-bridge/config.json}"
claude_settings="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
codex_home="${CODEX_HOME:-$HOME/.codex}"
units="$HOME/.config/systemd/user"
bridge="$share/retalk_bridge.py"
[[ -f "$bridge" ]] || bridge="$here/retalk_bridge.py"

run() {
    if [[ "$dry_run" == 1 ]]; then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi
}

if [[ -f "$units/retalk-bridge.timer" ]]; then
    run systemctl --user disable --now retalk-bridge.timer || true
    run rm -f "$units/retalk-bridge.timer" "$units/retalk-bridge.service"
    run systemctl --user daemon-reload
fi
args=()
[[ -f "$claude_settings" ]] && args+=(--claude-settings "$claude_settings")
[[ -f "$codex_home/hooks.json" ]] && args+=(--codex-hooks "$codex_home/hooks.json")
if [[ ${#args[@]} -gt 0 ]]; then
    run python3 "$bridge" uninstall-hooks "${args[@]}"
fi
if [[ -f "$codex_home/hooks.json" && "$(tr -d ' \n' < "$codex_home/hooks.json")" == "{}" ]] \
    && grep -qxF "created $codex_home/hooks.json" "$share/install-manifest.txt" 2>/dev/null; then
    run rm -f "$codex_home/hooks.json"
fi
if [[ "$purge" == 1 ]]; then
    default_state="$HOME/.local/state/retalk-bridge"
    state="$(python3 -c 'import json,os,sys; c=json.load(open(sys.argv[1])); print(os.path.abspath(os.path.expanduser(c.get("state_dir","~/.local/state/retalk-bridge"))))' "$config" 2>/dev/null || echo "$default_state")"
    if [[ "$state" == "$default_state" ]]; then
        run rm -rf "$state"
    else
        echo "uninstall.sh: not deleting state_dir $state (only the default $default_state is purged); remove it yourself" >&2
    fi
    run rm -f "$config"
fi
run rm -rf "$share"
echo "retalk bridge removed. Backups (*.bak-retalk-bridge-*) were kept."
