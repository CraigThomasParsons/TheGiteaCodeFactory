#!/usr/bin/env bash
# setup-host-runner.sh — provision the factory-host Gitea Actions runner for the
# current user: a host-mode runner (jobs run directly as this account, no
# container) that serves templates/pr-review-trigger.yml. Other runners and their
# labels are left alone.
#
# Usage: scripts/setup-host-runner.sh COMMAND [options]
#   render    write the runner config and systemd user unit from
#             templates/host-runner/ (unchanged files are left as they are)
#   register  register with Gitea once; skips when the runner file already exists
#   enable    reload systemd user units and enable --now the runner service
#   doctor    read-only checks of the whole setup; exit 3 if anything needs fixing
# Options:
#   --instance URL      Gitea base URL, http(s):// (register)
#   --token-file PATH   file holding only the runner registration token, mode 600
#                       (register). The token is passed to gitea-runner by file or
#                       environment, never on a command line, and never printed.
#   --name NAME         runner name (default factory-host-<short hostname>)
#   --runner-bin PATH   gitea-runner executable (default: gitea-runner on PATH)
#   --dry-run           print what would change and change nothing
# Environment: XDG_CONFIG_HOME, XDG_STATE_HOME, FACTORY_HOST_RUNNER_CONFIG_DIR,
#   FACTORY_HOST_RUNNER_STATE_DIR.
# Exit status: 0 done or nothing to do, 2 bad arguments, 3 misconfiguration or
#   a failed write. Typical order: render, register, enable, doctor.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
templates="$(dirname "$here")/templates/host-runner"
label="factory-host:host"
service="gitea-runner-factory-host.service"

usage() { sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; }
die() { echo "setup-host-runner: $2" >&2; exit "$1"; }

command="${1:-}"
case "$command" in
    render|register|enable|doctor) shift ;;
    -h|--help) usage; exit 0 ;;
    "") usage >&2; exit 2 ;;
    *) die 2 "unknown command $command" ;;
esac

instance="" token_file="" name="" runner_bin="" dry_run=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --instance|--token-file|--name|--runner-bin)
            [[ $# -ge 2 && -n "$2" ]] || die 2 "$1 needs a value"
            case "$1" in
                --instance) instance="$2" ;;
                --token-file) token_file="$2" ;;
                --name) name="$2" ;;
                --runner-bin) runner_bin="$2" ;;
            esac
            shift ;;
        --dry-run) dry_run=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die 2 "unknown argument $1" ;;
    esac
    shift
done

[[ -n "${HOME:-}" && "$HOME" == /* ]] || die 3 "HOME must be an absolute path"
config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
config_dir="${FACTORY_HOST_RUNNER_CONFIG_DIR:-$config_home/factory-host-runner}"
state_dir="${FACTORY_HOST_RUNNER_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/factory-host-runner}"
unit_dir="$config_home/systemd/user"
config="$config_dir/config.yaml"
unit="$unit_dir/$service"
runner_file="$state_dir/.runner"
pr_trigger="$HOME/.local/bin/pr-trigger"

# Rendered paths land unquoted in a systemd unit and quoted in YAML.
for path in "$config_dir" "$state_dir" "$unit_dir"; do
    [[ "$path" =~ ^/[A-Za-z0-9._/+-]+$ ]] || die 3 "unsupported path (absolute, no spaces or quotes): $path"
done

find_runner() {
    if [[ -z "$runner_bin" ]]; then
        runner_bin="$(command -v gitea-runner || true)"
    elif [[ "$runner_bin" != */* ]]; then
        runner_bin="$(command -v "$runner_bin" || true)"
    fi
    [[ -n "$runner_bin" && -x "$runner_bin" && ! -d "$runner_bin" ]] || return 1
    runner_bin="$(cd "$(dirname "$runner_bin")" && pwd)/$(basename "$runner_bin")"
    [[ "$runner_bin" =~ ^/[A-Za-z0-9._/+-]+$ ]]
}

require_runner() {
    find_runner || die 3 "gitea-runner not found or unusable; install it or pass --runner-bin PATH"
}

mode_of() { stat -c '%a' -- "$1"; }

run() {
    if [[ "$dry_run" == 1 ]]; then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi
}

render_config() {
    local text
    text="$(<"$templates/config.example.yaml")"
    printf '%s\n' "${text//@STATE_DIR@/$state_dir}"
}

