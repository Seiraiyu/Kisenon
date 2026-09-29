// PostGraphile v5 config. `npm run server` serves main; `npm run preview-branch`
// starts a second copy with DATABASE_URL/PORT pointed at the fork.
import { PgSimplifyInflectionPreset } from "@graphile/simplify-inflection";
import { makePgService } from "postgraphile/adaptors/pg";
import { PostGraphileAmberPreset } from "postgraphile/presets/amber";

/** @type {GraphileConfig.Preset} */
const preset = {
  extends: [PostGraphileAmberPreset, PgSimplifyInflectionPreset],
  pgServices: [
    makePgService({
      connectionString: process.env.DATABASE_URL,
      schemas: ["graphql_react"],
    }),
  ],
  grafserv: { port: Number(process.env.PORT ?? 5678), graphiql: true },
};

export default preset;
