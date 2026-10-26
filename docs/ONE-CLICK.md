# One-click all-in-one IPA (this fork)

Download and extract the **complete repository** from this fork. On an Apple
Silicon Mac, install and open full Xcode and accept its license first. Double-click
`一键生成完整IPA.command` in the root, then choose:

1. A folder containing **one game's** base NSP/XCI, its update and optional DLC.
2. Your own `prod.keys` file.
3. The folder for the resulting unsigned IPA.

The frontend installs missing build dependencies, runs the **current official**
`scripts/build_ipa_from_nsp.py`, validates the package, and writes the IPA,
SHA256 and a small provenance JSON file into your chosen output folder. Generated
IPAs have unique names; previous output is not overwritten. Renaming or moving
the source folder is fine if its internal structure stays intact.

The IPA contains the rewritten program, iOS shaders, font and RomFS, plus DLC
provided to the official pipeline. It uses NX's original app, controls and
packaging. **No ACNH Mobile runtime, shell assembly or external `.data` is used.**
Sign the complete IPA with your sideloading tool. These files are private outputs;
the launcher does not upload them or sign/install them on your phone.

## Games and registered versions

The list is read on each run from `dm/games/*/game.tsv`, using `title_id`, `name`
and the `build` rows (package tag and display version); it is never hardcoded to
Animal Crossing 3.0.3. To print the current list without installing dependencies:

```sh
python3 scripts/nx_one_click.py --list-games
python3 scripts/nx_one_click.py --list-games --json
```

A shipped profile records known builds, not certification of complete iOS
playability. Some games have only been tested on Mac; read each game's note in
`dm/games/<title ID>/README.md` for platform limits. The frontend takes the newest
version present, like the official CLI, but stops if it is not registered. Give
`--package vNNN` to select another registered version actually in your folder.
Update files without version tags follow the official scanner's inference;
extracted NSO build IDs remain checked by the official pipeline. If required
shader-source versions are absent or IDs differ, upstream may derive a profile
and report untested inputs. Do not treat that warning as tested compatibility.
Unknown games and other versions can still be attempted through the original
CLI; they are not added to the frontend's supported list.

## Command-line options

```sh
./一键生成完整IPA.command --game-dir '/path/to/game' \
  --keys '/path/to/prod.keys' --output-dir '/path/to/output' --language zh-Hans
```

The default language is `en-US`, matching the official script. Use `--language`
for another supported game language; unsupported language selections are rejected
by the official pipeline. Add `--plan` to inspect inputs without dependency
installation, building, notifications or cache changes.

Caches and logs are kept on the game drive: official `<title ID>_build/` plus
`.nxnative-one-click/` for dependencies and wrapper logs. Inputs and saves are
not deleted; a failure retains logs and any partial output for diagnosis. Reserve
roughly twice the input game size plus 10 GB, as for manual NX builds. Keep game
files and keys outside the source checkout. Never put your game data in Git.

## Upstream sync protection

The hourly workflow merges upstream, then restores the fork's pre-merge versions
of precisely these paths, including when upstream edited or deleted them:

- `一键生成完整IPA.command`
- `scripts/nx_one_click.py`
- `dm/local_one_click/` (frontend dependencies, picker, tests and sync helper)
- `docs/ONE-CLICK.md`
- `.github/workflows/sync-upstream.yml`
- `.github/workflows/local-one-click-tests.yml`

All other paths, including the official packer, `dm/games`, shaders, host code,
and upstream tools follow the normal merge. Other conflicts stop without a push.
The merge records upstream history; it does not reset or force-push the fork.
Keep the existing `UPSTREAM_SYNC_TOKEN` secret with Contents and Workflows write
permissions. Local file protection does not freeze upstream APIs: upstream
interface changes may require a frontend update. Tests can be run with:

```sh
python3 -m unittest discover -s dm/local_one_click/tests -v
```
