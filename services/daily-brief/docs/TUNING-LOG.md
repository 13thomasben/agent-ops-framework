# Tuning log

Every prompt or weight change lands here with a date, so we can tell which
change caused which improvement (spec §9). Review questions each session:
what appeared that shouldn't · what was missing · what was ranked wrong.

Format: `date · who · file touched · change · why · result (filled in next review)`

---

- 2026-07-27 · owner/Claude · baseline · initial `ask_classifier.md` prompt,
  weights per spec §4 (days-open 10/day, ext 30 / int 15 / vendor 5, deal +20,
  seniority +15, repeat +25, windows 1/1/2/3 bd), confidence floor 0.6 ·
  starting point for week-1 review · result: —
