#!/usr/bin/env python3
"""Install the complete skill dependency set, without replacing existing skills."""
import argparse
from pathlib import Path
import shutil


def install(source, destination):
    candidates = sorted(p for p in source.iterdir() if (p / 'SKILL.md').is_file())
    conflicts = [p.name for p in candidates if (destination / p.name).exists() or (destination / p.name).is_symlink()]
    if conflicts:
        raise ValueError('Existing skills preserved; choose an empty destination: ' + ', '.join(conflicts))
    destination.mkdir(parents=True, exist_ok=True)
    for p in candidates:
        shutil.copytree(p, destination / p.name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    return len(candidates)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True,
                        help='e.g. a target repository/.agents/skills; no implicit home-directory writes')
    args = parser.parse_args()
    try:
        count = install(Path(__file__).resolve().parents[1] / 'skills', args.destination.expanduser())
        print(f'Installed {count} skills in {args.destination}; existing agent settings unchanged.')
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
