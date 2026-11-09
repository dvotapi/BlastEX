"""PDF паспорта на бурение (TASK-015, PR 2).

`layout` раскладывает снимок ревизии (`drilling_passport_revisions.context`)
в страницы и строки, `pdf` рисует раскладку ReportLab, `rig_scheme` — схема
установки станка. Ничего не пересчитывает: формулы — только
`design/drilling_passport.py`.
"""
