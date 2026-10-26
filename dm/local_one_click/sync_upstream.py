#!/usr/bin/env python3
"""Merge upstream, retaining this fork's narrowly scoped launcher files."""
import argparse
import os
from pathlib import Path
import subprocess

FILES = {'一键生成完整IPA.command', 'scripts/nx_one_click.py',
         'docs/ONE-CLICK.md', '.github/workflows/sync-upstream.yml',
         '.github/workflows/local-one-click-tests.yml'}
PREFIXES = ('dm/local_one_click/',)


def protected(path):
    return path in FILES or any(path.startswith(prefix) for prefix in PREFIXES)


def git(*args, check=True):
    return subprocess.run(['git', *args], check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def paths(*args):
    return [p for p in git(*args).stdout.decode().split('\0') if p]


def merge(upstream):
    if git('status', '--porcelain', '--untracked-files=all').stdout:
        raise RuntimeError('Sync requires a clean checkout.')
    before = git('rev-parse', 'HEAD').stdout.decode().strip()
    git('rev-parse', '--verify', upstream)
    outcome = git('-c', 'user.name=github-actions[bot]', '-c',
                  'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                  'merge', '--no-commit', '--no-ff', upstream, check=False)
    merge_head = git('rev-parse', '--git-path', 'MERGE_HEAD').stdout.decode().strip()
    active = Path(merge_head).exists()
    if not active:
        if outcome.returncode:
            raise RuntimeError(outcome.stderr.decode())
        print('Already up to date.')
        return False
    try:
        # Also restore nonconflicting upstream changes/deletions of protected files.
        candidates = set(paths('ls-files', '-z')) | set(paths('ls-tree', '-r', '--name-only', '-z', before))
        for path in sorted(p for p in candidates if protected(p)):
            git('restore', '--source=' + before, '--staged', '--worktree', '--', path)
        conflicts = paths('diff', '--name-only', '--diff-filter=U', '-z')
        if conflicts:
            raise RuntimeError('Conflicts outside launcher protection; no push: ' + ', '.join(conflicts))
        if outcome.returncode not in (0, 1):
            raise RuntimeError(outcome.stderr.decode())
        # A commit records the upstream parent even if its only changes were protected.
        git('-c', 'user.name=github-actions[bot]', '-c',
            'user.email=41898282+github-actions[bot]@users.noreply.github.com',
            'commit', '-m', 'Merge upstream; preserve local one-click frontend')
        print('Merged upstream. Preserved launcher and helper paths; no force push.')
        return True
    except BaseException:
        git('merge', '--abort', check=False)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream-ref', default='refs/remotes/upstream/main')
    args = parser.parse_args()
    merge(args.upstream_ref)
