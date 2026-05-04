# Aether Forge — video sources

Remotion sources for the videos embedded in the docs-site (`docs-site/public/videos/`).
Each composition renders to an MP4 in `out/`, which is then copied into
`docs-site/public/videos/` and referenced from the relevant `.mdx` page.

> **History.** The first ~27 videos in this project (`00-hero` through
> `29-two-agent-marketplace`) were rendered from a `video/` directory
> referenced in [`docs/prd/aether-forge-prd-v0.18.0.md`](../docs/prd/aether-forge-prd-v0.18.0.md)
> that was never committed to the repo. This `videos-src/` directory is
> the first time the source has lived in-tree. If you're adding a new
> video, start here — the canonical style guide below was reverse-engineered
> by extracting reference frames from `00-hero`, `21-cli`, and
> `28-python-sdk`.

## Quick start

```bash
cd videos-src
npm install
npm run dev                     # opens Remotion Studio at http://localhost:3000
npm run render:all              # renders all 3 (~3 minutes total)
npm run render:extending        # just the extending video
npm run render:getting-started  # just the getting-started video
npm run render:python-sdk       # just the python-sdk video
```

After rendering, copy the MP4 into `docs-site/public/videos/` and embed
it from the relevant `.mdx` page (see existing usages of `<video src=...>`).

## Compositions

| Composition ID | Output | Duration | Embedded in |
|---|---|---|---|
| `ExtendingFramework` | `out/30-extending.mp4` | 25 s | `docs-site/.../guides/extending.mdx` |
| `GettingStarted` | `out/31-getting-started.mp4` | 31 s | `docs-site/.../getting-started.mdx` |
| `PythonSDK` | `out/32-python-sdk.mp4` | 26.5 s | `docs-site/.../reference/python-sdk.mdx` |

---

# Style guide (canonical)

Every Aether Forge video must follow these rules. They were derived by
inspecting the existing videos frame-by-frame and codifying the common
elements. **If a new video diverges from this, it doesn't ship.**

## 1. Hard rules — never break

- **Resolution & framerate**: 1920×1080, 60 fps. Match every existing
  video's encoding (h264 / aac).
- **Background**: pure black `#000000`. *Not* `#0a0a0a` — the docs-site
  wrapper is `#0a0a0a` but the video itself is true black so the
  embedded `<video>` blends seamlessly.
- **Palette**: pure monochrome. Never use red accents, never use
  decorative gradients. Code-block syntax tinting is the only
  exception (cyan keywords, green strings, gray comments, amber type
  names).
- **Fonts**: Inter (Google Fonts) for everything except code; JetBrains
  Mono for code. Both pre-loaded in `shared.tsx`.
- **Outro**: every video ends on the canonical `OutroScene` from
  `shared.tsx`. The end card is identical across the project — knot
  logo + AETHER / FORGE wordmark + `github.com/HeyElsa/aether-forge`
  pill + "Spec first. Real money. Production grade." + tiny
  "by [elsa-mark]". Do not customize it per-video.

## 2. Title scene anatomy

The title is the first ~3 seconds. Use `TitleScene` from `shared.tsx`:

```tsx
<TitleScene
  titleLines={["GET", "STARTED"]}
  tagline="Idea to governed, testable agent in 90 seconds"
/>
```

