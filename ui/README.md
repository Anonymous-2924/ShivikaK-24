# ui/

Phase 8 target. React Three Fiber + Three.js. Not Streamlit — Streamlit
cannot do the fly-through.

Scaffolding is intentionally deferred: picking a Vite/Next.js setup before
the API shape is settled would be premature. Phase 7 locks the API; this
directory gets wired then.

## Reminders for Phase 8

- Edges rendered as instanced curved geometry, not line segments.
- Hierarchical edge bundling — do it properly, this is the look.
- Layout computed OFFLINE during graph build, shipped as a positions file.
- Bloom post-processing pass.
- LOD collapsing distant nodes into aggregate blobs.
- States: Ambient (hero) and Query (propagation with hop pauses, camera
  dollies along the path).
- Right column: ranked SKU risk list, live-sorts as propagation lands.
- Left column: supplier sparklines from the numeric track.
- Evidence drawer: click any edge → source span + confidence + method.
- As-of date slider → replay historic graph using edge temporal validity.
