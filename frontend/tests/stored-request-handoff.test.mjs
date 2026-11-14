import assert from "node:assert/strict";
import { build } from "esbuild";
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.value = ""; this.style = {}; }
  set textContent(value) { this.value = value; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
}
globalThis.document = { createElement: tag => new Element(tag) };
const built = await build({ entryPoints: ["src/stored-plan-report.ts"], bundle: true, write: false, platform: "node", format: "esm" });
const moduleUrl = "data:text/javascript;base64," + Buffer.from(built.outputFiles[0].contents).toString("base64");
const { createStoredPlanReport } = await import(moduleUrl);
const original = '{"proposal":{"rationale":"<img src=x>"},"request_id":"fixture-original"}';
const handoff = { schema_version: "stored-original-request-handoff-v1", scope: "canonical_semantic_body_only_not_execution_authorization", status: "available", canonical_semantic_json: original,
  manager_body_sha256: "manager-fixture", manager_intent_sha256: "manager-fixture", controller_request_sha256: "core-fixture", project_producer_code_identity: "producer-fixture", controller_producer_code_identity: "controller-fixture", source_snapshot_sha256: "snapshot-fixture" };
function render(value) {
  const controller = { request_id: "fixture-original", status: "waiting", child_binding_status: "explicit_null", request_handoff: value };
  return createStoredPlanReport({ status: "available", plans: [{ revision: { version: 1 }, controllers: [controller] }] }, {});
}
function flatten(node) { return [node, ...node.children.flatMap(flatten)]; }
const node = render(handoff), all = flatten(node), pre = all.find(element => element.tagName === "pre");
assert.equal(pre.textContent, original);
assert.ok(node.textContent.includes("不是执行授权"));
assert.ok(node.textContent.includes("不代表原网络字节或字段顺序"));
for (const label of ["manager-fixture", "core-fixture", "producer-fixture", "controller-fixture", "snapshot-fixture"]) assert.ok(node.textContent.includes(label));
assert.equal(all.some(element => element.tagName === "img" || element.tagName === "button"), false);
const recipeParent = { request_id: "fixture-recipe", status: "waiting", child_binding_status: "explicit_null", request_handoff: handoff,
  manager_receipt: { view_status: "available", command: "advance_recipe", request_id: "fixture-recipe", record_status: "preparing", result_recorded: true, result_present: false } };
const recipe = createStoredPlanReport({ status: "available", plans: [{ revision: { version: 1 }, controllers: [recipeParent] }] }, {});
assert.ok(recipe.textContent.includes("工作台 advance_recipe 收据"));
for (const invalid of [{ ...handoff, status: "integrity_error" }, { ...handoff, scope: "other" }, {}, null]) {
  const view = render(invalid); assert.equal(flatten(view).some(element => element.tagName === "pre"), false); assert.ok(view.textContent.includes("无法完整核对"));
}
console.log("stored request UI: text-only body, identities, no action and fail-closed states passed");