render_unit() {
    local text
    text="$(<"$templates/$service")"
    text="${text//@RUNNER_BIN@/$runner_bin}"
    text="${text//@CONFIG@/$config}"
    printf '%s\n' "${text//@STATE_DIR@/$state_dir}"
}

ensure_dir() {
    if [[ -d "$1" ]]; then return; fi
    run mkdir -p -m 700 -- "$1" || die 3 "cannot create $1"
}

# write_file DEST MODE CONTENT: atomic replace; identical content is left alone.
write_file() {
    local dest="$1" mode="$2" content="$3" tmp
    if [[ -f "$dest" && "$(<"$dest")" == "$content" ]]; then
        echo "unchanged $dest"
        return
    fi
    if [[ "$dry_run" == 1 ]]; then
        echo "would write $dest (mode $mode)"
        return
    fi
    tmp="$(mktemp "$dest.XXXXXX")" || die 3 "cannot write next to $dest"
    if ! { printf '%s\n' "$content" > "$tmp" && chmod "$mode" "$tmp" && mv -f -- "$tmp" "$dest"; }; then
        rm -f -- "$tmp"
        die 3 "failed to write $dest"
    fi
    echo "wrote $dest"
}

cmd_render() {
    require_runner
    ensure_dir "$config_dir"
    ensure_dir "$state_dir"
    ensure_dir "$state_dir/work"
    ensure_dir "$unit_dir"
    write_file "$config" 600 "$(render_config)"
    write_file "$unit" 644 "$(render_unit)"
}

# Prints how this runner accepts a token without argv: token-file or env.
token_channel() {
    local help
    help="$("$runner_bin" register --help 2>&1 || true)"
    if grep -q -- '--token-file' <<<"$help"; then
        echo token-file
    elif grep -q 'GITEA_RUNNER_REGISTRATION_TOKEN' <<<"$help"; then
        echo env
    else
        return 1
    fi
}

secure_runner_file() {
    if [[ "$(mode_of "$runner_file")" != 600 ]]; then
        run chmod 600 -- "$runner_file" || die 3 "cannot chmod 600 $runner_file"
    fi
}

