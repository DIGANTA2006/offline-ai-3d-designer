ALTER TABLE "User" ADD COLUMN "hardDeleteAt" TIMESTAMP(3);
CREATE INDEX "User_hardDeleteAt_idx" ON "User"("hardDeleteAt");