import assert from "node:assert/strict";
import { build } from "esbuild";

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.value = ""; }
  set textContent(value) { this.value = value; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
}
globalThis.document = { createElement: tag => new Element(tag) };
const result = await build({ entryPoints: ["src/hypothesis-source.ts"], bundle: true, write: false, platform: "node", format: "esm" });
const moduleUrl = "data:text/javascript;base64," + Buffer.from(result.outputFiles[0].contents).toString("base64");
const { createHypothesisSource } = await import(moduleUrl);
const scope = "frozen_protocol_hypothesis_source_declaration";
const render = (source, project = {}) => createHypothesisSource(source, project).textContent;
const missing = render({ scope, source_basis: null, policy: null });
assert.match(missing, /来源声明未记录/);
assert.doesNotMatch(missing, /规则选择次数：0|冻结阈值：0|ID 相同/);
const counter = "fixture opposing observations 0.839691x and 2.339x; single timers";
const source = { scope, protocol_sha256: "fixture-protocol-sha", source_basis: { old_source_project_id: "fixture-project", source_counterevidence: counter, source_informed_rule_choices: 1 }, policy: { threshold: 7, allowed_arm_ids: ["fixture-threshold7"] } };
const matched = render(source, { status: "available", project_id: "fixture-project" });
assert.ok(matched.includes(counter));
assert.ok(matched.includes("冻结阈值：7"));
assert.ok(matched.includes("规则选择次数：1"));
assert.ok(matched.includes("fixture-protocol-sha"));
assert.ok(matched.includes("仅是记录 ID 匹配"));
assert.ok(matched.includes("不自动导入或关联行动，也不共享预算"));
assert.doesNotMatch(render(source, { status: "available", project_id: "another" }), /记录 ID 匹配/);
assert.doesNotMatch(render(source, { status: "unknown", project_id: "fixture-project" }), /记录 ID 匹配/);
assert.match(render({ ...source, scope: "untrusted" }), /来源声明未记录或无法确认/);
const partial = render({ scope, source_basis: { old_source_project_id: "fixture-project" } });
assert.match(partial, /来源观察及反证原文：未记录/);
assert.match(partial, /规则选择次数：未记录；冻结阈值：未记录/);
console.log("hypothesis source UI: missing, raw values, identity match and mismatch passed");
