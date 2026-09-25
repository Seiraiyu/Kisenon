-- Demo data: 200 users, 2,000 posts, 20,000 votes. Run after migrations/001_schema.sql.
INSERT INTO graphql_react.users (username, email)
SELECT 'user' || i, 'user' || i || '@example.com' FROM generate_series(1, 200) i;

INSERT INTO graphql_react.posts (title, text, creator_id, created_at)
SELECT
  'Post #' || i || ': ' || (ARRAY['Branching Postgres', 'GraphQL tips', 'React hooks',
                                  'Serverless SQL', 'Indexes explained'])[1 + i % 5],
  'Body of post ' || i || '. ' || repeat('Lorem ipsum dolor sit amet. ', 1 + i % 8),
  1 + (i * 7) % 200,
  now() - (i || ' minutes')::interval
FROM generate_series(1, 2000) i;

-- 20,000 distinct (user, post) pairs; ~80% upvotes. The trigger fills posts.points.
INSERT INTO graphql_react.updoots (user_id, post_id, value)
SELECT 1 + (n % 200), 1 + (n / 200 * 20 + n % 200) % 2000, CASE WHEN n % 5 = 0 THEN -1 ELSE 1 END
FROM generate_series(0, 19999) n;

ANALYZE graphql_react.users, graphql_react.posts, graphql_react.updoots;
