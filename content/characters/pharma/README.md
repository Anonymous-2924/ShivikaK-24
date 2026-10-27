# Advisor portraits — Pharmaceuticals

The game ships with **procedural placeholder portraits**: an animated SVG face
(`src/ui/components/AdvisorPortrait.tsx`) drawn in the department's color, with
four expressions (happy / neutral / worried / angry). No image files are
required to play.

## Dropping in real art later

To replace an advisor's placeholder with real illustration, add four images to
this folder using the convention below, then wire them up in
`AdvisorPortrait.tsx` (there is a clearly-marked `CUSTOM ART` hook at the top of
that file).

```
content/characters/pharma/<department-id>-happy.png
content/characters/pharma/<department-id>-neutral.png
content/characters/pharma/<department-id>-worried.png
content/characters/pharma/<department-id>-angry.png
```

`<department-id>` matches the `id` in `content/industries/pharma.json`
(`rnd`, `regulatory`, `sales`, `marketing`, `finance`).

Each advisor's `portraitPrompt` in the industry profile is a ready-made
image-generation prompt for producing that art.

Recommended: square images, 512×512, transparent or solid background,
consistent framing across the four expressions so they swap cleanly.
