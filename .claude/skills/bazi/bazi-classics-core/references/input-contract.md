# Input Contract

Use this when validating `bazi_structured_data.md/json`.

The calculator owns these facts. The report skill reads them; it does not recalculate them.

## Required Fields

```json
{
  "subject": {
    "name": "optional",
    "gender": "男/女/未提供",
    "birthDate": "YYYY-MM-DD",
    "birthTime": "HH:MM or unknown",
    "birthPlace": "city, region",
    "calendarType": "solar/lunar",
    "timePrecision": "exact/approximate/part_of_day/unknown",
    "solarTimeApplied": true
  },
  "pillars": {
    "year": { "stem": "甲", "branch": "子" },
    "month": { "stem": "甲", "branch": "子", "solarTermBoundary": "立春/惊蛰/..." },
    "day": { "stem": "甲", "branch": "子" },
    "hour": { "stem": "甲", "branch": "子", "uncertain": false }
  },
  "dayMaster": {
    "stem": "甲",
    "element": "木",
    "yinYang": "阳"
  },
  "hiddenStems": {
    "子": ["癸"]
  },
  "tenGods": {
    "yearStem": "偏财",
    "yearBranchMain": "正印"
  },
  "relations": {
    "combinations": [],
    "clashes": [],
    "harms": [],
    "punishments": [],
    "threeMeetings": [],
    "threeCombinations": []
  },
  "luck": {
    "direction": "forward/reverse",
    "startAge": 0,
    "currentLuck": { "pillar": "甲子", "startYear": 2020, "endYear": 2029, "ageRange": "20-29" },
    "majorLuck": []
  }
}
```

## Report Context Fields

`bazi_report_context.md` adds reader and life-stage context:

- current date
- current age
- life stage: child, teen, adult, elder
- report audience
- topic priority, if user provided one
- per-luck-cycle true ages

## Hard Failures

Stop report generation if:

- day pillar is missing
- month pillar is not tied to solar terms
- hour pillar is uncertain but report claims hour-specific conclusions
- luck age ranges are absent
- current age or report audience is unknown
