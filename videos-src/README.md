# Aether Forge — video sources

Remotion sources for the videos embedded in `docs-site/`. Each
composition renders to an MP4 in `out/`, which is then copied into
`docs-site/public/videos/`.

## Why this lives here

The repo previously shipped only the rendered MP4 outputs (under
`docs-site/public/videos/`) without source. This directory restores the
sources so contributors can re-render existing videos or add new ones
when docs change.

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

## Compositions

| Composition ID | Output | Duration | Embedded in |
|---|---|---|---|
| `ExtendingFramework` | `out/30-extending.mp4` | 25 s | `docs-site/.../guides/extending.mdx` |
| `GettingStarted` | `out/31-getting-started.mp4` | 31 s | `docs-site/.../getting-started.mdx` |
| `PythonSDK` | `out/32-python-sdk.mp4` | 26.5 s | `docs-site/.../reference/python-sdk.mdx` |

## Shared primitives

`src/shared.tsx` exports the reusable scene types and style tokens
every composition uses: `TitleScene`, `ContentScene`, `OutroScene`,
`SceneCaption`, `CodeBlock`, `ShellOutput`, `TypedLine`,
`CursorBlink`, helpers (`fadeIn`, `typewriter`), palette constants,
and the loaded font families. Define new scenes once there if more
than one composition needs them.

## Adding a new composition

1. Create `src/compositions/MyComposition.tsx` exporting a React
   component.
2. Register it in `src/Root.tsx` with a `<Composition id=… />` entry.
3. Add a `render:<name>` script to `package.json`.
4. `npm run render:<name>` writes to `out/`.
5. Copy the MP4 into `docs-site/public/videos/` and reference it from
   the relevant `.mdx`.

## Style

- 1920×1080, 60 fps (matches existing videos in the repo)
- Dark background `#0a0a0a` (matches docs-site `<video>` style)
- Inter for headings, JetBrains Mono for code (Google Fonts)
- Outro: `by [Elsa logo]` (white variant on dark) — see `OutroScene` in
  `src/compositions/ExtendingFramework.tsx` for the canonical pattern

## What's not committed

- `node_modules/` (run `npm install`)
- `out/` (rendered outputs — copy to `docs-site/public/videos/` and
  commit those instead)
