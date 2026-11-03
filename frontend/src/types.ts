export type JsonRecord = Record<string, unknown>;
export interface Source { id: string; title: string; url: string; description: string; }
export interface Claim { id: string; statement: string; evidence_ids: string[]; status: "observed" | "limitation" | "planned"; }
export interface Question { id: string; text: string; created_at: string | number; status: string; }
export interface Trial {
  id: string; ordinal: number; status: string; reason?: string; parent_trial_id?: string;
  candidate: { degree: number; alpha: number }; metrics?: Record<string, number>;
  proposal?: { hypothesis?: string; expected_effect?: string; evidence_trial_ids?: string[] };
  decision_reason?: string; model_sha256?: string; recipe_sha256?: string; error?: { code?: string };
}
export interface Section { heading: string; paragraphs: string[]; claim_ids?: string[]; }
export interface Project {
  id: string; title: string; question: string; source_goal: string; status: string;
  csrf_token?: string; labels: Record<string, string>; dataset: JsonRecord;
  metrics: { trials: number; accepted: number; rejected: number; best_validation_mse: number; test_mse: number | null; best_trial_id: string };
  sources: Source[]; claims: Claim[]; trials: Trial[];
  figures: { id: string; title: string; url: string; caption: string }[];
  report: { title: string; sections: Section[] };
  next_questions: Question[]; snapshot: { sha256: string; created_at: string | number; source_campaign_id: string; mode: string };
  exports: { pdf: string; reproduction: string };
}
export type Kind = "question" | "source" | "trial" | "claim" | "paper" | "questions";
export type SectionName = "overview" | "sources" | "trials" | "claims" | "paper" | "questions";
export interface ResearchObject {
  id: string; rawId: string; kind: Kind; title: string; summary: string; status: string;
  tag: string; group: "evidence" | "experiments" | "conclusions" | null;
  references: string[]; data: Source | Claim | Trial | Project;
}
export interface Viewport { zoom: number; x: number; y: number; }
export interface Layout {
  schema_version: 1; project_id: string; snapshot_sha256: string;
  positions: Record<string, { x: number; y: number }>; viewport: Viewport;
}
