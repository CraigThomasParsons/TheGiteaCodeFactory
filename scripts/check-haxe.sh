#!/usr/bin/env bash
# check-haxe.sh — prove the committed generated files match their Haxe source.
#
# 1. Checks the compiler and libraries match the pins in haxe/toolchain.env.
# 2. Rebuilds every haxe/build/*.hxml into a temporary directory and fails if
#    any output differs from the committed file, or if the file is not tracked
#    by Git. This catches hand edits to generated files and Haxe changes whose
#    output was not rebuilt and committed.
# 3. Runs the toolchain proof (the same Haxe source compiled to Python and to
#    Node must print the same thing) and the utest suites in haxe/test/ on
#    Haxe's interpreter, Python and Node.
#
# Nothing in the working tree is modified. Fails when Haxe is missing unless
# CHECK_SKIP_HAXE=1 is set. Install the toolchain with scripts/install-haxe.sh;
# see docs/haxe-setup.md.
set -euo pipefail

# shellcheck source=haxe-common.sh
source "$(dirname "$0")/haxe-common.sh"
cd "$gcf_root"

if [[ "${CHECK_SKIP_HAXE:-0}" == "1" ]]; then
    echo "check-haxe: CHECK_SKIP_HAXE=1; generated files and Haxe tests were not checked." >&2
    exit 0
fi

if ! gcf_have_haxe; then
    echo "check-haxe: haxe not found; generated files were not checked." >&2
    echo "check-haxe: install it with 'bash scripts/install-haxe.sh' (docs/haxe-setup.md), or set CHECK_SKIP_HAXE=1 to skip deliberately." >&2
    exit 1
fi
gcf_require_pinned_haxe
gcf_check_library_pins

scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
status=0

echo "check-haxe: rebuilding generated files"
in_git=0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 && in_git=1
while IFS= read -r generated; do
    if [[ "$in_git" == 1 ]] && ! git ls-files --error-unmatch -- "$generated" >/dev/null 2>&1; then
        echo "check-haxe: $generated is generated but not committed" >&2
        status=1
        continue
    fi
    # diff rather than `git diff --no-index`, so the check also works outside a
    # Git checkout (a source tarball, or a container without the .git directory).
    if ! diff -u -- "$generated" "$scratch/out/$generated"; then
        echo "check-haxe: $generated differs from its Haxe source; run 'bash scripts/build-haxe.sh' and commit the result (never edit it by hand)" >&2
        status=1
    fi
done < <(bash scripts/build-haxe.sh --out-root "$scratch/out")

echo "check-haxe: running the toolchain proof"
python_output="$(python3 haxe/generated/proof/hello.py first second)"
node_output="$(node haxe/generated/proof/hello.js first second)"
if [[ "$python_output" != "proof ok: target=python, args=first|second, reversed=second|first" ||
      "$node_output" != "proof ok: target=node, args=first|second, reversed=second|first" ]]; then
    echo "check-haxe: toolchain proof printed unexpected output:" >&2
    printf '  python: %s\n  node:   %s\n' "$python_output" "$node_output" >&2
    status=1
fi

for suite in haxe/test/*.hxml; do
    echo "check-haxe: utest on $(basename "$suite" .hxml)"
    expanded="$scratch/test.hxml"
    output="$scratch/tests.out"
    gcf_expand_hxml "$suite" "$output" > "$expanded"
    if ! "$gcf_haxe" "$expanded"; then
        status=1
        continue
    fi
    case "$gcf_target" in
        python) python3 "$output" || status=1 ;;
        js) cp "$output" "$scratch/tests.cjs" && node "$scratch/tests.cjs" || status=1 ;;
    esac
done

if [[ "$status" == 0 ]]; then
    echo "check-haxe: generated files match their source; proof and utest passed"
fi
exit "$status"
