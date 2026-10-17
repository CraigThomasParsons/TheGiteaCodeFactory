#!/usr/bin/env bash
# install.sh — install the retalk bridge for the current user.
#
# Copies retalk_bridge.py to ~/.local/share/retalk-bridge/, writes
# ~/.config/retalk-bridge/config.json if it does not exist yet, backs up the
# Claude Code settings and Codex config with a timestamp, merges the bridge's
# hook entries (other hooks are left alone), and with --watcher installs and
# starts a systemd user timer that runs `retalk_bridge.py tick` every minute.
# Running it again is safe: hook entries are replaced, never duplicated.
#
# Usage: skills/retalk-bridge/scripts/install.sh
#          --claude-identity DIR --claude-peer NAME
#          --codex-identity DIR --codex-peer NAME
#          [--hook-cwd DIR]... [--watcher] [--dry-run]
#   --claude-identity  retalk identity directory the Claude side reads and sends as
#   --claude-peer      the Codex identity's name in that identity's contacts
#   --codex-identity   retalk identity directory the Codex side reads and sends as
#   --codex-peer       the Claude identity's name in that identity's contacts
#   --hook-cwd DIR     a directory (and its subdirectories) where live sessions
#                      get messages through hooks; repeatable. None means hooks
#                      stay silent until you add directories to the config.
#   --watcher          install and start the systemd user timer (auto replies)
#   --dry-run          print what would change and change nothing
# Environment: CLAUDE_SETTINGS (default ~/.claude/settings.json),
#   CODEX_HOME (default ~/.codex), RETALK_BRIDGE_CONFIG.
# Undo with uninstall.sh (same directory).
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
skill="$(dirname "$here")"
claude_identity="" claude_peer="" codex_identity="" codex_peer=""
hook_cwds=() watcher=0 dry_run=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --claude-identity) claude_identity="$2"; shift ;;
        --claude-peer) claude_peer="$2"; shift ;;
        --codex-identity) codex_identity="$2"; shift ;;
        --codex-peer) codex_peer="$2"; shift ;;
        --hook-cwd) hook_cwds+=("$2"); shift ;;
        --watcher) watcher=1 ;;
        --dry-run) dry_run=1 ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "install.sh: unknown argument $1" >&2; exit 2 ;;
    esac
    shift
done

share="$HOME/.local/share/retalk-bridge"
config="${RETALK_BRIDGE_CONFIG:-$HOME/.config/retalk-bridge/config.json}"
claude_settings="${CLAUDE_SETTINGS:-$HOME/.claude/settings.json}"
codex_home="${CODEX_HOME:-$HOME/.codex}"
units="$HOME/.config/systemd/user"
stamp="$(date +%Y%m%d-%H%M%S)"
manifest="$share/install-manifest.txt"

if [[ ! -f "$config" ]]; then
    for name in claude_identity claude_peer codex_identity codex_peer; do
        [[ -n "${!name}" ]] || { echo "install.sh: --${name//_/-} is required for a first install" >&2; exit 2; }
    done
fi

run() {
    if [[ "$dry_run" == 1 ]]; then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi
}

backup() {
    local file="$1"
    if [[ -e "$file" ]]; then
        run cp -p -- "$file" "$file.bak-retalk-bridge-$stamp"
        [[ "$dry_run" == 1 ]] || echo "backup $file.bak-retalk-bridge-$stamp" >> "$manifest"
    fi
}

run mkdir -p "$share" "$(dirname "$config")"
[[ "$dry_run" == 1 ]] || echo "# retalk-bridge install $stamp" >> "$manifest"
run install -m 0755 "$here/retalk_bridge.py" "$share/retalk_bridge.py"
run install -m 0644 "$skill/SKILL.md" "$share/SKILL.md"

if [[ -f "$config" ]]; then
    echo "keeping existing $config"
else
    # A few lines of Python only to write JSON with correct quoting.
    run python3 - "$config" "$skill/templates/config.example.json" "$claude_identity" "$claude_peer" \
        "$codex_identity" "$codex_peer" "${hook_cwds[@]}" <<'PY'
import json, os, sys
path, template, ci, cp, xi, xp, *cwds = sys.argv[1:]
config = json.load(open(template))
config["sides"]["claude"].update(identity_dir=ci, peer=cp, hook_cwds=cwds)
config["sides"]["codex"].update(identity_dir=xi, peer=xp, hook_cwds=cwds)
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as out:
    json.dump(config, out, indent=2)
    out.write("\n")
print("wrote " + path)
PY
    [[ "$dry_run" == 1 ]] || echo "created $config" >> "$manifest"
fi

backup "$claude_settings"
backup "$codex_home/config.toml"
backup "$codex_home/hooks.json"
run python3 "$share/retalk_bridge.py" install-hooks --claude-settings "$claude_settings" \
    --codex-hooks "$codex_home/hooks.json" --command "python3 $share/retalk_bridge.py"
[[ "$dry_run" == 1 ]] || printf 'merged %s\nmerged %s\n' "$claude_settings" "$codex_home/hooks.json" >> "$manifest"

if [[ "$watcher" == 1 ]]; then
    run mkdir -p "$units"
    run install -m 0644 "$skill/templates/retalk-bridge.service" "$units/retalk-bridge.service"
    run install -m 0644 "$skill/templates/retalk-bridge.timer" "$units/retalk-bridge.timer"
    run systemctl --user daemon-reload
    run systemctl --user enable --now retalk-bridge.timer
    [[ "$dry_run" == 1 ]] || printf 'created %s\ncreated %s\n' "$units/retalk-bridge.service" "$units/retalk-bridge.timer" >> "$manifest"
fi

echo "retalk bridge installed. Codex asks you to trust new hooks once: run /hooks in Codex."
echo "Claude Code loads hooks when a session starts; restart open sessions to pick them up."
echo "Undo: bash $here/uninstall.sh"
