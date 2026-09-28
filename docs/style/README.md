# Example style guides

Agents review and write code against written standards. These guides are the
author's real ones, taken from their own projects, and are included as worked
examples of the level of detail that makes agent review useful. They are not
universal rules.

| Guide | Written for |
|---|---|
| [php_style.md](php_style.md), [eloquent_style.md](eloquent_style.md) | A Laravel/Livewire browser game |
| [python_style.md](python_style.md) | That game's automation and NAS deployment scripts |
| [javascript_node_style.md](javascript_node_style.md), [ts_node_style.md](ts_node_style.md) | Node.js and TypeScript tooling |
| [typescript_quality_architecture.md](typescript_quality_architecture.md), [unicode_and_hygiene_standards.md](unicode_and_hygiene_standards.md) | The game's TypeScript front end: how lint, type-check and hygiene checks are split up and rolled out |
| [golang_style.md](golang_style.md) | Go services |

To use one, copy it into your project's `docs/style/`, keep the rules you agree
with and replace project names, paths and vocabulary. The advisory reviewer reads
`docs/style/javascript_node_style.md` and `docs/style/ts_node_style.md` from the
target repository by default; see [pr-loops.md](../pr-loops.md) to point it at others.
