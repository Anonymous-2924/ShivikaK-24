# Vector Store Comparison

Default: **Qdrant** (embedded on-disk by default; server mode optional).

| Dimension | Qdrant | PostgreSQL + pgvector | Chroma | Supabase (pgvector) |
|---|---|---|---|---|
| Local setup | Embedded (pip) or Docker | Needs Postgres + extension | Embedded (pip) | Hosted/managed |
| No-server option | **Yes** (on-disk) | No | Yes | No (cloud) |
| Metadata filtering | **Rich** (typed payload filters) | SQL `WHERE` | Basic `where` | SQL `WHERE` |
| Hybrid search | Native sparse+dense support | Manual (FTS + vector) | Limited | Manual |
| Persistence | On-disk / server snapshots | Durable (RDBMS) | On-disk | Managed |
| Ops overhead (local) | **Low** | Medium–High | Low | Low (but cloud dep) |
| Multi-company metadata scale | Good | Good | OK (small) | Good |
| Deployment | Local → self-host → cloud | Self-host / managed | Local mostly | Cloud |

## Why Qdrant is the default here
1. **No mandatory server/Docker** for the Python app — the embedded on-disk
   mode fits a 16 GB Windows laptop and the "no Docker as a hard dependency"
   constraint, while server mode is one env change away.
2. **Strong typed metadata filtering**, which this project leans on heavily
   (company / FY / report type / content type / basis).
3. **A clean path to hybrid retrieval** and to self-hosting/cloud later.

This is not a claim that Qdrant is universally best. For a team already running
Postgres, **pgvector** consolidates infra and gives transactional metadata;
**Chroma** is great for quick local prototypes; **Supabase** suits a managed
cloud-first setup. The storage layer is abstracted (`src/storage/`) so another
store can be evaluated without rewriting the app.

See `docs/architecture_decisions.md` (ADR-002) for the decision record.
A benchmark harness can run the same corpus/queries across stores; measured
numbers only — none are fabricated here.
