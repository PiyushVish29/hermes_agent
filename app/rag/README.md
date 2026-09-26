# RAG boundary

RAG answers what information exists in explicitly approved documents. It is
separate from personal memory: indexed chunks live only in the configured RAG
SQLite database and are never passed to `MemoryManager` for persistence.

`RagManager` requires explicit `rag_index_roots`, validates every root and file
through `PathSecurityLayer`, excludes sensitive and unsupported files, chunks
documents, creates deterministic local embeddings, and returns source paths and
chunk indexes with retrieval results. Re-indexing upserts changed documents and
removes stale chunks. Deletion is an authorized RAG operation and does not
modify the memory database.
