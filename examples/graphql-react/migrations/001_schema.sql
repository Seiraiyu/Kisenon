-- graphql-react schema, adapted from benawad/lireddit (MIT, see NOTICE).
-- Re-runnable: drops and recreates the graphql_react schema.
DROP SCHEMA IF EXISTS graphql_react CASCADE;
CREATE SCHEMA graphql_react;

CREATE TABLE graphql_react.users (
  id         int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  username   text NOT NULL UNIQUE,
  email      text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE graphql_react.posts (
  id         int GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title      text NOT NULL,
  text       text NOT NULL,
  points     int  NOT NULL DEFAULT 0,
  creator_id int  NOT NULL REFERENCES graphql_react.users(id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON graphql_react.posts (creator_id);
CREATE INDEX ON graphql_react.posts (created_at);

-- lireddit's "updoot": one vote (+1 / -1) per user per post.
CREATE TABLE graphql_react.updoots (
  user_id int NOT NULL REFERENCES graphql_react.users(id),
  post_id int NOT NULL REFERENCES graphql_react.posts(id) ON DELETE CASCADE,
  value   int NOT NULL CHECK (value IN (-1, 1)),
  PRIMARY KEY (user_id, post_id)
);
CREATE INDEX ON graphql_react.updoots (post_id);

-- posts.points is maintained by trigger, never written by the app.
CREATE FUNCTION graphql_react.updoots_points() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE', 'DELETE') THEN
    UPDATE graphql_react.posts SET points = points - OLD.value WHERE id = OLD.post_id;
  END IF;
  IF TG_OP IN ('INSERT', 'UPDATE') THEN
    UPDATE graphql_react.posts SET points = points + NEW.value WHERE id = NEW.post_id;
  END IF;
  RETURN NULL;
END $$;
CREATE TRIGGER updoots_points AFTER INSERT OR UPDATE OR DELETE ON graphql_react.updoots
  FOR EACH ROW EXECUTE FUNCTION graphql_react.updoots_points();

-- Exposed as the `vote` mutation. Auth is out of scope: every vote is cast by
-- the demo user (id 1).
CREATE FUNCTION graphql_react.vote(post_id int, value int) RETURNS graphql_react.posts
LANGUAGE sql VOLATILE AS $$
  INSERT INTO graphql_react.updoots (user_id, post_id, value)
  VALUES (1, vote.post_id, vote.value)
  ON CONFLICT (user_id, post_id) DO UPDATE SET value = EXCLUDED.value;
  SELECT * FROM graphql_react.posts WHERE id = vote.post_id;
$$;
