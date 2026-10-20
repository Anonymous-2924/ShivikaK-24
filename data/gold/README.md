# data/gold/

Hand-verified critical tables that bypass extraction entirely and are
trusted at confidence 1.0 during graph build.

## Format

Each gold table is three files sharing a basename:

```
<basename>.parquet          # the data, typed
<basename>.schema.json      # column names, dtypes, units, period, provenance
<basename>.sha256           # checksum of the .parquet, verified at ingest
```

## schema.json shape

```json
{
  "basename": "acme_bom_2026q3",
  "entity_type": "DataTable",
  "linked_entity": "Supplier:ACME",       // optional; graph will build has_financials / contains edges
  "columns": [
    {"name": "part_number", "dtype": "string", "role": "identifier"},
    {"name": "qty_per_unit", "dtype": "float64", "unit": "each", "role": "quantity"},
    {"name": "unit_cost_usd", "dtype": "float64", "unit": "USD", "role": "price"}
  ],
  "period": {"valid_from": "2026-07-01", "valid_to": "2026-09-30"},
  "provenance": "ACME ERP export, verified by L. Khanna 2026-10-18",
  "notes": "replaces the extracted version from docs/acme_bom.pdf which lost merged-cell headers"
}
```

## Checksum file

Plain text, one line:

```
<64-hex-sha256>  <basename>.parquet
```

Verified on every ingest run; a mismatch fails the ingest loudly rather than
silently falling back to the parsed version.

## Empty on delivery

No files are shipped here. Add them as you verify critical tables.
