// @vitest-environment node
// Smoke test against a real database: `DATABASE_URL=... npm test`. Skipped otherwise.
import { postgraphile } from "postgraphile";
import { describe, expect, it } from "vitest";
import preset from "../graphile.config.mjs";

describe.skipIf(!process.env.DATABASE_URL)("PostGraphile schema", () => {
  it("exposes the posts connection and the vote mutation", async () => {
    const pgl = postgraphile(preset);
    try {
      const { schema } = await pgl.getSchemaResult();
      expect(Object.keys(schema.getQueryType()!.getFields())).toContain("posts");
      expect(Object.keys(schema.getMutationType()!.getFields())).toEqual(
        expect.arrayContaining(["vote", "createPost"]),
      );
    } finally {
      await pgl.release();
    }
  });
});
