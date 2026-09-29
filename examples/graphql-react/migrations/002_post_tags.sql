-- Applied ONLY on the preview fork by `npm run preview-branch`.
ALTER TABLE graphql_react.posts ADD COLUMN tags text[] NOT NULL DEFAULT '{}';
UPDATE graphql_react.posts
SET tags = ARRAY[(ARRAY['postgres', 'graphql', 'react', 'branching', 'kisenon'])[1 + id % 5]];
