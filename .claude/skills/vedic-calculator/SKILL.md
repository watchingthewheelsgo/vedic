---
name: vedic-calculator
description: 吠陀占星排盘计算引擎。当用户提供出生时间和地点，需要从零计算星盘数据时触发。输入出生日期、时间、地点，直接输出structured_data.md，跳过JHora排盘和PDF读取流程。当用户提到'直接排盘''计算星盘''不用jhora''快速排盘''算一下'等关键词时触发。也在vedic-reader判断无PDF输入时建议使用。
---

# vedic-calculator: 吠陀占星排盘引擎

> 基于pysweph天文引擎 + dashaflow算法模块，直接从出生时间计算完整星盘数据。
> 输出格式完全兼容vedic-reader的structured_data.md，可直接交给vedic-core分析。

## 服务化边界

本 skill 只定义排盘流程、输入输出契约、校验规则和 structured_data.md 的语义。

在产品运行环境中：
- 排盘计算由 backend calculator/tool 执行。
- skill 不描述服务环境，不引用脚本路径，不要求用户或 LLM 临时处理运行准备。
- 如果 backend tool 报错，向用户展示服务端错误，不自行替代计算。

## 输出契约

backend calculator 接收出生信息、坐标、时区、时间精度和用户信息，输出：
- `structured_data.md`
- SAV 总计校验结果，必须为 337
- 行星完整性、Ra-Ke 对宫、Lagna 合理性等校验信号

## 使用流程

### Step 1: 收集出生信息

向用户收集：
```
- 出生日期 (YYYY-MM-DD)
- 出生时间 (HH:MM，24小时制)
- 出生地点 (城市名)
- 性别
- 感情状态（可选）
- 时间精度（精确到分钟 / ±15分钟 / ±1小时 / 不确定）
- 时间来源（出生证 / 家人记忆 / 大概回忆 / 未追问）
```

### Step 2: AI转换地理坐标

根据用户提供的城市名，AI直接填写：
- 纬度 (lat)
- 经度 (lon)  
- 时区字符串 (tz_str)

常用参考：
```
北京:     39.9042, 116.4074, "Asia/Shanghai"
上海:     31.2304, 121.4737, "Asia/Shanghai"
广州:     23.1291, 113.2644, "Asia/Shanghai"
成都:     30.5728, 104.0668, "Asia/Shanghai"
台北:     25.0330, 121.5654, "Asia/Taipei"
香港:     22.3193, 114.1694, "Asia/Hong_Kong"
新德里:   28.6139, 77.2090,  "Asia/Kolkata"
孟买:     19.0760, 72.8777,  "Asia/Kolkata"
```

> ⚠️ 中国全境使用 "Asia/Shanghai" (UTC+8)
> ⚠️ 印度全境使用 "Asia/Kolkata" (UTC+5:30)

### Step 3: 调用 backend calculator

把 Step 1-2 得到的信息交给 backend calculator/tool：

```json
{
  "birth_date": "YYYY-MM-DD",
  "birth_time": "HH:MM",
  "birth_place": "城市名",
  "lat": 0.0,
  "lon": 0.0,
  "timezone": "Area/City",
  "gender": "男/女/未提供",
  "relationship": "单身/恋爱中/已婚/未提供",
  "time_precision": "exact/approximate/part_of_day/unknown",
  "time_source": "出生证/家人记忆/大概回忆/未追问"
}
```

backend calculator 负责：
1. 计算本命盘、分盘、Shadbala、SAV/BAV、Dasha、过运。
2. 使用原 formatter 契约生成 `structured_data.md`。
3. 校验 SAV 总计 = 337。

> ⚠️ 禁止 agent 自己拼 chart 输出；必须使用 backend calculator 生成 `structured_data.md`。
> chart 的语义结构见下方「engine 返回数据结构」。

### Step 4: 校验输出

检查生成的structured_data.md：
1. SAV总计 = 337 ✅
2. 行星完整性 = 10颗 ✅
3. Ra-Ke差180° ✅
4. Lagna星座是否合理

### Step 5: 模式选择

structured_data.md 生成后，向用户输出：

