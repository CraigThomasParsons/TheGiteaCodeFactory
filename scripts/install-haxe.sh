#!/usr/bin/env bash
# install-haxe.sh — install the pinned Haxe compiler and libraries this kit builds with.
#
# Versions, download URLs and SHA-256 checksums come from haxe/toolchain.env.
# Every download is verified against its checksum before it is used. Nothing is
# installed system-wide unless --system is given.
#
# Usage: scripts/install-haxe.sh [--ci | --system] [--libs-only] [--prefix DIR]
#
#   (no mode)    Per-user install. The compiler goes to
#                ${XDG_DATA_HOME:-~/.local/share}/gitea-code-factory/haxe-<version>,
#                unless a `haxe` of the pinned version is already on PATH.
#   --ci         Install everything into a new temporary directory (under
#                $RUNNER_TEMP when set). For CI jobs and for trying the toolchain
#                without touching your home directory.
#   --system     System-wide compiler. On Arch Linux and derivatives (CachyOS,
#                Manjaro, EndeavourOS) uses `sudo pacman -S haxe` when the
#                repository version matches the pin; otherwise extracts the
#                official tarball into /opt/haxe-<version> and links
#                /usr/local/bin/haxe. Needs sudo. Libraries stay per-user.
#   --libs-only  Install only the libraries, for machines that already have the
#                pinned compiler (for example from a CI setup action).
#   --prefix DIR Install under DIR instead of the default location.
#
# Libraries go to $HAXE_LIBCACHE, default ~/haxe/haxe_libraries (the location
# lix uses, so lix users share one cache); with --ci they go to the temporary
# directory.
#
# Standard output carries only shell `export` lines, so callers can run
#   eval "$(bash scripts/install-haxe.sh --ci)"
# Progress messages go to standard error. In GitHub or Gitea Actions, --ci also
# appends the same settings to $GITHUB_PATH and $GITHUB_ENV for later steps.
#
# Exit codes: 0 installed, 1 download, checksum or install failure, 2 usage error.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=../haxe/toolchain.env
source "$root/haxe/toolchain.env"

mode=user
libs_only=0
prefix=""

usage() {
    sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci) mode=ci ;;
        --system) mode=system ;;
        --libs-only) libs_only=1 ;;
        --prefix)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            prefix="$2"
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) echo "install-haxe: unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

log() { echo "install-haxe: $*" >&2; }
fail() { log "$*"; exit 1; }

for tool in curl tar python3; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required"
done

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# download URL SHA256 DESTINATION: fetch, verify, then move into place.
download() {
    local url="$1" expected="$2" destination="$3" partial actual
    partial="$destination.partial"
    log "downloading $url"
    curl -fsSL --retry 3 --retry-delay 2 -o "$partial" "$url" || { rm -f "$partial"; fail "download failed: $url"; }
    actual="$(sha256_of "$partial")"
    if [[ "$actual" != "$expected" ]]; then
        rm -f "$partial"
        fail "checksum mismatch for $url: expected $expected, got $actual"
    fi
    mv "$partial" "$destination"
}

installed_version() {
    "$1" -version 2>/dev/null | head -n 1 || true
}

case "$mode" in
    ci)
        if [[ -n "$prefix" ]]; then
            base="$prefix"
            mkdir -p "$base"
        else
            base="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/gcf-haxe.XXXXXX")"
        fi
        compiler_dir="$base/haxe-$GCF_HAXE_VERSION"
        libcache="$base/haxe_libraries"
        ;;
    user)
        base="${prefix:-${XDG_DATA_HOME:-$HOME/.local/share}/gitea-code-factory}"
        compiler_dir="$base/haxe-$GCF_HAXE_VERSION"
        libcache="${HAXE_LIBCACHE:-$HOME/haxe/haxe_libraries}"
        ;;
    system)
        compiler_dir="${prefix:-/opt}/haxe-$GCF_HAXE_VERSION"
        libcache="${HAXE_LIBCACHE:-$HOME/haxe/haxe_libraries}"
        ;;
esac

path_dir=""

# Extract the official tarball into $1 (its single top-level directory is dropped).
install_tarball() {
    local target="$1" use_sudo="${2:-}" scratch
    if [[ -x "$target/haxe" && "$(installed_version "$target/haxe")" == "$GCF_HAXE_VERSION" ]]; then
        log "haxe $GCF_HAXE_VERSION already present in $target"
        return
    fi
    scratch="$(mktemp -d)"
    download "$GCF_HAXE_LINUX64_URL" "$GCF_HAXE_LINUX64_SHA256" "$scratch/haxe.tar.gz"
    $use_sudo mkdir -p "$target"
    $use_sudo tar -xzf "$scratch/haxe.tar.gz" -C "$target" --strip-components=1
    rm -rf "$scratch"
    [[ "$(installed_version "$target/haxe")" == "$GCF_HAXE_VERSION" ]] || fail "installed compiler in $target does not report $GCF_HAXE_VERSION"
    log "installed haxe $GCF_HAXE_VERSION in $target"
}

