#!/usr/bin/env bash
# haxe-common.sh — helpers shared by build-haxe.sh and check-haxe.sh.
# Source this file; it does nothing when run on its own.
#
# The build files in haxe/build/ and haxe/test/ are ordinary .hxml files in the
# format lix understands: `-lib <name>` refers to haxe_libraries/<name>.hxml,
# which uses ${HAXE_LIBCACHE}. Plain `haxe` resolves `-lib` through haxelib
# instead, so these helpers expand the library files themselves. That way the
# kit needs neither haxelib nor lix, and lix users still get the same result.

gcf_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../haxe/toolchain.env
source "$gcf_root/haxe/toolchain.env"

gcf_haxe="${HAXE:-haxe}"
gcf_libcache="${HAXE_LIBCACHE:-$HOME/haxe/haxe_libraries}"

gcf_have_haxe() {
    command -v "$gcf_haxe" >/dev/null 2>&1
}

gcf_haxe_version() {
    "$gcf_haxe" -version 2>/dev/null | head -n 1
}

# gcf_require_pinned_haxe: fail unless the compiler matches the pin.
gcf_require_pinned_haxe() {
    local found
    if ! gcf_have_haxe; then
        echo "haxe not found; install it with: bash scripts/install-haxe.sh (see docs/haxe-setup.md)" >&2
        return 1
    fi
    found="$(gcf_haxe_version)"
    if [[ "$found" != "$GCF_HAXE_VERSION" ]]; then
        echo "haxe $found found at $(command -v "$gcf_haxe"); this kit is pinned to $GCF_HAXE_VERSION (see docs/haxe-setup.md)" >&2
        return 1
    fi
}

# gcf_expand_hxml FILE OUTPUT_FILE: print FILE with every `-lib` expanded and
# the single --python/--js output path replaced by OUTPUT_FILE. Sets
# gcf_target (python or js) and gcf_output (the path the build file names).
gcf_expand_hxml() {
    gcf_target=""
    gcf_output=""
    gcf_expanded_libs=" "
    _gcf_expand "$1" "$2"
    if [[ -z "$gcf_target" ]]; then
        if ! grep -Eq '^[[:space:]]*--interp([[:space:]]|$)' "$1"; then
            echo "$1: needs exactly one --python, --js or --interp line" >&2
            return 1
        fi
    fi
}

_gcf_expand() {
    local file="$1" output_file="$2" line name
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" || "$line" == \#* ]] && continue
        if [[ "$line" =~ ^(-lib|-L|--library)[[:space:]]+([A-Za-z0-9_.-]+)$ ]]; then
            name="${BASH_REMATCH[2]}"
            [[ "$gcf_expanded_libs" == *" $name "* ]] && continue
            gcf_expanded_libs+="$name "
            if [[ ! -f "$gcf_root/haxe_libraries/$name.hxml" ]]; then
                echo "$file: library $name has no haxe_libraries/$name.hxml pin" >&2
                return 1
            fi
            _gcf_expand "$gcf_root/haxe_libraries/$name.hxml" "$output_file" || return 1
            continue
        fi
        if [[ "$line" =~ ^--(python|js)[[:space:]]+(.+)$ ]]; then
            if [[ -n "$gcf_target" ]]; then
                echo "$file: more than one output target" >&2
                return 1
            fi
            gcf_target="${BASH_REMATCH[1]}"
            gcf_output="${BASH_REMATCH[2]}"
            printf -- '--%s %s\n' "$gcf_target" "$output_file"
            continue
        fi
        printf '%s\n' "${line//\$\{HAXE_LIBCACHE\}/$gcf_libcache}"
    done < "$file"
}

# gcf_check_library_pins: the lix files must name the versions in toolchain.env,
# and those versions must be installed in $HAXE_LIBCACHE.
gcf_check_library_pins() {
    local entry name version sha ok=0
    if ! grep -q "\"version\": \"$GCF_HAXE_VERSION\"" "$gcf_root/.haxerc"; then
        echo ".haxerc does not pin Haxe $GCF_HAXE_VERSION (haxe/toolchain.env)" >&2
        ok=1
    fi
    for entry in $GCF_HAXE_LIBS; do
        IFS=: read -r name version sha <<<"$entry"
        if ! grep -q "/$name/$version/haxelib" "$gcf_root/haxe_libraries/$name.hxml" 2>/dev/null; then
            echo "haxe_libraries/$name.hxml does not pin $name $version (haxe/toolchain.env)" >&2
            ok=1
        fi
        if [[ ! -f "$gcf_libcache/$name/$version/haxelib/haxelib.json" ]]; then
            echo "library $name $version is not installed in $gcf_libcache; run: bash scripts/install-haxe.sh --libs-only" >&2
            ok=1
        fi
    done
    return "$ok"
}