| Element | Spec |
|---|---|
| Knot logo | `forge-logo.svg`, white, 140×140 px, top |
| Title | Two-line uppercase, Inter weight **200** (thin), letter-spacing **8px**, font-size **130** (or **104** if it doesn't fit at 130) |
| Tagline | Inter weight 400, gray (`MUTED`), font-size 32, centered |
| Animation | Stagger fade-in: logo → title (0.4s delay) → tagline (0.8s delay) |

Reference frames (existing videos): `21-cli` opens with "THE FORGE / CLI".
`03-agent-generation` opens with "AGENT / GENERATION". Match that exactly.

## 3. Content scene anatomy

Use `ContentScene` from `shared.tsx`:

```tsx
<ContentScene kicker="Step 1" subtitle="Import the extension Protocols">
  <CodeBlock filename="my_extension.py" source={...} />
</ContentScene>
```

| Element | Spec |
|---|---|
| Kicker | Tiny uppercase, Inter weight 600, letter-spacing **4px**, color `MUTED` (gray). Never red. |
| Subtitle | Inter weight 600, font-size 44, white |
| Body | A `CodeBlock`, `ShellOutput`, or any custom React. Padded 100×120 px from edges. |
| Animation | Single fade-in for the caption; body components handle their own animations (typewriter for code). |

## 4. Code blocks

Use `CodeBlock` for typewriter-revealed source. Use `ShellOutput` for
terminal output that appears at once.

```tsx
<CodeBlock
  filename="src/strategy/coinbase_source.py"
  charsPerSecond={80}            // tune per scene length
  fontSize={30}                  // 24-30 typical
  source={`from aether_forge import DataSource, DataResult`}
/>
```

| Style detail | Value |
|---|---|
| Background | `#0a0a0a` (slightly lighter than scene bg) |
| Border | 1px `#1f2937` |
| Radius | 14 px |
| Shadow | `0 18px 60px rgba(0,0,0,0.55)` |
| Filename header | Inter, 20px, gray |
| Cursor | Blinks at end while typewriter still typing |

Heuristic syntax tinting (no real lexer):
- Keywords (`from`, `import`, `class`, `def`, `return`, etc.) → cyan
- Strings (`"..."`) → green
- Comments (`# ...`) → gray
- Capitalized identifiers → amber (treated as type names)

## 5. End card (canonical)

Every video ends on the same end card via `<OutroScene />` (no props).
The card layout is locked — do not modify per-video:

```
            [knot logo]

           AETHER
           FORGE

  ┌──────────────────────────────────┐
  │  github.com/HeyElsa/aether-forge │
  └──────────────────────────────────┘

   Spec first. Real money. Production grade.

              by  [elsa-mark]
```

Implementation: `OutroScene` in `src/shared.tsx`. Sequence in your
composition: `<Series.Sequence durationInFrames={240} name="Outro"><OutroScene /></Series.Sequence>`.

## 6. Length convention

| Video kind | Target |
|---|---|
| Feature walkthrough (single concept) | 25–30 s |
| Multi-step guide | 30–35 s |
| Hero / brand reel | 60–90 s |

Per-scene: 3 s for title, 4–8 s per content scene, 4 s for outro. Use
`Series.Sequence` durationInFrames at 60 fps (so 3 s = 180 frames).

## 7. File numbering convention

Existing videos are numbered `00-hero` through `32-python-sdk`. New
videos get the **next free integer** with a descriptive slug:

```
docs-site/public/videos/33-my-new-video.mp4
```

Match this in `package.json` (`render:my-new-video` script) and
`Root.tsx` (`<Composition id="MyNewVideo" ... />`).

---

# How to add a new video

1. **Pick a number + name.** Next free is `33-`.
2. **Create the composition file** at
   `src/compositions/MyComposition.tsx`. Start by copying the
   smallest existing one (`PythonSDK.tsx`) as a template — it shows
   the `Series` of scenes pattern with the canonical title + content +
   outro.
3. **Use only `shared.tsx` primitives** — `TitleScene`, `ContentScene`,
   `OutroScene`, `CodeBlock`, `ShellOutput`, `Wordmark`. If a scene
   needs something genuinely new, add it to `shared.tsx` (don't
   one-off it in your composition).
4. **Register** in `src/Root.tsx` with a `<Composition id=… />`. The
   `durationInFrames` must equal the sum of your `Series.Sequence`
   durations.
5. **Add render script** in `package.json`:
   `"render:my-name": "remotion render src/index.tsx MyComposition out/33-my-name.mp4 --concurrency=4"`.
6. **Render**: `npm run render:my-name`.
7. **Verify visually**: extract the title and outro frames with ffmpeg
   and compare against `00-hero`, `21-cli`, or `28-python-sdk`. They
   should be visually indistinguishable in style.

   ```bash
   ffmpeg -ss 2 -i out/33-my-name.mp4 -vframes 1 /tmp/title.png
   ffmpeg -ss $(($DURATION-2)) -i out/33-my-name.mp4 -vframes 1 /tmp/outro.png
   ```

8. **Copy the MP4** to `docs-site/public/videos/33-my-name.mp4`.
9. **Embed** in the relevant `.mdx`:

   ```mdx
   <video src="/videos/33-my-name.mp4" controls playsInline
     style={{width:'100%',aspectRatio:'16/9',background:'#0a0a0a',
             borderRadius:12,marginTop:16,marginBottom:16,display:'block'}}
     preload="metadata" />
   ```

10. **Commit both** the composition source and the rendered MP4.
    Remotion is deterministic, so the MP4 is reproducible from the
    source — but committing it avoids forcing every contributor to
    re-render.

---

# Don'ts

- **Don't** add red, blue, or any accent color to title/outro/kickers.
  The existing 27 videos are pure monochrome. Code syntax colors are
  the only exception.
- **Don't** customize the end card per-video. It's identical across
  every video for brand consistency.
- **Don't** use CSS `transition:` or `animation:` — Remotion will not
  render them. Use `useCurrentFrame()` + `interpolate()` /
  `spring()`. (See `videos-src/`'s `remotion-best-practices` skill or
  the `shared.tsx` `fadeIn` helper.)
- **Don't** use Tailwind `animate-*` class names — same reason.
- **Don't** use per-character opacity for code reveals — use string
  slicing via the `typewriter()` helper. The existing `CodeBlock`
  already does this correctly.
- **Don't** load fonts inside a component body — they're loaded once
  at module top of `shared.tsx`. Add weights there if you need them.
- **Don't** commit `node_modules/` or `out/`. They're gitignored.

---

# Shared primitives — what's in `shared.tsx`

| Export | Type | Purpose |
|---|---|---|
| `TitleScene` | Component | Knot logo + 2-line wordmark + tagline. The opening 3 s of every video. |
| `ContentScene` | Component | Wraps a kicker + subtitle + body in the canonical padding/layout. |
| `OutroScene` | Component | The canonical end card. Takes no props. |
| `SceneCaption` | Component | The kicker + subtitle pair (used inside `ContentScene`). |
| `Wordmark` | Component | Two-line uppercase thin-weight typography (used by both `TitleScene` and `OutroScene`). |
| `CodeBlock` | Component | Typewriter-revealed code with filename header, syntax tinting, blinking cursor. |
| `ShellOutput` | Component | Terminal output (no typewriter). Supports `prompt` + `text` + `color` per line. |
| `TypedLine`, `CursorBlink` | Components | Lower-level primitives used by `CodeBlock`. |
| `fadeIn(frame, fps, delay, dur)` | Helper | Returns a 0–1 spring value for opacity / translateY. |
| `typewriter(text, frame, fps, cps)` | Helper | Returns a substring length proportional to elapsed frames. |
| `BG`, `FG`, `MUTED`, `KEYWORD`, `STRING`, `COMMENT`, `TYPENAME`, `SUCCESS`, `ACCENT` | Constants | Palette. `ACCENT` is aliased to `MUTED` for backward compat — never use it for visible accents. |
| `interFamily`, `monoFamily` | Constants | Loaded Google Font family strings. |

Static assets in `public/`:

| File | Origin | Use |
|---|---|---|
| `forge-logo.svg` | `docs-site/public/logo.svg` (knot, white-fill) | Title scene + outro |
| `elsa-mark.svg` | `docs-site/public/elsa-logo.svg` (small Elsa wordmark, multi-color) | Outro "by [elsa]" |

---

# Reference

- Existing videos: `docs-site/public/videos/00-hero.mp4` through
  `32-python-sdk.mp4`.
- v0.18.0 PRD describing the original (uncommitted) video setup:
  [`docs/prd/aether-forge-prd-v0.18.0.md`](../docs/prd/aether-forge-prd-v0.18.0.md).
- Remotion docs and best practices: see the `remotion-best-practices`
  Claude Code skill (used to scaffold this directory) or
  https://www.remotion.dev/docs.

---

# What's not committed

- `node_modules/` (run `npm install`)
- `out/` (rendered outputs — copy to `docs-site/public/videos/` and
  commit those instead)
