# Source Map

This skill is derived from three local PDFs supplied by the user:

| Text | Local path | Pages observed | Primary use |
| --- | --- | ---: | --- |
| 穷通宝鉴 | `/Users/haiyuan/Desktop/bazi/穷通宝鉴.pdf` | 53 | 调候：十日干十二月令 |
| 子平真诠评注 | `/Users/haiyuan/Desktop/bazi/子平真诠评注.pdf` | 166 | 格局：月令取格、用神、相神、成败救应、行运 |
| 滴天髓 | `/Users/haiyuan/Desktop/bazi/滴天髓.pdf` | 121 | 气势：体用、衰旺、中和、源流、通关、清浊、寒暖燥湿 |

## Extraction Protocol

If a future run needs exact wording or a section not summarized in references:

1. Extract PDFs to temporary text outside the repo.
2. Search the temporary text by heading or day-stem/month keywords.
3. Use short excerpts only when needed; otherwise paraphrase.
4. Do not copy large source passages into reports or skill files.

Known useful search handles:

- `穷通宝鉴`: `三春甲木`, `正月甲木`, `三夏甲木`, `三秋甲木`, `三冬甲木`, `三春乙木`
- `子平真诠评注`: `论用神`, `论用神成败救应`, `论相神紧要`, `论用神配气候得失`, `论行运`
- `滴天髓`: `体用`, `月令`, `衰旺`, `中和`, `源流`, `通关`, `清气`, `浊气`, `真神`, `假神`, `寒暖`, `燥湿`, `小儿`, `岁运`

## Current Extraction Evidence

In this implementation pass, the PDFs were extracted to temporary text under `/private/tmp/bazi_pdf_text` with `pypdf`. The extraction was used only to identify structure and summarize rules. The skill keeps compact references rather than full converted books.
