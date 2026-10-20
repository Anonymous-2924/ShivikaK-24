# tools/datagen/

**Standalone** generator. No imports from `src/` — enforced by a ruff rule
in `pyproject.toml` and by a test in `tests/test_datagen_standalone.py`.

Writes to `generated_data/` (gitignored). You move files from there into
`data/inbox/` manually. The app never touches `generated_data/`.

Phase 2 fills this in. CLI contract:

```
python -m tools.datagen.generate --suppliers 500 --skus 2000 --seed 42
```

Must be deterministic given a seed. Deliberate mess (duplicate entities,
unit inconsistencies, OCR noise, contradictions, etc.) is logged to
`generated_data/REALISM_LOG.md`.
