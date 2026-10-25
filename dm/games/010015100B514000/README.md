# Super Mario Bros. Wonder (`010015100B514000`)

Base game v0 (1.0.0, SDK 16.2.0) and update 1.2.1 (v327680, a new `main` build on SDK 16.2.12); the profile carries both builds and packs 1.2.1 by default. Nintendo EPD's engine (sead, agl), on NVN 55 (it requires 55.x with minor ≥ 15). Modules `main` and `sdk`. The first game of this repository, after Diablo II: Resurrected in d2r-mobile: much of the host was brought up on it. Plays on the iPhone. The README lists its IPA at about 4 GB.

## What it needs

| Setting | Where | Why |
|---|---|---|
| Resource heap +16 KB | [`patches.py`](patches.py) `CUTS`, v0 `main` `cd6e42ae…` at `main+0x1e62fc`, 1.2.1 `main` `ff773e90…` at `main+0x1cf9b0` | a resource heap came up about 0x70 bytes short; see [Memory](#memory) |
| 5 GB guest layout: `mem_reserve 0x140000000`, `mem_alias 0xB8000000`, `mem_stack 0x10000000`, `app_pool 0xCD500000` | [`game.tsv`](game.tsv) | 256 MB in front + 2.875 GB alias region + 256 MB stack region + 1.625 GB heap region: the game maps 1.75 GB of virtual address memory on demand into the alias region and asks for a 1.47 GB heap |
| `shader_versions v0 v327680` | `game.tsv` | the shader tables are the union of both versions, so packing either needs both NSPs |

No `dm/tools/sdk_patches.py` cut for its `sdk` builds (`3053b229…` v0, `e4bd58ca…` 1.2.1). No `render_cond`: a minute's boot counted 65,536 or more clears under render conditions, and the game needs none. No `pad_layout`: the virtual gamepad starts in the 2D layout.

## Versions

- v0 (1.0.0) and 1.2.1 (v327680). With the update layered over v0, unchanged files become APFS clones, so the merged RomFS adds only about 114 MB to the 3.5 GB base.
- 1.2.1 is a new `main` build (SDK 16.2.12). Its resource-heap cut was carried over from v0 with `dm/tools/nso_fnmap.py` (containing function `0x1e603c` → `0x1cf6f0`, identical after address masking; `ExpHeap::create` `0x4aac38` → `0x4c4a18`).
- 1.2.1 imports 28 SDK functions v0 did not, which the host answers: `nn::nfp` (amiibo, initialized at boot) finds none, `pl::IsRunningOnOunce` (is this a Switch 2) is false, `ec::ShowShopApplicationInformationForUpgrade` is a no-op, `account::PopOpenUsers` returns none and `aoc::CountAddOnContent` none. Mario only reads the count from `PopOpenUsers` and falls back to `TryOpenPreselectedUser` on 0, and counts add-on content only on a Switch 2 (`hle_sdk16.c`, `hle_account.c`, `hle_misc.c`).
- 1.2.1 compresses the NACP's title area (a u16 size, then raw deflate inflating to 32 entries of 0x300 bytes), which LibHac 0.19 does not decode; `nx_extract` and the NSP script do. Its patch NCA (key generation 17) makes hactool stop with `Invalid BKTR layout!`, which is why `nx_extract` uses LibHac.

## Memory

- The game reserves "virtual address memory" (1.75 GB in `System/HeapSize/*.HeapDef.byml`) and maps it into the alias region with `MapPhysicalMemory` on demand. With the alias region left after the node area too small, large resources were silently skipped and a null deref followed where they were used, also visible as `SetHeapSize` asking for much less than the pool. The 5 GB layout above fixed it.
- Its two modules are about 74 MB, and its heap request matches hardware with the host's 64 MB of "used" memory.
- **Current: every resource heap gets +16 KB.** Each resource gets its own `sead::ExpHeap` sized resource-size-table value + 0x1008 (`main+0x1e603c` → `ExpHeap::create` `main+0x4aac38`, v0). The table values are Nintendo's measured peaks with almost no margin (Yoshi's animation file `PlayerYoshiAnm` uses 99% of its budget). `Model/NpcCommonerA.bfres` in the opening course (Course900) came up about 0x70 bytes short: its last GPU chunk (MatBlock, 0x9000 bytes, 4 KB aligned, `main+0x4290c0`) fit, but the chunk's 0x598-byte descriptor did not; a buffer was then built on a null memory pool and the game crashed on a null read at `main+0x106f5c8`. The cut makes `mov x0,x23` → `add x0,x23,#0x4000` (the `ExpHeap::create` size argument).
- The single 128 MB NVN virtual memory pool (flag 0x200) is mapped onto one physical pool in one request, so the host aliases it (`hle_nvn.c`). Before, a failed `MapVirtual` gave a buffer with a null pool right after a scene change.
- How the heap was traced: probes on the gsys GPU allocator (`main+0x4290c0`) and the heap's `tryAlloc` (vtable slot +0x30); the `!xN` heap walk uses Mario's sead layout by default (`DM_PROBE_HEAP` `0,28,30,b0,c8`; [05, Probes](../../../docs/agents/05-debugging.md#probes-without-a-debugger-dm_probe)).

## Frame rate

- **Current:** 60 fps with a dynamic present interval. The game times every frame (`main+0xcfd24`); after a frame that ran past one vertical sync it sets present interval 2 for the next frame and sets its own time step to the interval (a float at `main+0x36ceff0`), so that frame catches up 2/60 s (Mario 1.2.1 on the iPhone). A user's 2-minute iPhone session switched 123 times, mostly for one frame.
- **Resolved:** in `display` mode those frames were shown for 16.7 ms and the game visibly jumped ahead ("sometimes the speed increases when jumping"). In `game` mode (the default since 2026-10-15) the display link keeps a frame whose period is over 25 ms on screen for its whole period (`g_link_hold_until` in `nvn_mtl.m`), and the 30 fps target waits until interval 2 has held for a full second (`nvn_game_fps` in `hle_nvn.c`), so one-frame switches no longer flip the display-link mode. `DM_TEST_PRESENT_LAG=90,30` (30 ms before every 90th present) makes Mario do this on the Mac; run it with `DM_WINDOW=1` to get the display link.
- `core_preempt` stays off: with it Mario's loader threads waited for busy decompression threads and its first frame moved from 0.6 to 2.9 s.
- The precise `SleepThread` (`sleep_precise`, found on Metroid Dread) took Mario's frame-time p95 from 19.7 to 18.4 ms.
- The spin-wait rewrite finds 175 loops in `main`; the store rule added one more in each build.

## Rendering

Game-specific findings; the general host changes they led to are listed under [Found on this game](#found-on-this-game).

- **Resolved: tall blue / textured panels flickering over the fountain.** Mario writes the same uniform slot twice in a row each frame (4 bytes of −1, then 16 bytes of wave coefficients). Without an intra-encoder barrier the writes occasionally landed in reverse order, the fountain's GPU wave simulation (a 512×1 RGBA16F texture, render → copy back → splash pass every frame) ran with −1 as its self coefficient, diverged to ±65504, and its vertex shader pushed the water surface to the top of the screen. How it was found ([05, Intermittent rendering glitches](../../../docs/agents/05-debugging.md#intermittent-rendering-glitches)): screenshots of frames 4430–4590 scored by a metric tuned to the glitch (long vertical straight edges in a sky region: ≈1.0 against ≈0.3), a control run, `DM_NVN_SKIP_FS` bisection, `DM_NVN_CBDUMP` showing byte-identical inputs, then `DM_NVN_T2T_TRACE` and a numpy re-implementation of the shader step: a coefficient of −1 instead of 1.81 explained every bad texel. `DM_NVN_BLIT_ORDER=0` reproduces it.
- **Resolved: the whole picture darker and more saturated (Mac and iPhone).** Mario's last pass writes the `RGBA8` swapchain texture through an `RGBA8_SRGB` view (`TextureViewSetFormat` 0x38 on a 0x25 texture); the host attached the base texture and stored the linear values unencoded (against a Switch screenshot, 0.55 → 0.26, 0.75 → 0.52). It is the only such view, 1 of 80 passes in a course frame.
- **Resolved: menus and dialogue boxes with no text.** Glyphs are rasterized on the CPU into a linear 2048×8192 R8 texture (flags IMAGE | LINEAR) in a CPU-visible pool; the font atlas is sampled with the swizzle (1, 1, 1, R), without which glyphs were white boxes.
- **Resolved: a black sky.** Four 64×1 RGBA16F sky colour ramps are CPU-written linear textures.
- **Resolved: a black band and flicker (iPhone; Mac runs of the scene looked clean).** Mario writes the byte 1 at `NVNcommandBuffer` +0x10 (`main+0x4da5c`, `main+0xb8dec`), which was the low byte of the host's `end`. Each write shrank the 512-byte material setup blocks, their recordings overflowed into host segments, `GetCommandMemoryUsed` returned 0, the game marked the setups empty and skipped calling them, and draws ran with the previous draw's vertex buffers (out-of-range vertices, NaN). `cmd_t` now reserves the byte (`nvn_flag10`).
- `NVNprogram` is smaller in Mario than the 0xC0 bytes in `nvn.h`: a 168-byte host record corrupted the next object (a crash in SHA-256 on the code address 0x16300), so `prog_t` stays 112 bytes.
- Mario calls `nvnProgramSetShaders` for some programs with a code address not yet mapped, so such a stage is hashed at its first draw.
- Its transient render targets are new texture objects every frame over the same storage, never finalized; without sharing host textures by `(pool, offset, description)` they leaked about 13 MB a frame.
- 8-bit index buffers in its full-screen passes and final copy; scissored zero clears of sub-rectangles of small targets (pyramid levels packed into 480×272, 256×256 and 64×36 targets); a depth clear scissored outside a pass, which the host still clears whole (`depth-stencil clear with a scissor or partial stencil mask, cleared whole`).
- Its 4×4 fallback textures (black, white, transparent, red) are filled with `nvnTextureWriteTexels`; since they upload from guest memory, materials that sample the default white texture got slightly brighter.
- Same-pass feedback draws `a7e5c6fd501cf21f` and `22a61cb1ec732aef` on its RG11B10F scene have shown no magenta blocks on the iPhone so far, so the profile lists no `feedback_snap`; snapshotting every shader raised submit time from 1.4 to 4.0 ms.
- Uniform updates inside a pass: attachment loads and stores unchanged by the deferred updates (its updates already covered what the draws read).
- It ships agl's BC4 block encoder `0544282c162305db` (the shader Tears of the Kingdom draws into a BC4 3D texture).
- Mario keeps NVN's GL depth mode (near = −w).

## Shaders

- 12,811 shaders in v0 and 16,268 across both versions; 16,266 compile. In v0 the main `bfsha` held only 4,888 of the 12,811.
- Containers: `Shader/*.bfsha` (BNSH), `Lib/agl/*.sarc` + `Shader/Secred.sarc` (agl BAHS `sharcb`), `Effect/*.esetb` (BNSH), `Layout/*.blarc` (BNSH) and two BNSH inside `main`. Groups in `game.tsv` (`SecredUber`, `agl`, `effect`, `layout`).
- Texture handles at `0x20 + 8 × slot` (the docs call it "Mario's binding layout"). 38% of texture reads go through handles stored in the game's uniform buffers (`fp_t_cb7_2A`: word 0x2A of c[7] = uniform slot 4), the binding kinds `tex_ubo` / `samp_ubo`.
- Many shaders share a control section and differ in code, so keys hash both.
- All 71 compute shaders have a header (magic `0x12345679`) and zero padding, instructions at +0x100. Fed from +0x30 at first, 12 compute shaders (particles, post effects) translated into an endless loop that hung the GPU at the first gameplay scene.
- 2 agl post-effect compute shaders still produce SPIR-V that SPIRV-Cross cannot parse (7 before the compute start-offset fix).
- Integer vertex inputs: 529 of 4,854 vertex shaders are re-translated with `uint` inputs (skinned models read bone indices as integer bits; without it every character was stretched into streaks).
- Pairs: 331 of 9,043 vertex / pixel pairs failed to link before `vs_pad` (the opening course used none of them; later levels did, about 11,500 failed builds in one 11-minute session). The offline link check: 8,712 linked / 331 failed before, 9,043 / 0 after, 14,603 / 0 for the v0 + 1.2.1 tables.
- Vertex format `RGB10A2SN` (0x69) → `MTLVertexFormatInt1010102Normalized`.

## Audio

- The `sdk` carries the audio renderer (SDK 16): the host switches it to CPU rendering with manual execution and drives it from a guest thread, no IPC ([Running the SDK's own renderer on the CPU](../../../docs/reference/audio.md#running-the-sdks-own-renderer-on-the-cpu)).
- **Resolved:** Mario updates the renderer twice in a row at start-up; with a real audio device the first frame came after both, and the light limiter later crashed on a null state pointer (`ApplyLightLimiterEffect`, `sdk+0x228494`). The `AudioRenderSystem::Update` hook renders a catch-up frame first when nothing was rendered since the last update.

## Services and survey

- `main` imported 1,107 symbols, 692 of which D2R never imported (`nn::audio` 197, `nn::hid` 48); 172 of the host's 186 hook names then existed in its `sdk`. Its SVC set was a subset of D2R's.
- NVN entry points: the loader (`main+0x1070910`) calls `GetProcAddress` per name and stores through the GOT (`nvn_slots_got.py`). It fetched 534 functions and called 236; 79 were new to the host (CommandBuffer 31, Texture 15, Buffer 10, Sampler 10).
- Its device setup checks `nvnDeviceGetInteger(API_MAJOR/MINOR)` and returns silently on a failed check.
- Files: `System/Resource/ResourceSizeTable.*.rsizetable` (RESTBL), `Font/*.bfarc`, `Mals/<Region><lang>.sarc`, `Voice/Resource/<Region><lang>`; `*.zs` is plain zstd with no dictionary; BYML version 7.
- Fonts: SDK 16 and `main` imports `ScalableFontEngineHelper::Decode`, so the shared font is served as BFTTF (marker + size + TTF). Controller-button icons in text come from the Nintendo-extension font (`GameMsg/Key.msbt`: U+E0E0–E0F0, U+E0AB–E0AE, U+E090–E097, U+E100/E101), served from `make_ext_font.py`'s `nintendo_ext.ttf`.
- **Resolved:** a crash indexing a per-core table with index −2 in Mario's font engine (`main+0x107dbc0`): threads created with ideal core −2 now resolve to the process default core.
- Focus handling mode 2 (focus notifications are sent). Mario never throws C++ exceptions.
- Ghidra: `main` (28 MB) took about 35 minutes to analyse, 138k functions.

## Mac routes

- `DM_KEYS="12:A,14:A,20:A,26:A,32:A"` reaches the opening course.

## Found on this game

General host changes first needed here; each applies to every game:

- **NVN on Metal basics** in [rendering.md](../../../docs/reference/rendering.md): [8-bit index widening](../../../docs/reference/rendering.md#8-bit-index-buffers), [texture swizzles](../../../docs/reference/rendering.md#texture-swizzle-through-swizzled-metal-views) (`nvn_fmt_to_mtl`, `img_fit`), [format-changing render-target views](../../../docs/reference/rendering.md#render-target-views-that-change-the-format) (`attach`, `present_raw_src`), [storage-shared transient targets](../../../docs/reference/rendering.md#transient-render-targets-shared-by-storage), [inline uniform updates as in-order copies](../../../docs/reference/rendering.md#inline-uniform-updates-as-ordered-gpu-copies) snapshotted at encode (`mtl_sub_update`), [CPU-written linear textures](../../../docs/reference/nvn-objects.md#linear-textures-in-cpu-visible-pools) on the pool buffer (`tex_linear`), [integer vertex inputs](../../../docs/reference/rendering.md#integer-vertex-inputs) (`int_inputs`, `vfmt_for_ct`), [intra-encoder barriers](../../../docs/reference/rendering.md#metal-4-does-not-order-operations-inside-one-encoder) (`blit_buf`, `DM_NVN_BLIT_ORDER`), [zero-filled new textures](../../../docs/reference/rendering.md#new-textures-start-as-zero) (`tex_zero_fill`), [scissored zero clears](../../../docs/reference/rendering.md#scissored-colour-clears) (`clear_rect_zero`), [vertex output padding from shader pairs](../../../docs/reference/shaders.md#pixel-shader-inputs-the-vertex-shader-does-not-write) (`vs_pad`, `shader_pairs.tsv`), [virtual pools aliased onto one physical pool](../../../docs/reference/nvn-objects.md#virtual-memory-pools-mapped-onto-one-physical-pool).
- **Binding layout and handles in uniform buffers** (`NVN_RB_TEXU` / `NVN_RB_SAMPU`): [04, section 3](../../../docs/agents/04-graphics.md#3-find-the-binding-layout-by-census); the compute code start: [Compute code with and without a header](../../../docs/reference/shaders.md#compute-code-with-and-without-a-header).
- **The SDK's audio renderer in-process** and the catch-up frame between two updates: [Running the SDK's own renderer on the CPU](../../../docs/reference/audio.md#running-the-sdks-own-renderer-on-the-cpu), [At least one rendered frame between two updates](../../../docs/reference/audio.md#at-least-one-rendered-frame-between-two-updates).
- **Resource heaps cut by build ID** (`CUTS` in `patches.py`), **memory partition** (`mem_init`), **virtual NVN pools**: [Per-resource heaps sized from Nintendo's measured peaks](../../../docs/reference/memory.md#per-resource-heaps-sized-from-nintendos-measured-peaks), [Partitioning the guest block between alias region, stacks and heap](../../../docs/reference/memory.md#partitioning-the-guest-block-between-alias-region-stacks-and-heap), [Virtual memory pools mapped onto one physical pool](../../../docs/reference/nvn-objects.md#virtual-memory-pools-mapped-onto-one-physical-pool).
- **Update imports diffed before the first run**, **fixed-address code gated by `module_t.build_id`**, **BFTTF shared font** (`hle_sdk16.c`), **the extension font**, **`GetCommandMemoryUsed` counting host segments**, **`NVNcommandBuffer` +0x10** (`nvn_flag10`), **`prog_t` size**: [A game update imports SDK calls the base game did not](../../../docs/reference/services.md#a-game-update-imports-sdk-calls-the-base-game-did-not), [Code inherited from another title at fixed addresses](../../../docs/reference/services.md#code-inherited-from-another-title-at-fixed-addresses), [Shared font address: BFTTF header or bare TTF](../../../docs/reference/services.md#shared-font-address-bfttf-header-or-bare-ttf), [Nintendo-extension glyphs for button icons](../../../docs/reference/services.md#nintendo-extension-glyphs-for-button-icons), [What `GetCommandMemoryUsed` counts](../../../docs/reference/nvn-objects.md#what-getcommandmemoryused-counts), [Inlined SDK code writes into `NVNcommandBuffer` +0x10](../../../docs/reference/nvn-objects.md#inlined-sdk-code-writes-into-nvncommandbuffer-0x10), [Host records must fit the game's SDK object sizes](../../../docs/reference/nvn-objects.md#host-records-must-fit-the-games-sdk-object-sizes).
- **Exclusive windows** (fall-through exit first, Mario had 82): [Exit stub order in exclusive windows](../../../docs/reference/rewriter.md#exit-stub-order-in-exclusive-windows). **Ideal core −2**: [Ideal core −2 resolves to the process default core](../../../docs/reference/threads.md#ideal-core-2-resolves-to-the-process-default-core).
- **Present-interval holds** (`g_link_hold_until`, `nvn_game_fps`): [Frames of a dynamic present interval held on screen and at the acquire](../../../docs/reference/frame-rate.md#frames-of-a-dynamic-present-interval-held-on-screen-and-at-the-acquire).
- **Glitch detector before bisection**: [05, Intermittent rendering glitches](../../../docs/agents/05-debugging.md#intermittent-rendering-glitches); **offline pipeline link check**: [05](../../../docs/agents/05-debugging.md#offline-pipeline-link-check).

## Open

- On the Mac, Mario's menu and dialogue text render blank (fine on the iPhone), per development.md's known gaps.
- Why the resource heap is short is not known (`patches.py`: every allocation size before that block is set by game code and data); Breath of the Wild's identical failure came from host record sizes, and whether Mario's chunk is sized the same way is not checked yet.
- dm/games/README.md says the heap check turns "Wonder's 1.44 GB" request into a 0xc0000000 alias region; 03 says it asks for 1.47 GB, and the profile's alias region is 0xB8000000.
- Several addresses in 02 and 03 (`main+0x1070910`, `main+0x107dbc0`, `main+0x4da5c`, `main+0xb8dec`, `main+0xcfd24`, `main+0x36ceff0`) do not name their build; the present-interval ones are from 1.2.1.
- 2 agl post-effect compute shaders do not translate.