```
✅ 排盘完成！所有数据已生成（行星/分盘/SAV/Dasha+小运/宫主表/尊贵度/过运…）

📊 Shadbala 精度说明：
   structured_data以calc为主数据源。
   Shadbala始终先写入calc基准值。如没有JHora PDF，直接采用calc。
   如有同一出生时间生成的JHora PDF，则逐行对照并展示PDF值；
   二者不一致时会明确提示"当前采用PDF"。其余PDF数据只用于交叉验证。

下一步：
  a) 直接进入验前事（推荐）
  b) 发送 JHora PDF 补充 Shadbala
```

- 用户选 a) 或说"直接分析"/"开始" → 触发 vedic-reader（精简模式：跳过提取，直接读 structured_data → 验前事）
- 用户发送 PDF → 核对出生信息一致性 → 从PDF文本层提取有效Shadbala
  → 与calc Shadbala逐行对照 → PDF存在的行展示PDF值，差异行标注并提示用户
  → PDF缺失行保留calc → 其余PDF数据仅交叉验证
  → 再触发reader验前事


## engine 返回数据结构

> ⚠️ **必读！** 不要猜 key 名。以下是 `calculate_full_chart()` 返回的 dict 结构。

```python
chart = {
    # 基础天文
    'ayanamsa': 23.8982,           # float, True Chitra ayanamsa 度数（约23.9°，与Lahiri差<1′）
    'lagna': {
        'sign': 'Cancer',          # str, 英文星座名
        'sign_idx': 3,             # int, 0-indexed (Aries=0)
        'degree': 13.61,           # float, 绝对度数 (星座内)
        'deg_str': "13°36'",       # str, 格式化度分
        'longitude': 103.61,       # float, 黄道经度
        'nakshatra': {'name': 'Pushya', 'pada': 4, 'lord': 'Saturn'}
    },
    'planets': {
        'Sun': {
            'sign': 'Scorpio', 'sign_idx': 7,
            'degree': 25.41, 'deg_str': "25°24'",
            'longitude': 235.41,
            'house': 5,            # int, 1-indexed 从 Lagna 数
            'retrograde': False,
            'nakshatra': {'name': 'Jyeshtha', 'pada': 3, 'lord': 'Mercury'}
        },
        # ... Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu 同结构
    },

    # SAV — ⚠️ key 是英文星座名，不是 'by_sign'!
    'sav': {
        'Aries': 36, 'Taurus': 34, 'Gemini': 22, 'Cancer': 28,
        'Leo': 34, 'Virgo': 29, 'Libra': 29, 'Scorpio': 25,
        'Sagittarius': 32, 'Capricorn': 20, 'Aquarius': 26, 'Pisces': 22
    },
    'sav_by_house': {
        1: {'sign': 'Cancer', 'value': 28},  # 按宫位编号
        # ... 2-12 同结构
    },

    # BAV
    'bav': {
        'Sun': {'Aries': 6, 'Taurus': 5, ...},  # 12星座
        # ... Moon, Mars, Mercury, Jupiter, Venus, Saturn
    },

    # Shadbala — ⚠️ 用 strength_pct (不是 strength_ratio)!
    'shadbala': {
        'Sun': {
            'total_60ths': 288.6,  'total_rupas': 4.81,
            'sthana': 82.0, 'kaala': 55.0, 'dig': 6.7,
            'cheshta': 44.9, 'naisargika': 60.0, 'drik': 40.0,
            'strength_pct': 96.2,  # ⚠️ 百分比，直接用！
            'classification': '弱',
            'ishta_phala': 7.64,   # Ishta Phala
            'kashta_phala': 50.18  # Kashta Phala
        },
        # ... Moon, Mars, Mercury, Jupiter, Venus, Saturn 同结构
    },

    # Dasha
    'dashas': [
        {
            'planet': 'Jupiter', 'start': '1998-02', 'end': '2014-02',
            'years': 16, 'is_current': False,
            'antardashas': [
                {'planet': 'Jupiter', 'start': '1998-02-11', 'end': '2000-04-01', 'is_current': False},
                # ... 9个小运
            ]
        },
        # ... 共9段大运
    ],

    # 分盘 — (sign_name, sign_idx) tuple
    'd9':  {'Lagna': ('Scorpio', 7), 'Sun': ('Aquarius', 10), ...},
    'd10': {'Lagna': ('Cancer', 3),  'Sun': ('Pisces', 11), ...},
    'd4':  {'Lagna': ('Libra', 6),   'Sun': ('Leo', 4), ...},
    'd5':  {'Lagna': ('Pisces', 11), 'Sun': ('Scorpio', 7), ...},
    'vargottama': {'Sun': False, 'Moon': False, 'Rahu': True, ...},
    'divisional_charts': {'D2': ..., 'D3': ..., ...},  # 额外分盘

    # 预分析
    'karakas': {'7k': [...], '8k': [...], 'dk_7k': 'Saturn', 'dk_8k': 'Rahu', 'dk_note': '7K(主)=Saturn, 8K(参考)=Rahu'},
    'dignity': {'Sun': {'compound': 'great_friend', ...}, ...},
    'aspects': [{'source':'Mars','target':'Saturn','type':'4th Graha Drishti','strength':'紧密'}, ...],
    'house_aspects': [{'source':'Jupiter','target_house':9,'type':'5th Graha Drishti'}, ...],
    'house_lords': {1: {'lord':'Moon','domain':'自我','lord_house':8}, ...},
    'special_points': {'AL': {'sign':'Virgo','house':3}, 'UL': {'sign':'Pisces','house':9}},
    'combustion': {},
    'moon_phase': {'waxing': True, 'sun_moon_diff': 88.6},
}
```


