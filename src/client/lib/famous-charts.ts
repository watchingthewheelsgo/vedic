import type { LocaleCode } from "../i18n/messages";

// Public birth records; pillars use local clock time (year, month, day, hour).
export type FamousChart = {
  id: string;
  name: Record<LocaleCode, string>;
  born: string;
  place: string;
  pillars: [string, string, string, string];
};

export const famousCharts: FamousChart[] = [
  {
    id: "bruce-lee",
    name: { zh: "李小龙", en: "Bruce Lee", ja: "ブルース・リー" },
    born: "1940-11-27 07:12",
    place: "San Francisco",
    pillars: ["庚辰", "丁亥", "甲戌", "戊辰"]
  },
  {
    id: "albert-einstein",
    name: { zh: "爱因斯坦", en: "Albert Einstein", ja: "アインシュタイン" },
    born: "1879-03-14 11:30",
    place: "Ulm",
    pillars: ["己卯", "丁卯", "丙申", "甲午"]
  },
  {
    id: "steve-jobs",
    name: { zh: "史蒂夫·乔布斯", en: "Steve Jobs", ja: "スティーブ・ジョブズ" },
    born: "1955-02-24 19:15",
    place: "San Francisco",
    pillars: ["乙未", "戊寅", "丙辰", "戊戌"]
  }
];

export function dayMasterOf(chart: FamousChart): string {
  return chart.pillars[2][0];
}
