import type { Project, ResearchObject, SectionName } from "./types";
import { numeric } from "./dom";

const nodeId = (kind: string, raw: string) => kind + "-" + encodeURIComponent(raw).replace(/%/g, "_");
export const kindLabels: Record<ResearchObject["kind"], string> = { question: "研究问题", source: "依据来源", trial: "假设与试验", claim: "研究判断", paper: "论文成果", questions: "后续问题" };
export function objectsFor(project: Project): ResearchObject[] {
  const objects: ResearchObject[] = [{
    id: nodeId("question", project.id), rawId: project.id, kind: "question", title: project.question,
    summary: project.source_goal, status: "frozen", tag: "冻结问题", group: null, references: [], data: project,
  }];
  project.sources.forEach((source) => objects.push({
    id: nodeId("source", source.id), rawId: source.id, kind: "source", title: source.title, summary: source.description,
    status: "source", tag: source.id, group: "evidence", references: [], data: source,
  }));
  project.trials.forEach((trial) => objects.push({
    id: nodeId("trial", trial.id), rawId: trial.id, kind: "trial",
    title: "试验 " + String(trial.ordinal).padStart(2, "0") + " · " + trial.candidate.degree + " 阶配方",
    summary: "α = " + numeric(trial.candidate.alpha) + " · " + (trial.proposal?.hypothesis || trial.reason || "原始记录未提供假设。"),
    status: trial.status, tag: ({ accepted: "当次采用", rejected: "未晋升", failed: "失败", running: "原记录：在途" } as Record<string, string>)[trial.status] || "状态待核",
    group: "experiments", references: [...(trial.proposal?.evidence_trial_ids || []), ...(trial.parent_trial_id ? [trial.parent_trial_id] : [])], data: trial,
  }));
  project.claims.forEach((claim) => objects.push({
    id: nodeId("claim", claim.id), rawId: claim.id, kind: "claim", title: claim.statement,
    summary: claim.status === "limitation" ? "适用边界须与结果一起阅读。" : "判断依据保留在原始记录与引用中。",
    status: claim.status, tag: ({ observed: "记录事实", limitation: "适用边界", planned: "待执行" } as Record<string, string>)[claim.status] || "待核",
    group: "conclusions", references: claim.evidence_ids || [], data: claim,
  }));
  objects.push({
    id: nodeId("paper", project.id), rawId: "report", kind: "paper", title: "论文与复现附件",
    summary: project.report.sections.length + " 个章节 · " + project.figures.length + " 张结果图。全文与图表使用同一份冻结证据。",
    status: "paper", tag: "可阅读 / 导出", group: "conclusions", references: [], data: project,
  }, {
    id: nodeId("questions", project.id), rawId: "next_questions", kind: "questions", title: "继续研究的问题",
    summary: project.next_questions.length ? project.next_questions.length + " 条人工问题已保存，尚未执行。" : "暂未保存后续问题。记录一个未决疑问，留待人工安排。",
    status: "planned", tag: "待人工执行", group: "evidence", references: [], data: project,
  });
  return objects;
}
export function sectionObjects(objects: ResearchObject[], section: SectionName): ResearchObject[] {
  const kinds: Partial<Record<SectionName, ResearchObject["kind"]>> = { sources: "source", trials: "trial", claims: "claim", paper: "paper", questions: "questions" };
  return section === "overview" ? objects : objects.filter((object) => object.kind === kinds[section]);
}

