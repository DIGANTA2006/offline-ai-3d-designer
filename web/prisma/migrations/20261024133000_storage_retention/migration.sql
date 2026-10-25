ALTER TABLE "Project"
  ADD COLUMN "isImportant" BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE "ProjectVersion"
  ADD COLUMN "isProtected" BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX "Project_userId_isImportant_createdAt_idx"
  ON "Project"("userId", "isImportant", "createdAt");
