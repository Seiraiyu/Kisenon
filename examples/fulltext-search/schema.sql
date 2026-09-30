-- fulltext-search schema. Re-runnable: drops and recreates schema fulltext_search.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP SCHEMA IF EXISTS fulltext_search CASCADE;
CREATE SCHEMA fulltext_search;

CREATE TABLE fulltext_search.articles (
  id    int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title text NOT NULL,
  body  text NOT NULL,
  -- Title words weigh more (A) than body words (B). Kept in sync by Postgres, no trigger.
  tsv   tsvector GENERATED ALWAYS AS (
          setweight(to_tsvector('english', title), 'A') ||
          setweight(to_tsvector('english', body), 'B')
        ) STORED
);

CREATE INDEX articles_tsv_gin    ON fulltext_search.articles USING gin (tsv);
CREATE INDEX articles_title_trgm ON fulltext_search.articles USING gin (title gin_trgm_ops);
