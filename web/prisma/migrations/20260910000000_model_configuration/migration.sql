CREATE TABLE "ModelConfiguration" (
  "id" INTEGER NOT NULL DEFAULT 1,
  "enabledModelIds" TEXT[] NOT NULL,
  "defaultModelId" TEXT NOT NULL,
  "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "ModelConfiguration_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "ModelConfiguration_singleton" CHECK ("id" = 1),
  CONSTRAINT "ModelConfiguration_enabled_default" CHECK (
    cardinality("enabledModelIds") > 0 AND "defaultModelId" = ANY("enabledModelIds")
  )
);
INSERT INTO "ModelConfiguration" ("id", "enabledModelIds", "defaultModelId")
VALUES (1, ARRAY['claude-haiku-4-5-20251001','claude-sonnet-5','claude-opus-5','claude-fable-5','gpt-4o-mini','gpt-4o','gpt-4.1-mini','gpt-4.1','gemini-flash-latest','gemini-pro-latest'], 'claude-haiku-4-5-20251001')
ON CONFLICT ("id") DO NOTHING;
