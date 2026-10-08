# Haxe toolchain setup

The kit's helper scripts are being moved to a single source language,
[Haxe](https://haxe.org/), whose compiler turns one program into Python 3 or
JavaScript (see the [decision record](adr/0001-haxe-as-the-source-language.md)).
The generated Python and JavaScript files are committed at the paths the helpers
have always had, so:

- **Running** a helper needs only Python 3 or Node.js, exactly as before. You do
  not need Haxe to use the kit, install its skills or run its helpers.
- **Changing or checking** a helper needs the pinned Haxe toolchain described
  here, because `scripts/check-ci.sh` rebuilds every generated file and fails if
  it differs from the committed copy.

Commands on this page run from the root of your TheGiteaCodeFactory clone.

## What is pinned

| Component | Version | What it is |
|---|---|---|
| Haxe compiler | 4.3.7 | The compiler and its standard library. A single Linux binary with no runtime dependencies. |
| [utest](https://lib.haxe.org/p/utest/) | 1.13.2 | Unit-test library for Haxe code. |
| [hxnodejs](https://lib.haxe.org/p/hxnodejs/) | 12.2.0 | Haxe bindings for Node.js APIs, used by the Node target. |

The versions, download URLs and SHA-256 checksums live in
[haxe/toolchain.env](../haxe/toolchain.env). The same versions are written in the
format of [lix](https://github.com/lix-pm/lix.client), a Haxe version and library
manager, in [.haxerc](../.haxerc) and [haxe_libraries/](../haxe_libraries/). You
do not need lix: the kit's scripts read those files themselves.

Neither haxelib (Haxe's own package manager) nor Neko (the virtual machine
haxelib runs on) is needed.

## Install

`scripts/install-haxe.sh` downloads the pinned compiler and libraries, checks
every download against its SHA-256, and prints the shell settings to use them.
Its progress messages go to standard error and the settings to standard output,
so you can apply them with `eval`. It never installs system-wide unless you pass
`--system`. Run `bash scripts/install-haxe.sh --help` for every option.

### Try it without changing your home directory

```bash
eval "$(bash scripts/install-haxe.sh --ci)"
```

This puts everything in a new temporary directory and adds it to `PATH` for the
current shell only. CI jobs use this mode.

### Arch Linux and derivatives (CachyOS, Manjaro, EndeavourOS)

Arch's `extra` repository usually carries the current Haxe. Check that it is the
pinned version, then install it and add the libraries:

```bash
pacman -Si haxe | grep '^Version'       # expect 4.3.7-<release>
sudo pacman -S --needed haxe
bash scripts/install-haxe.sh --libs-only
```

`bash scripts/install-haxe.sh --system` does the same version check and falls
back to the official tarball in `/opt/haxe-4.3.7` (linked from
`/usr/local/bin/haxe`) when the repository has a different version.

If you would rather not install anything system-wide, use the per-user install
below; it works on any x86_64 Linux.

### Debian, Ubuntu and other x86_64 Linux

Distribution packages are often too old: Debian 12 (bookworm) ships Haxe 4.2.5.
Install the official tarball for your user instead:

```bash
bash scripts/install-haxe.sh
```

The compiler goes to `~/.local/share/gitea-code-factory/haxe-4.3.7` (or under
`$XDG_DATA_HOME`), the libraries to `~/haxe/haxe_libraries`. Add the two lines
it prints to your shell profile, for example:

```bash
export PATH="$HOME/.local/share/gitea-code-factory/haxe-4.3.7:$PATH"
export HAXE_LIBCACHE="$HOME/haxe/haxe_libraries"
```

If a `haxe` of the pinned version is already on your `PATH`, the script keeps it
and installs only the libraries. For a system-wide install in
`/opt/haxe-4.3.7`, use `bash scripts/install-haxe.sh --system` (needs sudo).
Ubuntu users can also use the Haxe Foundation's `ppa:haxe/releases`, provided it
offers 4.3.7, followed by `--libs-only`.

### Other platforms

The pinned tarball is for Linux x86_64. Elsewhere, install Haxe 4.3.7 from
[haxe.org/download](https://haxe.org/download/), then run
`bash scripts/install-haxe.sh --libs-only` for the libraries.

### lix users

`npx lix download` reads `.haxerc` and `haxe_libraries/` and installs the same
versions into the same library cache (`~/haxe/haxe_libraries`), so lix and
`install-haxe.sh` can be mixed.

## Verify

```bash
haxe -version                 # 4.3.7
bash scripts/check-haxe.sh
```

`check-haxe.sh` should end with:

```text
check-haxe: generated files match their source; proof and utest passed
```

It checks the compiler and library versions, rebuilds every generated file into
a temporary directory and compares it with the committed copy, runs the
toolchain proof (one Haxe program compiled to Python and to Node, which must
print the same line) and runs the utest suites on Haxe's interpreter, Python and
Node. It does not modify your working tree.

## Where things are

| Path | Contents |
|---|---|
| `haxe/src/gcf/<helper>/` | Haxe source, one package per helper |
| `haxe/build/<name>.hxml` | One build file per generated file. Each names exactly one `--python` or `--js` output path |
| `haxe/test/` | utest suites (`TestMain.hx` lists them) and one build file per test target |
| `haxe/generated/` | Generated files that have no historical path, such as the toolchain proof in `haxe/generated/proof/` |
| `haxe/toolchain.env` | Pinned versions and checksums |
| `.haxerc`, `haxe_libraries/` | The same pins in lix format |
| `scripts/install-haxe.sh` | Installs the toolchain |
| `scripts/build-haxe.sh` | Regenerates the committed files |
| `scripts/check-haxe.sh` | Drift check, proof and utest; called by `check-ci.sh` |

## Change a helper and rebuild

1. Edit the Haxe source under `haxe/src/`, and its tests under `haxe/test/`.
2. Regenerate the committed files:

   ```bash
   bash scripts/build-haxe.sh
   ```

   It prints each file it wrote. Pass one or more `haxe/build/<name>.hxml`
   files to rebuild only those.
3. Run `bash scripts/check.sh` (or `bash scripts/check-ci.sh` without Docker).
4. Commit the Haxe change and the regenerated files together.

Build through `scripts/build-haxe.sh`, not by running `haxe haxe/build/<name>.hxml`
directly: the script expands the `-lib` lines from `haxe_libraries/`, adds the
generated-file header and, for Node output, a two-line prologue that lets
Haxe's CommonJS output run in this repository's ES-module package.

### Never edit a generated file

Generated files begin with a header like:

```text
# GENERATED FILE - DO NOT EDIT.
# Built by scripts/build-haxe.sh from haxe/src/gcf/proof/HelloPython.hx (haxe/build/proof-python.hxml).
```

A hand edit is overwritten by the next build, and `check-haxe.sh` rejects it in
CI. Change the Haxe source instead. This applies to agents too: when a review
finding points at a generated file, fix the Haxe source and rebuild.

### Add a generated file

Create `haxe/build/<name>.hxml` with the class path, the `--main` class, any
`-lib` lines and exactly one output line, for example:

```text
--class-path haxe/src
--main gcf.example.Main
--python scripts/example.py
```

Run `bash scripts/build-haxe.sh` and commit the new build file, source and
output. `check-haxe.sh` fails for a generated file that is not committed.

### Add or update a library

Add `name:version:sha256` to `GCF_HAXE_LIBS` in `haxe/toolchain.env`, where the
checksum is that of `https://lib.haxe.org/p/<name>/<version>/download/`, and add
`haxe_libraries/<name>.hxml` in lix format (copy an existing one, including any
flags from the library's `extraParams.hxml`). Then run
`bash scripts/install-haxe.sh --libs-only`.

## CI

- **Gitea Actions** ([.gitea/workflows/pr-validation.yml](../.gitea/workflows/pr-validation.yml)):
  the `factory-node` runner image has Python and Node but no Haxe, so the job
  runs `eval "$(bash scripts/install-haxe.sh --ci)"` before
  `bash scripts/check-ci.sh`. That downloads about 10 MB on each run and needs
  internet access to `github.com` and `lib.haxe.org` from the runner.
- **GitHub Actions** ([.github/workflows/check.yml](../.github/workflows/check.yml)):
  `krdlab/setup-haxe`, pinned by commit, installs the compiler, and
  `install-haxe.sh --ci --libs-only` adds the libraries.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `check-haxe: haxe not found` | Install the toolchain as above, or make sure its directory is on `PATH` in the shell running the check. To skip on purpose (for example on a machine where you only run the kit), set `CHECK_SKIP_HAXE=1`. CI must not skip. |
| `haxe 4.x.y found ...; this kit is pinned to 4.3.7` | Another Haxe comes first on `PATH`. Put the pinned one first, or point the scripts at it with `HAXE=/path/to/haxe`. |
| `library ... is not installed in ...` | Run `bash scripts/install-haxe.sh --libs-only`. If you installed into another location, export the `HAXE_LIBCACHE` it printed. |
| `checksum mismatch for ...` | The download is not the file the pin describes. Retry once; if it persists, do not replace the checksum without finding out why the published file changed. |
| `... differs from its Haxe source` | A generated file was edited by hand, or Haxe source changed without a rebuild. Run `bash scripts/build-haxe.sh` and commit the result. If you changed nothing, check `haxe -version`. |
| `... is generated but not committed` | Commit the new generated file with its build file and source. |
| `This is the first time you are running haxelib` | Something ran `haxe` on a build file directly, so Haxe asked haxelib to resolve `-lib`. Use `scripts/build-haxe.sh`, or lix, which resolve libraries themselves. |
| `ReferenceError: require is not defined` | Raw Haxe JavaScript output was run inside this repository's ES-module package. Generated files built by `build-haxe.sh` include the prologue that prevents this. |
| CI job never starts | The runner does not advertise the `factory-node` label, or cannot serve this repository. See [gitea-prerequisites.md](gitea-prerequisites.md#2-a-runner-with-a-label-the-workflows-ask-for). |
| CI fails while downloading | The runner has no internet access to `github.com` or `lib.haxe.org`. Allow it, or provide a runner image with Haxe 4.3.7 and the libraries already installed and set `HAXE_LIBCACHE`. |
