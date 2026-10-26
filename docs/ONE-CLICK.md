# One-click all-in-one IPA (this fork)

Download and extract the **complete repository** from this fork. On an Apple
Silicon Mac, install and open full Xcode and accept its license first. Double-click
`一键生成完整IPA.command` in the root, then choose:

1. A folder containing **one game's** base NSP/XCI, its update and optional DLC.
2. Your own `prod.keys` file.
3. The folder for the resulting unsigned IPA.

The frontend installs missing build dependencies, runs the **current official**
`scripts/build_ipa_from_nsp.py`, validates the package, and writes
only the complete IPA into your chosen output folder after a successful build. Generated
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
version present, like the official CLI. Registration is informational, not a
version whitelist: other updates and the base game alone are passed to the
official pipeline, which may derive a profile and omit build-specific fixes.
Give `--package vNNN` to select a package actually in your folder.
Update files without version tags follow the official scanner's inference;
extracted NSO build IDs remain checked by the official pipeline. If required
shader-source versions are absent or IDs differ, upstream may derive a profile
and report untested inputs. Do not treat that warning as tested compatibility.
Unknown games can still be surveyed through the original CLI. An unregistered
version is never relabeled as tested or added to the registered build list.

## Command-line options

```sh
./一键生成完整IPA.command --game-dir '/path/to/game' \
  --keys '/path/to/prod.keys' --output-dir '/path/to/output' --language zh-Hans
```

The default language is `en-US`, matching the official script. Use `--language`
for another supported game language; unsupported language selections are rejected
by the official pipeline. Add `--plan` to inspect inputs without dependency
installation, building, notifications or cache changes.

After the complete IPA passes ZIP and embedded-resource validation, the frontend
removes its generated extraction, rewrite, shader and compile caches, exported
XCI NSP copies, local dependency venv/tool cache and build logs. It does not
create checksum/provenance sidecar files. Your original game packages, keys and
complete IPA remain. A subsequent build recreates these generated files.

A failed/cancelled build retains caches and logs for diagnosis. Cleanup never
removes originals or known save folders. If keys, the IPA or a nonempty save
folder overlap a cleanup target, that target is retained with an explanation.
Unrelated user files and other games are not swept. Reserve roughly twice the
input game size plus 10 GB (plus XCI export space) for each build. Keep game
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

## Integrated XCI cartridges (base + updates + DLC)

The frontend reads the XCI secure partition and its encrypted CNMT metadata with
LibHac and your own keys; it does not infer the update version from the filename.
An integrated XCI is exported once as separate base, patch and DLC NSP inputs,
keeping every NCA unchanged. The original XCI is never modified. The official
pipeline then selects the newest update, layers it over the base, checks module
build IDs and builds its normal all-in-one IPA. External NSP updates/DLC beside
the XCI are also included. Keep one XCI / one game per selected folder.

Exported inputs and all official build caches stay under
`<game folder>/.nxnative-one-click/container-inputs/`. Allow additional free space
roughly equal to the XCI's secure content for the exported inputs, on top of the
normal extraction/build space. Retries after a failed build reuse these inputs when the
source and reader are unchanged. A successful build removes them. An incomplete export is not treated as ready.

`--plan` can inspect XCI contents without export when the metadata tool remains from an unfinished normal run. Missing keys, unreadable metadata, missing content and
multiple base applications fail explicitly rather than falling back to a guessed
v0 build. Integrated XCZ requires decompression to XCI first.
