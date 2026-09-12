import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../src/money.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 },
});
const { money } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`);

test("missing or invalid case amounts remain unavailable instead of crashing or becoming zero", () => {
  for (const value of [undefined, null, "", " ", "1.25", "invalid", 1.25, NaN, Infinity, {}, true, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(money(value), "Unavailable");
  }
});

test("integer centavos retain exact digits, currency and sign", () => {
  assert.equal(money(0), "MXN $0.00");
  assert.equal(money(123456), "MXN $1,234.56");
  assert.equal(money("9007199254740993", "USD"), "USD $90,071,992,547,409.93");
  assert.equal(money(-1), "MXN -$0.01");
  assert.equal(money(-12345n), "MXN -$123.45");
});
