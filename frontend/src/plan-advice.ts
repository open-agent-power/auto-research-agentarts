/** Local display eligibility for the two fixed published post-hoc experience cases. */
type Obj = Record<string, unknown>;
const object = (value: unknown): Obj => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Obj : {};
const array = (value: unknown): Obj[] => Array.isArray(value) ? value.map(object) : [];
const hash = (value: unknown): boolean => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const identifier = (value: unknown): boolean => typeof value === "string" && /^[A-Za-z0-9_.:-]{1,80}$/.test(value);
const selectorFields: Record<string, unknown> = {
  split:"validation", direction:"tfidf_cosine_minus_bm25", epsilon:1e-12,
  recall:"abs(delta_recall@20) <= epsilon", mrr:"delta_mrr@10 < -epsilon", magnitude:"mean_negative_delta_mrr@10_rounded_4_decimals",
};

/** Returns only snapshot-bound cases, never a decision, authorization or inferred threshold. */
export function posthocPlanAdviceCases(project: Obj, context: Obj | null): Obj[] {
  if (!context || !identifier(project.id) || !identifier(project.run_id) || !hash(project.snapshot_ref)
      || !Number.isSafeInteger(project.state_version) || Number(project.state_version) < 0 || !hash(context.context_sha256)
      || project.primary_method !== "research.relevance-validation-pair" || context.project_id !== project.id
      || context.run_id !== project.run_id || context.state_version !== project.state_version || context.snapshot_ref !== project.snapshot_ref
      || context.schema_version !== "project-selection-context-v1") return [];
  const experience = object(context.experience);
  if (experience.schema_version !== "project-experience-context-v1" || experience.scientific_validation !== false
      || !Array.isArray(experience.cases) || experience.cases.length < 1 || experience.cases.length > 4) return [];
  const cases = array(experience.cases).filter(item => item.inclusion_status === "active");
  if (cases.some(item => typeof item.case_id !== "string" || !item.case_id.trim() || item.case_id.length > 160 || item.case_id.includes("\0")) || new Set(cases.map(item => item.case_id)).size !== cases.length) return [];
  return cases.filter(item => {
    const observation = object(item.observation), selector = object(observation.selector), origin = object(item.origin_evidence), scope = object(item.source_scope), cell = object(observation.cell);
    return typeof item.case_id === "string" && item.case_id.length > 0 && Number.isSafeInteger(item.case_version) && Number(item.case_version) >= 1 && hash(item.bundle_sha256)
      && hash(item.entry_id) && observation.kind === "posthoc_validation_loss" && item.transfer_scope === "analogy_not_current_evidence" && item.scientific_validation === false
      && scope.domain === "retrieval" && scope.contract === "staged-relevance-development-v1" && ["S065", "S067"].includes(String(scope.source_case))
      && Object.keys(selector).length === Object.keys(selectorFields).length && Object.entries(selectorFields).every(([key, value]) => selector[key] === value)
      && observation.verification === "published_binding_requires_origin; no_recomputation_or_signature" && cell.status === "available"
      && Number.isSafeInteger(cell.count) && Number(cell.count) >= 5 && typeof cell.mean_mrr_loss === "number" && Number.isFinite(cell.mean_mrr_loss)
      && cell.mean_mrr_loss >= 0 && cell.mean_mrr_loss <= 1 && origin.action_role === "upstream_primary_reference_not_audit_producer"
      && origin.published_result_sha256 === "762d92f53422976fd6b0928f4a7f35d0572fc6803bfb11cb04315cc1176493f8"
      && origin.protocol_sha256 === "bef2c9e49cb2323be5d16918703beb09b09aac19271186e059554e5685da1e70"
      && origin.reader_sha256 === "910e5715a533483aca7066e92a85591e7a3c351ae265d1d1196479eab0d6f07e";
  });
}
