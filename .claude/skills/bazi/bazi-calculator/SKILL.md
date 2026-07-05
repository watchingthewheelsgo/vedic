---
name: bazi-calculator
description: "八字排盘 calculator skill。当用户提供出生日期、时间、地点，需要计算四柱、十神、藏干、节气边界、大运、当前大运，或需要生成 bazi_structured_data.md/json 与 bazi_report_context.md 后再运行 bazi-classics-core 时触发。"
---

# bazi-calculator: 八字排盘入口

## Role

你是八字排盘的 workflow 层，不是排盘算法实现层。

核心职责：

1. 收集出生信息和报告上下文。
2. 调用 backend tool `bazi_calculate_chart`。
3. 确认生成 `bazi_structured_data.md`、`bazi_structured_data.json`、`bazi_report_context.md`。
4. 把结果交给 `bazi-classics-core` 做经典三层审计报告。

## Boundary

- 禁止手排年柱、月柱、日柱、时柱。
- 禁止手算大运顺逆、起运年龄、流年、大运年龄段。
- 禁止用常识或网上口诀替代 backend tool。
- 真太阳时、子时日界、起运算法流派必须记录为 settings，不可静默处理。
- 本 skill 不安装依赖、不写服务端代码、不修改 calculator 算法。

## Required Input

向用户或上游 intake 收集：

```text
- birth_date: YYYY-MM-DD
- birth_time: HH:MM or unknown
- birth_place: city / region
- gender: 男 / 女 / 未提供
- calendar_type: solar / lunar
- time_precision: exact / approximate / part_of_day / unknown
- timezone: IANA timezone, default Asia/Shanghai when appropriate
- latitude / longitude: optional, record when available
- current_date: YYYY-MM-DD
- audience: self / parent / partner / researcher / other
- relationship: reader relationship to subject
- topic: optional user focus
- day_boundary_sect: 1 or 2, default 2
- luck_sect: 1 or 2, default 2
- solar_time_policy: civil or record_only
```

If current date, current age context, or audience is missing, ask for it before report generation.

## Backend Tool

Use `bazi_calculate_chart` with these keys:

```json
{
  "birth_date": "YYYY-MM-DD",
  "birth_time": "HH:MM",
  "birth_place": "Shanghai",
  "gender": "male",
  "current_date": "2026-07-05",
  "out_dir": "/absolute/session/path",
  "calendar_type": "solar",
  "time_precision": "exact",
  "timezone": "Asia/Shanghai",
  "latitude": 31.2304,
  "longitude": 121.4737,
  "audience": "self",
  "relationship": "self",
  "topic": "general",
  "day_boundary_sect": 2,
  "luck_sect": 2,
  "solar_time_policy": "civil",
  "emit_artifact_content": false
}
```

Execution modes:

- File workspace mode: set `out_dir` to the current session directory and keep `emit_artifact_content=false`.
- Web artifact mode: set `out_dir` to an empty string and `emit_artifact_content=true`; then copy the returned artifact contents into the response artifacts.

## Output Contract

The backend tool must produce:

- `bazi_structured_data.json`
- `bazi_structured_data.md`
- `bazi_report_context.md`

The JSON is the machine-readable source of truth. The Markdown files are prompt artifacts for `bazi-classics-core`.

Minimum facts required downstream:

- year, month, day, hour pillars
- day master stem, element, yin/yang
- hidden stems
- ten gods for visible stems and branch hidden stems
- five-element counts
- combinations, clashes, harms, punishments, three meetings, three combinations
- previous/next Jie solar term boundary
- major luck direction, start offset, start date, current luck
- real current age and life stage
- warnings for time uncertainty, Jie boundary, Zi hour, or solar-time policy

## Handoff

After the calculator artifacts exist:

1. Tell the user the BaZi chart data is ready.
2. State whether there are boundary/time warnings.
3. Recommend running `bazi-classics-core` for the classical report.

Do not produce the classics report inside this skill.
