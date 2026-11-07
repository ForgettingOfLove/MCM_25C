"""预处理编排：读表 → 填补 → 派生/宽表 → 体检。

只负责「跑流程」，读盘交给 loader，填补交给 imputer，
派生交给 features，体检交给 quality，落盘交给 reporter。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd

from q1collect.config import STATIONS, YEARS
from q1collect.paths import ProjectPaths

from .config import CleanSettings
from .features import add_flags, to_series, to_wide
from .imputer import ClimatologyImputer, FillResult
from .loader import CollectTableLoader, LoadResult
from .quality import QualityChecker, QualityResult

log = logging.getLogger(__name__)


@dataclass
class CleanResult:
    """一次预处理的全部产物。"""

    long: pd.DataFrame
    wide: pd.DataFrame
    series: pd.DataFrame
    quality: QualityResult
    fill: FillResult
    load: LoadResult
    elapsed: float = 0.0

    @property
    def unfilled(self) -> int:
        return len(self.fill.unfilled)

    @property
    def filled(self) -> int:
        return self.fill.fill_count


class Preprocessor:
    """把采集表加工成可直接建模的序列。"""

    def __init__(self, paths: ProjectPaths,
                 settings: CleanSettings | None = None) -> None:
        self.paths = paths
        self.settings = settings or CleanSettings()
        self.loader = CollectTableLoader(paths)
        self.imputer = ClimatologyImputer(self.settings)
        self.checker = QualityChecker()

    # ------------------------------------------------------------ 主流程

    def run(self, source: str | None = None, cities: list[str] | None = None,
            years: list[int] | None = None) -> CleanResult:
        started = time.perf_counter()
        self.paths.ensure()

        load = self.loader.load(source=source, cities=cities, years=years)
        log.info("=" * 70)
        log.info("Q1 数据预处理 | %s | 城市 %d 个 | 年份 %d—%d | 记录 %d 行",
                 self.paths.rel(load.source), len(load.cities),
                 load.years[0], load.years[-1], len(load.frame))
        log.info("=" * 70)
        for warning in load.warnings:
            log.warning("  · %s", warning)
        if len(load.cities) < len(STATIONS) or len(load.years) < len(YEARS):
            log.warning("  · 本次只处理子集（%d 城 / %d 年），产物会覆盖全量结果；"
                        "正式交付请跑全量", len(load.cities), len(load.years))

        fill = self.imputer.fill(load.frame)
        if fill.unfilled and self.settings.strict:
            raise RuntimeError(
                f"{len(fill.unfilled)} 条缺失无法填补（--strict 下不继续）："
                f"{fill.unfilled[:5]}"
            )

        long = add_flags(fill.frame)
        wide = to_wide(long)
        series = to_series(wide)
        quality = self.checker.check(long, wide)

        elapsed = time.perf_counter() - started
        log.info("预处理完成：%d 行 → %d 条城年序列，填补 %d 条，用时 %.2f 秒",
                 len(long), len(series), fill.fill_count, elapsed)
        return CleanResult(long=long, wide=wide, series=series, quality=quality,
                           fill=fill, load=load, elapsed=elapsed)
