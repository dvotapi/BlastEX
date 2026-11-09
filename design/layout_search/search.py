"""Поиск раскладки по этапам: геометрия → первый ряд у откоса → подстройка.

Этапы идут по порядку. Семена следующего этапа — лучшие по `Evaluation.rank_key()`
среди всех оценённых вариантов (не только текущего этапа), с разными сетками;
отбракованные в семена не идут, пока есть прошедшие. Шаблоны от бровки и «от
тыла» делят один бюджет: на этапах 1 и 3 их варианты оцениваются через один
(`interleave_templates`), семена этапа 2 — только от бровки (схемы первого
ряда), этапа 3 — лучшие каждого шаблона. Отбраковка и сравнение общие; в
семена этапа 2 идут и варианты, отбракованные только превышением ЛСП
(`FRONT_ROWS_FIXABLE`): его и исправляют схемы первого ряда. Перед каждой оценкой
проверяются бюджет времени и запрос остановки (и в начале каждого этапа); при
срабатывании возвращается лучшее найденное, а если не оценено ничего — пустой
`best` и предупреждение `NOTHING_EVALUATED`; бюджет, кончившийся до конца
этапа 1, добавляет `BIG_BLOCK`. Поиск последовательный, без процессов и
потоков: параллельность — решение части 4в.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from design.layout_search.evaluate import Evaluation, SearchContext, evaluate
from design.layout_search.space import Candidate, interleave_templates, is_back, stage1, stage2, stage3

STAGE_GEOMETRY = "geometry"
STAGE_FRONT_ROWS = "front_rows"
STAGE_REFINE = "refine"
# Остановка (бюджет ≤ 0, запрос) раньше первой оценки: `best` пуст.
NOTHING_EVALUATED = "Подбор остановлен до первой оценки."
# Бюджет кончился, не досчитав этап 1 (геометрию).
BIG_BLOCK = "Блок большой: за отведённое время просчитана только часть вариантов геометрии."
# Округление координат устьев при сравнении сеток, м.
_COORD_DIGITS = 2
# Брак, который исправляют схемы первого ряда этапа 2 (пара у откоса, плавный
# переход): вариант, отбракованный только им, — семя этапа 2 наравне с прошедшими.
FRONT_ROWS_FIXABLE = frozenset({"floor_burden_excess"})


@dataclass
class SearchResult:
    """Итог поиска: лучшие варианты и сведения о ходе."""

    best: list[Evaluation]
    evaluated: int
    rejected: int
    stopped_early: bool
    elapsed_s: float
    all_rejected: bool
    warnings: list[str] = field(default_factory=list)


def _grid_key(ev: Evaluation) -> tuple:
    """Одинаковый набор устьев (до 0,01 м) и фланг — одна сетка."""
    coords = sorted(
        (round(h.collar.x, _COORD_DIGITS) + 0.0, round(h.collar.y, _COORD_DIGITS) + 0.0) for h in ev.holes
    )
    return (tuple(coords), ev.candidate.cut_flank)


def _ranked(evaluations: list[Evaluation], fixable: frozenset[str] = frozenset()) -> list[Evaluation]:
    """Прошедшие отбраковку, по `rank_key`; если их нет — отбракованные.

    `fixable` — коды, с которыми вариант считается прошедшим (семена этапа 2):
    отбракованный только ими сравнивается с прошедшими по остальному ключу."""

    def hard(ev: Evaluation) -> bool:
        return ev.rejected and not set(ev.reject_codes) <= fixable

    passed = [ev for ev in evaluations if not hard(ev)]
    return sorted(passed or evaluations, key=lambda ev: ev.rank_key(rejected=hard(ev)))


def _seeds(evaluations: list[Evaluation], count: int, fixable: frozenset[str] = frozenset()) -> list[Candidate]:
    """Лучшие варианты с разными сетками (`_grid_key`): дубли сетки семя не тратят."""
    return [ev.candidate for ev in _top_distinct(evaluations, count, fixable)]


def _template_seeds(
    evaluations: list[Evaluation], count: int, *, back: bool, fixable: frozenset[str] = frozenset()
) -> list[Candidate]:
    """`_seeds` среди вариантов одного шаблона."""
    return _seeds([ev for ev in evaluations if is_back(ev.candidate.params) == back], count, fixable)


def _top_distinct(
    evaluations: list[Evaluation], top_n: int, fixable: frozenset[str] = frozenset()
) -> list[Evaluation]:
    out: list[Evaluation] = []
    if top_n <= 0:
        return out
    seen: set[tuple] = set()
    for ev in _ranked(evaluations, fixable):
        key = _grid_key(ev)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
        if len(out) >= top_n:
            break
    return out


def search_layout(
    ctx: SearchContext,
    *,
    budget_s: float = 150.0,
    top_n: int = 3,
    stage2_seeds: int = 20,
    stage3_seeds: int = 3,
    progress: Callable[[str, int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> SearchResult:
    """Трёхэтапный перебор раскладки; `progress(этап, сделано, всего)`."""
    started = clock()
    base = ctx.design.pattern_params
    cache: dict[tuple, Evaluation] = {}
    stopped = False
    # Остановка по бюджету (не по запросу) и досчитан ли этап 1.
    budget_hit = False
    geometry_done = False

    def out_of_time() -> bool:
        nonlocal budget_hit
        if clock() - started >= budget_s:
            budget_hit = True
            return True
        return bool(should_stop and should_stop())

    # Оценки по раскладке: разные параметры, давшие одни скважины, считаются раз.
    layouts: dict = {}

    def run_stage(name: str, candidates: list[Candidate]) -> bool:
        """Оценивает новые варианты этапа; False — поиск остановлен."""
        nonlocal stopped
        # Уже оценённые (семя в этапе 2, повторы между этапами) не пересчитываются.
        todo = [c for c in candidates if c.key() not in cache]
        total = len(todo)
        if progress:
            progress(name, 0, total)
        for done, candidate in enumerate(todo, start=1):
            if out_of_time():
                stopped = True
                return False
            cache[candidate.key()] = evaluate(ctx, candidate, layouts)
            if progress:
                progress(name, done, total)
        return True

    contour = ctx.design.contour

    def refine() -> list[Candidate]:
        # Семена — лучшие каждого шаблона: шаблон, отставший на грубой сетке
        # этапа 1, после подстройки может обойти другой.
        evaluations = list(cache.values())
        seeds = _template_seeds(evaluations, stage3_seeds, back=False)
        seeds += _template_seeds(evaluations, stage3_seeds, back=True)
        return interleave_templates(stage3(seeds, base, contour))

    stages = (
        (STAGE_GEOMETRY, lambda: interleave_templates(stage1(base, contour))),
        # Схемы первого ряда есть только у шаблона от бровки.
        (
            STAGE_FRONT_ROWS,
            lambda: stage2(
                _template_seeds(list(cache.values()), stage2_seeds, back=False, fixable=FRONT_ROWS_FIXABLE), base
            ),
        ),
        (STAGE_REFINE, refine),
    )
    for name, make in stages:
        # Остановка проверяется и в начале этапа: этап без новых вариантов её не пропускает.
        if out_of_time():
            stopped = True
            break
        if not run_stage(name, make()):
            break
        if name == STAGE_GEOMETRY:
            geometry_done = True

    evaluations = list(cache.values())
    best = _top_distinct(evaluations, top_n)
    rejected = sum(1 for ev in evaluations if ev.rejected)
    all_rejected = bool(evaluations) and rejected == len(evaluations)

    warnings: list[str] = []
    for ev in best:
        for text in ev.warnings:
            if text not in warnings:
                warnings.append(text)
    # Остановка и «все отбракованы» — флаги `stopped_early`/`all_rejected`:
    # пометку по ним даёт интерфейс, предупреждение их не дублирует.
    if stopped and not evaluations:
        warnings.append(NOTHING_EVALUATED)
    elif stopped and budget_hit and not geometry_done:
        warnings.append(BIG_BLOCK)

    return SearchResult(
        best=best,
        evaluated=len(evaluations),
        rejected=rejected,
        stopped_early=stopped,
        elapsed_s=clock() - started,
        all_rejected=all_rejected,
        warnings=warnings,
    )
