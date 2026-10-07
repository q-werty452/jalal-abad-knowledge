# Local bot update readiness

Current bot data/index: `7602e001cb855a11` / `7602e001cb855a11`, 348 chunks, model `text-embedding-3-small`.
V4 staged data: `7fa44034af0e6322`, 667 chunks. Embedding operation estimate: 667 texts in 11 batches using `text-embedding-3-small`.

The local production bot was not synced because this task does not authorize paid embeddings. A sync without a matching index would remove semantic retrieval until rebuilding. The v4 data and contact audit were synced only to `v4/staging_bot` and passed parser checks.

The server archive requiring `knowledge/index/*` is not deployable yet. Build the embedding index and complete bot acceptance before packaging it.
