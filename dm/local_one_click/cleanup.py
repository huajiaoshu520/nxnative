"""Success-only cleanup of the frontend's private generated directories."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import shutil


@contextmanager
def build_lock(game_dir):
    # Lock the existing directory itself: no lock file is left after cleanup.
    fd = os.open(game_dir, os.O_RDONLY)
    legacy = None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            old = game_dir / '.nxnative-one-click/build.lock'
            if old.is_file():
                legacy = old.open('a')
                fcntl.flock(legacy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another build is using this game folder; stop or finish it before starting again.')
        yield
    finally:
        if legacy:
            legacy.close()
        os.close(fd)


def cleanup_success(game_dir, prepared_dir, title_id, ipa, keys):
    game_dir, prepared_dir, ipa, keys = [Path(p).resolve() for p in (game_dir, prepared_dir, ipa, keys)]
    if not (ipa.is_file() or (ipa.suffix == '.app' and ipa.is_dir())):
        raise ValueError('Cannot clean before a verified IPA or Mac app is published.')
    if not title_id or len(title_id) != 16 or any(c not in '0123456789abcdefABCDEF' for c in title_id):
        raise ValueError('Invalid cleanup title ID.')
    work = game_dir / '.nxnative-one-click'
    if prepared_dir != game_dir and not prepared_dir.is_relative_to(work / 'container-inputs'):
        raise ValueError('Prepared inputs do not belong to this game folder.')
    # Root inputs and explicitly selected keys/IPA must always survive. Never
    # follow a symlink when deleting a cache, nor recursively remove saved games.
    protected = [ipa, keys, *[p.resolve() for p in game_dir.iterdir()
                              if p.is_file() and p.suffix.lower() in ('.xci', '.nsp', '.nsz', '.xcz')]]
    candidates = [game_dir / (title_id + '_build'), work]
    removed, retained = [], []
    for path in candidates:
        if not path.exists():
            continue
        if path.is_symlink() or path.resolve() != path:
            retained.append(str(path))
            continue
        if any(p == path or p.is_relative_to(path) for p in protected):
            retained.append(str(path))
            continue
        saved = False
        for child in path.rglob('*'):
            if child.is_dir() and child.name.lower() in ('save', 'saves', 'savedata') and any(child.iterdir()):
                saved = True
                break
        if saved:
            retained.append(str(path))
            continue
        try:
            shutil.rmtree(path)
            removed.append(str(path))
        except OSError as error:
            retained.append(str(path) + ': ' + str(error))
    if retained:
        print('Output completed. Some caches retained to protect inputs/saves or because cleanup failed: ' + '; '.join(retained), flush=True)
    else:
        print('Build caches, generated NSP copies, logs and private dependency environment removed. Original game packages, keys and finished app/package retained.', flush=True)
    return removed, retained