cmd_register() {
    [[ -n "$instance" ]] || die 2 "register needs --instance URL"
    [[ -n "$token_file" ]] || die 2 "register needs --token-file PATH"
    [[ "$instance" =~ ^https?://[^[:space:]]+$ ]] || die 2 "--instance must be an http(s):// URL"
    name="${name:-factory-host-$(hostname -s 2>/dev/null || uname -n)}"
    [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die 2 "--name may use letters, digits, '.', '_' and '-'"
    require_runner
    if [[ -e "$runner_file" ]]; then
        secure_runner_file
        echo "already registered ($runner_file exists); delete it and the runner in Gitea to re-register"
        return
    fi
    if [[ ! -f "$config" ]]; then
        [[ "$dry_run" == 1 ]] || die 3 "missing $config; run render first"
        echo "note: $config is not rendered yet; run render before a real register"
    fi
    [[ -f "$token_file" && ! -L "$token_file" ]] || die 3 "token file not found or not a regular file: $token_file"
    [[ "$(stat -c '%u' -- "$token_file")" == "$(id -u)" ]] || die 3 "token file must be owned by $(id -un): $token_file"
    [[ "$(mode_of "$token_file")" == 600 || "$(mode_of "$token_file")" == 400 ]] \
        || die 3 "token file must be mode 600: chmod 600 $token_file"
    local token channel output status=0
    token="$(tr -d '[:space:]' < "$token_file")"
    [[ -n "$token" ]] || die 3 "token file is empty: $token_file"
    channel="$(token_channel)" || die 3 "$runner_bin register offers no --token-file or GITEA_RUNNER_REGISTRATION_TOKEN; refusing to pass the token on the command line"
    local args=(--config "$config" register --no-interactive --instance "$instance" --name "$name" --labels "$label")
    [[ "$channel" == token-file ]] && args+=(--token-file "$token_file")
    if [[ "$dry_run" == 1 ]]; then
        printf 'would run (token via %s):' "$channel"; printf ' %q' "$runner_bin" "${args[@]}"; echo
        return
    fi
    ensure_dir "$state_dir"
    if [[ "$channel" == env ]]; then
        output="$(cd "$state_dir" && umask 077 && GITEA_RUNNER_REGISTRATION_TOKEN="$token" "$runner_bin" "${args[@]}" 2>&1)" || status=$?
    else
        output="$(cd "$state_dir" && umask 077 && "$runner_bin" "${args[@]}" 2>&1)" || status=$?
    fi
    [[ -z "$output" ]] || printf '%s\n' "${output//"$token"/[redacted]}"
    [[ "$status" == 0 ]] || die 3 "gitea-runner register failed (exit $status)"
    [[ -f "$runner_file" ]] || die 3 "register finished but $runner_file was not written"
    secure_runner_file
    echo "registered $name with label $label"
}

cmd_enable() {
    [[ -f "$unit" ]] || die 3 "missing $unit; run render first"
    [[ -f "$runner_file" ]] || die 3 "missing $runner_file; run register first"
    command -v systemctl >/dev/null || die 3 "systemctl not found; start '$runner_bin daemon --config $config' another way"
    run systemctl --user daemon-reload || die 3 "systemctl --user daemon-reload failed"
    run systemctl --user enable --now "$service" || die 3 "systemctl --user enable --now $service failed"
    if command -v loginctl >/dev/null && [[ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)" != yes ]]; then
        echo "note: user lingering is off, so the runner stops at logout; 'loginctl enable-linger $(id -un)' keeps it running"
    fi
}

failures=0
ok() { echo "ok: $*"; }
warn() { echo "warn: $*"; }
fail() { echo "FAIL: $*"; failures=$((failures + 1)); }

cmd_doctor() {
    local channel
    if find_runner; then
        ok "runner binary $runner_bin ($("$runner_bin" --version 2>/dev/null | head -n 1 || true))"
        if channel="$(token_channel)"; then ok "register accepts the token via $channel"
        else fail "$runner_bin register offers no --token-file or GITEA_RUNNER_REGISTRATION_TOKEN"; fi
    else
        fail "gitea-runner not found; install it or pass --runner-bin PATH"
    fi
    if [[ -f "$config" ]]; then
        if grep -q "\"$label\"" "$config"; then ok "config $config advertises $label"
        else fail "config $config does not advertise $label"; fi
        if grep -Eq '^[[:space:]]*-[[:space:]]*"?[^"#]*:(docker|lxc)' "$config"; then
            fail "config $config also advertises a container label; keep this runner host-only"
        fi
        [[ "$(render_config)" == "$(<"$config")" ]] || warn "config $config differs from the template; review, then rerun render"
    else
        fail "missing $config; run render"
    fi
    if [[ -f "$runner_file" ]]; then
        if [[ "$(mode_of "$runner_file")" == 600 ]]; then ok "registered ($runner_file, mode 600)"
        else fail "$runner_file is mode $(mode_of "$runner_file"); chmod 600 it"; fi
    else
        fail "not registered: missing $runner_file; run register"
    fi
    if [[ -f "$unit" ]]; then
        if grep -q -- "--config $config" "$unit"; then ok "unit $unit uses $config"
        else fail "unit $unit does not use $config; rerun render"; fi
    else
        fail "missing $unit; run render"
    fi
    if command -v systemctl >/dev/null; then
        local enabled active
        enabled="$(systemctl --user is-enabled "$service" 2>/dev/null || true)"
        active="$(systemctl --user is-active "$service" 2>/dev/null || true)"
        if [[ "$enabled" == enabled ]]; then ok "$service is enabled"; else fail "$service is ${enabled:-not installed}; run enable"; fi
        if [[ "$active" == active ]]; then ok "$service is active"; else fail "$service is ${active:-unknown}"; fi
    else
        warn "systemctl not found; cannot check $service"
    fi
    if command -v loginctl >/dev/null; then
        if [[ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null || true)" == yes ]]; then ok "user lingering is on"
        else warn "user lingering is off; the runner stops at logout (loginctl enable-linger $(id -un))"; fi
    fi
    if [[ -x "$pr_trigger" && ! -d "$pr_trigger" ]]; then ok "pr-trigger is installed at $pr_trigger"
    else fail "missing executable $pr_trigger; install it from the PR loop"; fi
    if [[ "$failures" -gt 0 ]]; then
        echo "doctor: $failures problem(s) found"
        exit 3
    fi
    echo "doctor: factory-host runner looks ready"
}

"cmd_$command"
