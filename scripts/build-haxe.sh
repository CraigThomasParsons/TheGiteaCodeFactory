#!/usr/bin/env bash
# build-haxe.sh — regenerate the committed files that are built from Haxe source.
#
# Each haxe/build/<name>.hxml compiles one Haxe entry point to one Python 3 or
# Node.js file at the path its --python or --js line names. This script adds a
# "generated, do not edit" header (and, for Node, a prologue that lets the
# CommonJS output run inside this repository's ES-module package), then writes
# the file in place. Commit the regenerated files with the source change.
#
# Usage: scripts/build-haxe.sh [--out-root DIR] [haxe/build/<name>.hxml ...]
#   --out-root DIR  write outputs under DIR instead of the repository (the
#                   drift check in check-haxe.sh uses this)
#   With no build files, builds every haxe/build/*.hxml.
#
# Requires the pinned Haxe and libraries: bash scripts/install-haxe.sh
# (see docs/haxe-setup.md). Prints each generated path on standard output.
set -euo pipefail

# shellcheck source=haxe-common.sh
source "$(dirname "$0")/haxe-common.sh"
cd "$gcf_root"

out_root="$gcf_root"
builds=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --out-root)
            [[ $# -ge 2 ]] || { echo "build-haxe: --out-root needs a directory" >&2; exit 2; }
            out_root="$(mkdir -p "$2" && cd "$2" && pwd)"
            shift
            ;;
        -h|--help) sed -n '2,/^set -euo/p' "$0" | sed -e '$d' -e 's/^# \{0,1\}//'; exit 0 ;;
        *) builds+=("$1") ;;
    esac
    shift
done
if [[ ${#builds[@]} -eq 0 ]]; then
    shopt -s nullglob
    builds=(haxe/build/*.hxml)
    shopt -u nullglob
fi
if [[ ${#builds[@]} -eq 0 ]]; then
    echo "build-haxe: no build files in haxe/build/" >&2
    exit 0
fi

gcf_require_pinned_haxe || exit 1

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

# source_for BUILD_FILE: the .hx file holding the build's --main class.
source_for() {
    local build="$1" main cp candidate
    main="$(sed -nE 's/^[[:space:]]*(--main|-m)[[:space:]]+([A-Za-z0-9_.]+).*/\2/p' "$build" | head -n 1)"
    while read -r cp; do
        candidate="$cp/${main//.//}.hx"
        if [[ -f "$candidate" ]]; then
            echo "$candidate"
            return
        fi
    done < <(sed -nE 's/^[[:space:]]*(--class-path|-cp|-p)[[:space:]]+(.+)$/\2/p' "$build")
    echo "${main:-unknown}"
}

for build in "${builds[@]}"; do
    expanded="$scratch/build.hxml"
    raw="$scratch/raw"
    rm -f "$raw"
    gcf_expand_hxml "$build" "$raw" > "$expanded"
    if [[ -z "$gcf_target" ]]; then
        echo "build-haxe: $build has no --python or --js output" >&2
        exit 1
    fi
    "$gcf_haxe" "$expanded" >&2
    source_file="$(source_for "$build")"
    destination="$out_root/$gcf_output"
    mkdir -p "$(dirname "$destination")"
    {
        if [[ "$gcf_target" == python ]]; then
            echo "#!/usr/bin/env python3"
            echo "# GENERATED FILE - DO NOT EDIT."
            echo "# Built by scripts/build-haxe.sh from $source_file ($build)."
            echo "# Change the Haxe source and rebuild; see docs/haxe-setup.md."
        else
            echo "#!/usr/bin/env node"
            echo "// GENERATED FILE - DO NOT EDIT."
            echo "// Built by scripts/build-haxe.sh from $source_file ($build)."
            echo "// Change the Haxe source and rebuild; see docs/haxe-setup.md."
            echo 'import { createRequire } from "node:module";'
            echo 'const require = createRequire(import.meta.url);'
        fi
        cat "$raw"
    } > "$destination.tmp"
    # Keep the mode of a file being replaced so Git sees no mode change.
    if [[ -e "$destination" ]]; then
        chmod --reference="$destination" "$destination.tmp"
    fi
    mv "$destination.tmp" "$destination"
    echo "$gcf_output"
done
