import type { SkillArtifact, SkillSessionResponse } from "../../shared/domain";
import { messages, reportTitleKeys, type LocaleCode } from "../i18n/messages";

export const reportOrder = [
  "consultation_report.md",
  "career_phase4a.md",
  "love_report.md",
  "rectification_report.md",
  "bazi_data_audit.md",
  "bazi_overview.md",
  "bazi_classics_audit.md",
  "bazi_timing_report.md",
  "bazi_life_report.md",
  "bazi_appendix.md"
];

export const reportTitles: Record<string, string> = {
  "consultation_report.md": "VedicDust Consultation",
  "career_phase4a.md": "Career Guidance",
  "love_report.md": "Relationship Guidance",
  "rectification_report.md": "Birth Time Review",
  "bazi_data_audit.md": "BaZi Data Audit",
  "bazi_overview.md": "BaZi Overview",
  "bazi_classics_audit.md": "Classics Audit",
  "bazi_timing_report.md": "Luck and Timing",
  "bazi_life_report.md": "BaZi Life Report",
  "bazi_appendix.md": "BaZi Appendix"
};

export function isReportArtifact(artifact: SkillArtifact) {
  const path = artifact.path;
  if (!path.endsWith(".md")) return false;
  if (
    path === "bazi_chart_foundation.md" ||
    path === "bazi_report_context.md" ||
    path === "reader_prevalidation.md" ||
    path === "prevalidation_result.json" ||
    path === "user_context.md" ||
    path === "intake.md" ||
    path.endsWith("synastry_context.json")
  ) {
    return false;
  }
  return (
    path === "consultation_report.md" ||
    path.startsWith("career_") ||
    path.startsWith("love_") ||
    (path.startsWith("bazi_") && path !== "bazi_chart_foundation.md") ||
    path === "rectification_report.md" ||
    path.includes("/reports/")
  );
}

export function reportRank(path: string) {
  const normalized = path.split("/").pop() ?? path;
  const index = reportOrder.indexOf(normalized);
  if (index >= 0) return index;
  if (path.includes("/reports/")) return 200 + path.localeCompare("");
  return 100 + path.localeCompare("");
}

export function titleForArtifact(artifact: SkillArtifact, locale: LocaleCode = "en") {
  const basename = artifact.path.split("/").pop() ?? artifact.path;
  const key = reportTitleKeys[basename];
  if (key) return messages[locale]?.[key] ?? messages.en[key] ?? reportTitles[basename] ?? basename;
  if (reportTitles[basename]) return reportTitles[basename];
  if (artifact.title && artifact.title !== artifact.path) return artifact.title;
  return basename.replace(/\.md$/, "").replace(/[_-]+/g, " ");
}

export function getReportSections(session: SkillSessionResponse | null) {
  const artifacts = session?.artifacts ?? [];
  const sections = artifacts
    .filter(isReportArtifact)
    .sort((a, b) => reportRank(a.path) - reportRank(b.path) || a.path.localeCompare(b.path));
  if (!sections.some((section) => section.path === "consultation_report.md")) {
    return sections;
  }
  return sections.filter(
    (section) =>
      section.path === "consultation_report.md" ||
      section.path.startsWith("career_") ||
      section.path.startsWith("love_") ||
      section.path === "rectification_report.md" ||
      section.path.includes("/reports/")
  );
}
