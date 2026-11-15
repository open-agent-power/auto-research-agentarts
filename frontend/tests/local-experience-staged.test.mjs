import assert from "node:assert/strict";
import { build } from "esbuild";

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.value = ""; this.className = ""; }
  set textContent(value) { this.value = value; }
  get textContent() { return this.value + this.children.map(child => child.textContent).join(""); }
  append(...nodes) { this.children.push(...nodes); }
}
globalThis.document = { createElement: tag => new Element(tag) };
const result = await build({ entryPoints: ["src/local-experience.ts"], bundle: true, write: false, platform: "node", format: "esm" });
const moduleUrl = "data:text/javascript;base64," + Buffer.from(result.outputFiles[0].contents).toString("base64");
const { isStagedExperienceSchema, isSupportedExperienceSchema, stagedObservation } = await import(moduleUrl);
for (const version of [1, 2, 3]) {
  assert.equal(isStagedExperienceSchema(`staged-retrieval-experience-bundle-v${version}`), true);
  assert.equal(isSupportedExperienceSchema(`staged-retrieval-experience-bundle-v${version}`), true);
}
for (const schema of ["project-experience-bundle-v1", "cpu-project-experience-bundle-v1"])
  assert.equal(isSupportedExperienceSchema(schema), true);
for (const schema of ["staged-retrieval-experience-bundle-v4", null, {}, ""])
  assert.equal(isSupportedExperienceSchema(schema), false);
const pair = (recall, mrr) => ({ paired_candidate_minus_baseline: { "recall@20": { mean: recall }, "mrr@10": { mean: mrr } } });
const feedback = { outcome: "condition_not_met", condition: { metric: "recall@20", operator: "gt", threshold: 0 }, value: 0 };
const one = { selected_method: "bm25", query_count: 200, comparison_status: "selected_equals_baseline_single_computation",
  summary: { selected: { "recall@20": .97, "mrr@10": .85 } } };
const shadow = { condition: { all: [] }, value: { means: [0, -.02], leave_one_out: { minimum: -.005 } },
  comparison: { A_method: "bm25", B_method: "bm25", outcome: "unknown", reason: "same_arm", B_minus_A: null } };
const view = (observation, scope = {}) => { const node = new Element("article"); stagedObservation(node, observation, scope); return node.textContent; };
const realShape = { comparison: { baseline: "bm25", candidate: "tfidf_cosine" }, paired_summary: { splits: { dev: pair(.01, .02), validation: pair(0, -.02) } }, preregistered_feedback: feedback,
  shadow_comparison: shadow, final: one };
const text = view(realShape, { dataset_label: "fixture" });
assert.match(text, /基线方法 · bm25；候选方法 · tfidf_cosine/);
assert.match(text, /开发集候选减基线：Recall@20 0.01；MRR@10 0.02/);
assert.match(text, /验证集候选减基线：Recall@20 0；MRR@10 -0.02/);
assert.match(text, /原判定 · 条件未满足/);
assert.match(text, /原反馈值 · 0/);
assert.match(text, /比较结果 · 未知/);
assert.match(text, /B−A 未知，不是零/);
assert.match(text, /最终只计算了 BM25 单臂/);
assert.match(text, /最终 TF-IDF 未测/);
assert.match(text, /锚是未验证的操作者声明/);
assert.doesNotMatch(text, /已测两臂的 B−A/);
const partial = view({ shadow_comparison: {}, final: {} });
assert.match(partial, /Recall@20 未记录/);
assert.match(partial, /事前反馈绑定/);
assert.match(partial, /最终对照状态未记录/);
assert.doesNotMatch(partial, /已测两臂|最终只计算了 BM25/);
const missingComparison = view({ shadow_comparison: { value: {} } });
assert.match(missingComparison, /比较状态未记录/);
assert.doesNotMatch(missingComparison, /已测两臂的 B−A/);
const distinct = view({ shadow_comparison: { value: { means: [.1, -.02], leave_one_out: { minimum: 0 } },
  comparison: { A_method: "tfidf_cosine", B_method: "bm25", outcome: "condition_met", reason: "different_arms_measured",
    B_minus_A: { "recall@20": 0, "mrr@10": .03 } } }, final: { selected_method: "tfidf_cosine", baseline_method: "bm25",
    comparison_status: "distinct_selected_and_baseline", summary: { selected: { "recall@20": .8, "mrr@10": .7 },
      baseline: { "recall@20": .8, "mrr@10": .8 }, delta: { "recall@20": 0, "mrr@10": -.1 } } } });
assert.match(distinct, /本样本预定目标满足/);
assert.match(distinct, /已测两臂的 B−A：Recall@20 0；MRR@10 0.03/);
assert.match(distinct, /留一最小值 0/);
assert.match(distinct, /原基线 · bm25；Recall@20 0.8；MRR@10 0.8/);
assert.match(distinct, /保存的所选减基线：Recall@20 0；MRR@10 -0.1/);
console.log("staged experience UI: v1/v2/v3 schema, zero, unknown, missing and measured comparisons passed");
