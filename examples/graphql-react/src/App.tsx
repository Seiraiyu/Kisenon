import { type FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "urql";

// Auth is out of scope: every post and vote is made by this demo user.
const DEMO_USER_ID = 1;

export type Post = {
  id: string;
  rowId: number;
  title: string;
  text: string;
  points: number;
  createdAt: string;
  creator: { username: string };
  tags?: string[];
};
type PostsData = {
  posts: { edges: { node: Post }[]; pageInfo: { hasNextPage: boolean; endCursor: string | null } };
};

// `tags` only exists on the preview fork (migrations/002_post_tags.sql).
export const postsQuery = (withTags: boolean) => `
  query Posts($after: Cursor) {
    posts(first: 20, after: $after, orderBy: [CREATED_AT_DESC, PRIMARY_KEY_DESC]) {
      edges { node { id rowId title text points createdAt creator { username } ${withTags ? "tags" : ""} } }
      pageInfo { hasNextPage endCursor }
    }
  }`;
const VOTE = `
  mutation Vote($postId: Int!, $value: Int!) {
    vote(input: { postId: $postId, value: $value }) { result { id points } }
  }`;
const CREATE_POST = `
  mutation CreatePost($title: String!, $text: String!, $creatorId: Int!) {
    createPost(input: { post: { title: $title, text: $text, creatorId: $creatorId } }) { post { id } }
  }`;

export function App({ withTags = false }: { withTags?: boolean }) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const loadMore = (c: string) => setCursors((cs) => (cs.includes(c) ? cs : [...cs, c]));
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", fontFamily: "system-ui, sans-serif" }}>
      <h1>lireddit on Kisenon {withTags && <small>(preview branch)</small>}</h1>
      <CreatePost />
      {cursors.map((after, i) => (
        <Page key={after ?? "first"} after={after} withTags={withTags}
              isLast={i === cursors.length - 1} onLoadMore={loadMore} />
      ))}
    </main>
  );
}

function Page(props: {
  after: string | null;
  withTags: boolean;
  isLast: boolean;
  onLoadMore: (cursor: string) => void;
}) {
  const [{ data, fetching, error }] = useQuery<PostsData>({
    query: postsQuery(props.withTags),
    variables: { after: props.after },
  });
  if (error) return <p role="alert">{error.message}</p>;
  if (!data) return fetching ? <p>Loading…</p> : null;
  const { edges, pageInfo } = data.posts;
  const next = pageInfo.hasNextPage ? pageInfo.endCursor : null;
  return (
    <>
      {edges.map(({ node }) => <PostCard key={node.id} post={node} />)}
      {props.isLast && next && <LoadMore onVisible={() => props.onLoadMore(next)} />}
    </>
  );
}

// Infinite scroll: auto-loads when scrolled into view; still a real button.
function LoadMore({ onVisible }: { onVisible: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!ref.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => entries[0]?.isIntersecting && onVisible());
    io.observe(ref.current);
    return () => io.disconnect();
  }, [onVisible]);
  return <button ref={ref} onClick={onVisible}>Load more</button>;
}

function PostCard({ post }: { post: Post }) {
  const [, vote] = useMutation(VOTE);
  return (
    <article style={{ display: "flex", gap: 12, borderBottom: "1px solid #ddd", padding: "8px 0" }}>
      <div style={{ textAlign: "center", minWidth: 40 }}>
        <button aria-label={`upvote ${post.title}`}
                onClick={() => vote({ postId: post.rowId, value: 1 })}>▲</button>
        <div>{post.points}</div>
        <button aria-label={`downvote ${post.title}`}
                onClick={() => vote({ postId: post.rowId, value: -1 })}>▼</button>
      </div>
      <div>
        <h2 style={{ fontSize: 18, margin: 0 }}>{post.title}</h2>
        <small>by {post.creator.username}</small>
        {post.tags && <p>{post.tags.map((t) => <span key={t}>#{t} </span>)}</p>}
        <p>{post.text.slice(0, 160)}</p>
      </div>
    </article>
  );
}

function CreatePost() {
  const [{ fetching }, create] = useMutation(CREATE_POST);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const res = await create({ title, text, creatorId: DEMO_USER_ID });
    if (!res.error) {
      setTitle("");
      setText("");
    }
  }
  return (
    <form onSubmit={onSubmit} style={{ display: "grid", gap: 8, marginBottom: 16 }}>
      <input aria-label="title" placeholder="Title" value={title} required
             onChange={(e) => setTitle(e.target.value)} />
      <textarea aria-label="text" placeholder="Text" value={text} required
                onChange={(e) => setText(e.target.value)} />
      <button type="submit" disabled={fetching}>Create post</button>
    </form>
  );
}
