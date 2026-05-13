UPDATE "users" SET "name" = COALESCE("name", 'unknown') WHERE "name" IS NULL;
ALTER TABLE "users" ALTER COLUMN "name" SET NOT NULL;
