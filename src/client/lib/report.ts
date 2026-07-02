import type { SkillArtifact, SkillSessionResponse } from "../../shared/domain";

export const reportOrder = [
  "p1_overview.md",
  "p2a_planets.md",
  "p2b_planets.md",
  "p2c_planets.md",
  "p2d_planets.md",
  "p3a_d9.md",
  "p3b_divisional.md",
  "p4a_houses.md",
  "p4b_houses.md",
  "p5a_life.md",
  "p5b_life.md",
  "appendix.md",
  "career_phase4a.md",
  "love_report.md",
  "rectification_report.md"
];

export const reportTitles: Record<string, string> = {
  "p1_overview.md": "总览",
  "p2a_planets.md": "行星结构一",
  "p2b_planets.md": "行星结构二",
  "p2c_planets.md": "行星结构三",
  "p2d_planets.md": "行星结构四",
  "p3a_d9.md": "D9 与分盘",
  "p3b_divisional.md": "分盘补充",
  "p4a_houses.md": "宫位主题一",
  "p4b_houses.md": "宫位主题二",
  "p5a_life.md": "人生板块一",
  "p5b_life.md": "人生板块二",
  "appendix.md": "附录",
  "career_phase4a.md": "事业",
  "love_report.md": "关系",
  "rectification_report.md": "校时"
};

export function isReportArtifact(artifact: SkillArtifact) {
  const path = artifact.path;
  if (!path.endsWith(".md")) return false;
  if (
    path === "structured_data.md" ||
    path === "reader_prevalidation.md" ||
    path === "user_context.md" ||
    path === "intake.md" ||
    path.endsWith("structured_data_B.md") ||
    path.endsWith("synastry_data.md")
  ) {
    return false;
  }
  return (
    path.startsWith("p") ||
    path === "appendix.md" ||
    path.startsWith("career_") ||
    path.startsWith("love_") ||
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

export function titleForArtifact(artifact: SkillArtifact) {
  const basename = artifact.path.split("/").pop() ?? artifact.path;
  if (reportTitles[basename]) return reportTitles[basename];
  if (artifact.title && artifact.title !== artifact.path) return artifact.title;
  return basename.replace(/\.md$/, "").replace(/[_-]+/g, " ");
}

export function getReportSections(session: SkillSessionResponse | null) {
  const artifacts = session?.artifacts ?? [];
  return artifacts
    .filter(isReportArtifact)
    .sort((a, b) => reportRank(a.path) - reportRank(b.path) || a.path.localeCompare(b.path));
}
