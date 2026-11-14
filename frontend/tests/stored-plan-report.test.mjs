import assert from "node:assert/strict";
import { build } from "esbuild";
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.value = ""; }
  set textContent(value) { this.value = value; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
}
globalThis.document = { createElement: tag => new Element(tag) };
const result = await build({ entryPoints: ["src/stored-plan-report.ts"], bundle: true, write: false, platform: "node", format: "esm" });
const moduleUrl = "data:text/javascript;base64," + Buffer.from(result.outputFiles[0].contents).toString("base64");
const { createStoredPlanReport } = await import(moduleUrl);
const render = (history, report) => createStoredPlanReport(history, report).textContent;
const source = { status: "available", plans: [{ revision: { version: 1, request_id: "plan-fixture", question: "真实问题", basis: "原依据", steps: "原步骤", expected_feedback: "原反馈", reason: "原理由" },
  manager_receipt: { view_status: "available", request_id: "plan-fixture", record_status: "completed", result_recorded: true, result_present: true, result_status: "completed" },
  controllers: [{ request_id: "parent-fixture", status: "completed", child_request_id: "child-fixture", child_binding_status: "matched", decision_next_action: { kind: "conditional_proposal", execution_status: "not_executed", method_id: "fixture.method" }, matched_action: { id: "action-fixture", status: "completed" }, manager_receipt: { view_status: "available", request_id: "parent-fixture", record_status: "preparing", result_recorded: true, result_present: false } }] }], unmatched_controllers: [] };
const report = { status: "available", currentness: "unknown", slot: "fixture-slot", metadata: { title: "报告标题", saved_project_state_version: 13 }, declared_files: { "report.pdf": { bytes: 7, sha256: "fixture-hash" } } };
const shown = render(source, report);
for (const expected of ["真实问题", "原依据", "原步骤", "原反馈", "原理由", "not_executed", "决策快照", "action-fixture", "completed", "preparing", "null（原值）", "报告当前性未核对", "manifest 原声明", "不生成、刷新或下载报告"]) assert.ok(shown.includes(expected), expected);
const missing = render({ status: "partial", plans: null, reason: "missing" }, { status: "unavailable", currentness: "unknown" });
assert.ok(missing.includes("计划记录未读取或未记录"));
assert.ok(missing.includes("报告元数据：unavailable"));
assert.doesNotMatch(missing, /原计划列表为空|版本 0|已完成报告/);
const nullChild = structuredClone(source); nullChild.plans[0].controllers[0].child_request_id = null; nullChild.plans[0].controllers[0].child_binding_status = "explicit_null"; nullChild.plans[0].controllers[0].matched_action = null;
assert.ok(render(nullChild, {}).includes("子请求在原记录中为 null"));
console.log("stored plans UI: saved values, separate states, null and unknown passed");
