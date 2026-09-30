# Vectors in Postgres

Kisenon ships Postgres 17 with the pgvector extension. A `vector(384)` column stores
an embedding; an HNSW index with `vector_cosine_ops` makes nearest-neighbour search
fast. The `<=>` operator returns cosine distance, so `1 - (a <=> b)` is similarity.

Because vectors live next to ordinary rows, one SQL query can filter by metadata,
join to other tables and rank by similarity. Branching a database also branches its
embeddings, which makes it safe to test a new chunking strategy on a fork.