## 输出规格

输出的structured_data.md包含以下数据板块（完全匹配data_contract.md）：

| 板块 | 内容 |
|------|------|
| 元信息 | 出生时间、地点、Ayanamsa、读盘方式 |
| 行星位置 | 10颗行星+Lagna，星座/宫位/度数/逆行 |
| Nakshatra | 全部行星的Nakshatra+Pada |
| Chara Karakas | 7K主表（KN Rao）+ 8K参考 |
| Shadbala | 7颗行星的Rupas/百分比/排名/强弱/Ishta/Kashta |
| SAV | 原始值(按星座) + 宫位映射(按宫位) |
| BAV | 7颗行星×12星座矩阵 |
| Vimsottari Dasha | 9段大运 + 当前/下一大运Antardasha |
| 特殊点位 | AL(Arudha Lagna) + UL(Upapada Lagna) |
| Compound Dignity | Panchadha Maitri（旺/入庙/陷直接确定） |
| 吠陀视相关系 | 同座接触 + Graha Drishti + 宫位被视相 |
| 宫主表 | 12宫完整 |
| 分盘 | D9/D10/D4/D5 + Vargottama |
| 校验 | 12项自动校验 |
| 过运 | 慢行星过运 + Sade Sati + 双过运 |

## 技术规格

- Ayanamsa: **True Chitrapaksha (TRUE_CITRA)**（固定，不可更改；属Lahiri系，差<1′）
- Node模式: **Mean Node**
- 天文核心: pysweph (Swiss Ephemeris C binding)
- SAV/BAV: **PyJHora 原生**
- Dasha: **PyJHora 原生**
- Shadbala: **PyJHora + 9项修正**
- 分盘: **PyJHora 原生** — 15张 D1~D60
- Dignity: dashaflow + 旺/入庙/陷前置判断
- Chara Karakas: 7K（KN Rao）+ 8K参考
- 容错策略: **fail-fast**（核心计算不可用时直接报错，不给错误结果）

## 与其他skill的关系

```
路径1（纯calc，推荐）：
  用户给出生信息 → vedic-calculator → structured_data.md → vedic-reader(验前事) → vedic-core

路径2（PDF + calc主数据）：
  用户给PDF → reader提取出生信息 → calculator生成canonical structured_data
  → PDF交叉验证（仅有效Shadbala可覆盖）→ reader(验前事) → core

路径3（兜底）：
  用户材料无法提供完整出生信息 → reader提取模式（标注降级）→ reader(验前事) → core
```

所有路径输出的 structured_data.md 格式完全一致，core 无需区分数据来源。