is_arch_like() {
    [[ -r /etc/os-release ]] || return 1
    # shellcheck disable=SC1091
    local id id_like
    id="$(. /etc/os-release; echo "${ID:-}")"
    id_like="$(. /etc/os-release; echo "${ID_LIKE:-}")"
    [[ "$id" == arch || " $id_like " == *" arch "* ]]
}

install_compiler() {
    [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || \
        fail "the pinned tarball is for Linux x86_64; install Haxe $GCF_HAXE_VERSION yourself (see docs/haxe-setup.md), then rerun with --libs-only"
    case "$mode" in
        ci)
            install_tarball "$compiler_dir"
            path_dir="$compiler_dir"
            ;;
        user)
            local existing
            existing="$(command -v haxe 2>/dev/null || true)"
            if [[ -n "$existing" && "$(installed_version "$existing")" == "$GCF_HAXE_VERSION" ]]; then
                log "using haxe $GCF_HAXE_VERSION already on PATH at $existing"
                return
            fi
            install_tarball "$compiler_dir"
            path_dir="$compiler_dir"
            ;;
        system)
            local sudo_cmd=""
            [[ "$(id -u)" == 0 ]] || sudo_cmd="sudo"
            if is_arch_like && command -v pacman >/dev/null 2>&1; then
                local repo_version
                repo_version="$(pacman -Si haxe 2>/dev/null | awk -F': ' '/^Version/ {print $2; exit}')"
                if [[ "$repo_version" == "$GCF_HAXE_VERSION"-* ]]; then
                    log "installing haxe $repo_version with pacman"
                    $sudo_cmd pacman -S --needed haxe
                    return
                fi
                log "pacman offers haxe '${repo_version:-none}', not $GCF_HAXE_VERSION; using the official tarball"
            fi
            install_tarball "$compiler_dir" "$sudo_cmd"
            $sudo_cmd ln -sf "$compiler_dir/haxe" /usr/local/bin/haxe
            log "linked /usr/local/bin/haxe -> $compiler_dir/haxe"
            ;;
    esac
}

# Unpack a lib.haxe.org archive into $2, dropping a single wrapping directory if present.
extract_library() {
    python3 - "$1" "$2" <<'PY'
import pathlib, shutil, sys, tempfile, zipfile
archive, target = sys.argv[1], pathlib.Path(sys.argv[2])
with tempfile.TemporaryDirectory() as scratch:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            resolved = (pathlib.Path(scratch) / member).resolve()
            if not str(resolved).startswith(str(pathlib.Path(scratch).resolve())):
                sys.exit("archive member escapes the target directory: " + member)
        zf.extractall(scratch)
    top = pathlib.Path(scratch)
    entries = list(top.iterdir())
    if len(entries) == 1 and entries[0].is_dir() and (entries[0] / "haxelib.json").is_file():
        top = entries[0]
    if not (top / "haxelib.json").is_file():
        sys.exit("archive has no haxelib.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(top, target)
PY
}

install_libraries() {
    local entry name version sha target scratch
    mkdir -p "$libcache"
    for entry in $GCF_HAXE_LIBS; do
        IFS=: read -r name version sha <<<"$entry"
        target="$libcache/$name/$version/haxelib"
        if [[ -f "$target/haxelib.json" ]]; then
            log "library $name $version already present in $libcache"
            continue
        fi
        scratch="$(mktemp -d)"
        download "https://lib.haxe.org/p/$name/$version/download/" "$sha" "$scratch/$name.zip"
        extract_library "$scratch/$name.zip" "$target" || fail "could not unpack $name $version"
        rm -rf "$scratch"
        log "installed library $name $version in $libcache"
    done
}

if [[ "$libs_only" == 0 ]]; then
    install_compiler
fi
install_libraries

if [[ -n "$path_dir" ]]; then
    printf 'export PATH=%q:"$PATH"\n' "$path_dir"
fi
printf 'export HAXE_LIBCACHE=%q\n' "$libcache"

if [[ "$mode" == ci ]]; then
    if [[ -n "$path_dir" && -n "${GITHUB_PATH:-}" ]]; then
        echo "$path_dir" >> "$GITHUB_PATH"
    fi
    if [[ -n "${GITHUB_ENV:-}" ]]; then
        echo "HAXE_LIBCACHE=$libcache" >> "$GITHUB_ENV"
    fi
fi
