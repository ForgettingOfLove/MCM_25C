"""Q1 数据预处理包。

用途：读取 q1collect 产出的采集表，完成缺失填补、派生列、宽表与建模序列，
并出一份质量体检报告。只改「没有数」的格子，不动有标记的观测值。

模块职责
    config.py      CleanSettings  判据阈值、缺失口径、产物命名（唯一改参数的地方）
    loader.py      CollectTableLoader  读采集表、校验网格、补齐缺行
    imputer.py     ClimatologyImputer  历年同期非缺测均值填补
    features.py    rain_level / judge_yufengfen / add_flags / to_wide / to_series
    quality.py     QualityChecker 逐城逐年体检：零方差、填补率、三日全填补
    pipeline.py    Preprocessor   串起全流程
    reporter.py    CleanReporter  三张数据表 + 两张报告 + JSON
"""

from __future__ import annotations

__version__ = "0.1.0"

from .config import (CleanSettings, DURATION_MIN_H, MONTH_DAY_LABEL,
                     SMALL_RAIN_MAX, SMALL_RAIN_MIN)
from .features import add_flags, is_small_rain, judge_yufengfen, rain_level, to_series, to_wide
from .imputer import ClimatologyImputer, FillResult
from .loader import CollectTableLoader, LoadResult
from .pipeline import CleanResult, Preprocessor
from .quality import QualityChecker, QualityResult
from .reporter import CleanReporter

__all__ = [
    "CleanSettings",
    "CleanResult",
    "Preprocessor",
    "CleanReporter",
    "ClimatologyImputer",
    "FillResult",
    "CollectTableLoader",
    "LoadResult",
    "QualityChecker",
    "QualityResult",
    "add_flags",
    "to_wide",
    "to_series",
    "rain_level",
    "is_small_rain",
    "judge_yufengfen",
    "SMALL_RAIN_MIN",
    "SMALL_RAIN_MAX",
    "DURATION_MIN_H",
    "MONTH_DAY_LABEL",
    "__version__",
]
