import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const here = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(here, "../src/lib/billing/subscription-policy.ts");
const source = readFileSync(sourcePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
const scratchDir = mkdtempSync(join(tmpdir(), "subscription-policy-test-"));

try {
  const compiledPath = join(scratchDir, "subscription-policy.cjs");
  writeFileSync(compiledPath, compiled.outputText, { encoding: "utf8", flag: "wx" });
  const policy = require(compiledPath);

  assert.equal(policy.hasActiveProSubscription({ tier: "PRO", status: "ACTIVE" }), true);
  assert.equal(policy.hasActiveProSubscription({ tier: "PRO", status: "PAST_DUE" }), false);
  assert.equal(policy.hasActiveProSubscription({ tier: "PRO", status: "HALTED" }), false);
  assert.equal(policy.hasActiveProSubscription({ tier: "FREE", status: "ACTIVE" }), false);
  assert.equal(policy.hasActiveProSubscription(null), false);
  assert.equal(policy.hasActiveProSubscription(undefined), false);

  assert.equal(policy.hasPaidFeatureAccess("ADMIN", null), true, "admin access does not require a subscription");
  assert.equal(policy.hasPaidFeatureAccess("USER", { tier: "PRO", status: "ACTIVE" }), true);
  assert.equal(policy.hasPaidFeatureAccess("USER", { tier: "PRO", status: "CANCELLED" }), false);
  assert.equal(policy.hasPaidFeatureAccess("USER", { tier: "FREE", status: "ACTIVE" }), false);
  assert.equal(policy.hasPaidFeatureAccess("USER", null), false);

  console.log("PASS: shared Pro/Admin entitlement policy");
} finally {
  rmSync(scratchDir, { recursive: true, force: true });
}
