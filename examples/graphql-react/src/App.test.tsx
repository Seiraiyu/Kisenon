import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { type Client, Provider } from "urql";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fromValue, never } from "wonka";
import { App, type Post } from "./App";

const post = (n: number, extra: Partial<Post> = {}) => ({
  __typename: "Post", id: `P${n}`, rowId: n, title: `Post ${n}`, text: "body",
  points: n, createdAt: "2026-01-01T00:00:00Z", creator: { __typename: "User", username: "user1" },
  ...extra,
});
const page = (posts: object[], hasNextPage: boolean) => ({
  posts: {
    __typename: "PostConnection",
    edges: posts.map((node) => ({ __typename: "PostEdge", node })),
    pageInfo: { __typename: "PageInfo", hasNextPage, endCursor: hasNextPage ? "c1" : null },
  },
});

type Req = { query: { loc: { source: { body: string } } }; variables: unknown };

function mockClient(data: object) {
  return {
    executeQuery: vi.fn((_req: Req) => fromValue({ data })),
    executeMutation: vi.fn((_req: Req) =>
      fromValue({ data: { vote: { result: { id: "P1", points: 2 } } } })),
    executeSubscription: vi.fn(() => never),
  };
}

function renderApp(client: ReturnType<typeof mockClient>, withTags = false) {
  return render(
    <Provider value={client as unknown as Client}>
      <App withTags={withTags} />
    </Provider>,
  );
}

afterEach(cleanup);

describe("App", () => {
  it("renders the feed and loads the next page with the end cursor", () => {
    const client = mockClient(page([post(1), post(2)], true));
    renderApp(client);
    expect(screen.getByText("Post 1")).toBeTruthy();
    fireEvent.click(screen.getByText("Load more"));
    const vars = client.executeQuery.mock.calls.map(([req]) => req.variables);
    expect(vars).toContainEqual({ after: "c1" });
  });

  it("sends the vote mutation with the post's row id", () => {
    const client = mockClient(page([post(1)], false));
    renderApp(client);
    fireEvent.click(screen.getByLabelText("upvote Post 1"));
    expect(client.executeMutation.mock.calls[0]?.[0].variables).toEqual({ postId: 1, value: 1 });
    expect(screen.queryByText("Load more")).toBeNull();
  });

  it("asks for and shows tags on the preview branch", () => {
    const client = mockClient(page([post(1, { tags: ["postgres"] })], false));
    renderApp(client, true);
    expect(screen.getByText("#postgres")).toBeTruthy();
    expect(client.executeQuery.mock.calls[0]?.[0].query.loc.source.body).toContain("tags");
  });
});
