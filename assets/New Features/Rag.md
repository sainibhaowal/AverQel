> **Historical proposal:** this file records suggested or planned work, not current product behavior. Proposed endpoints, UI, status, and guarantees may never have been implemented; check the [current backend documentation index](../../backend/docs/README.md) before relying on it.


A real evaluation harness
You need a golden test set containing real documents and real questions, measuring:

- Recall@K
- MRR/nDCG
- Citation correctness
- Citation coverage
- Faithfulness/groundedness
- Abstention accuracy
- Latency and cost

Advanced query planning
Add optional:

- Query rewriting
- Multi-query retrieval
- Query decomposition
- Step-back questions
- Multi-hop retrieval
- Evidence verification

Hierarchical retrieval
Add parent-child chunks, document summaries, section summaries, and optional RAPTOR/PageIndex-style indexes for very long documents.

Full multimodal retrieval
Current OCR and Office conversion are useful, but they are not equivalent to understanding every chart, image, diagram, table, or slide visually. Add image/table representations only if your users need them.

Answer verification
The system should detect:

- Unsupported claims
- Missing citations
- Conflicting documents
- Low evidence coverage
- When it should say “not enough evidence”

Index lifecycle management
Production needs visible states for:

- Indexing
- Ready
- Failed
- Stale
- Reindexing
- Embedding-model migration
- Deleted-document cleanup
