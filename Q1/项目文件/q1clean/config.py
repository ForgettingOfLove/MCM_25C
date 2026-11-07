"""预处理口径：缺失判定、填补策略、判据阈值。

采集阶段只取数，从这里开始才「改数」。
凡是会改变原始值、或影响下游判定的参数，都集中在本文件，
其余模块一律 import，不重复定义。站点与年份沿用 q1collect.config，避免两套口径。
"""

from __future__ import annotations

from dataclasses import dataclass

from q1collect.config import MONTH_DAY

# ---------------------------------------------------------------- 状态口径

# 采集表 prcp_status 的两组语义
#   有数   ：ok（A–G 正常日总量）、dry_I（属性 I，按 0 记）、trace（属性 H，按 0 记）
#   无数   ：no_report（I 且无值）、missing（99.99 哨兵）、no_row（文件无此日）、no_file（404）
VALUE_STATUS: tuple[str, ...] = ("ok", "trace", "dry_I")
MISSING_STATUS: tuple[str, ...] = ("no_report", "missing", "no_row", "no_file")

# 算「历年同期均值」时不进池的状态：trace 是报 0 但观测有降水，进池会把均值压偏
IMPUTE_POOL_EXCLUDE: tuple[str, ...] = ("trace",)

# ---------------------------------------------------------------- 判据（GB/T 28592—2012）

SMALL_RAIN_MIN = 0.1      # 小雨下限（mm/24h）
SMALL_RAIN_MAX = 9.9      # 小雨上限
DURATION_MIN_H = 3.0      # 「雨纷纷」降水时长下限（h），论文自设，非国标

# 从大到小排，rain_level() 顺序命中
RAIN_LEVELS: tuple[tuple[float, str], ...] = (
    (250.0, "特大暴雨"), (100.0, "大暴雨"), (50.0, "暴雨"),
    (25.0, "大雨"), (10.0, "中雨"), (SMALL_RAIN_MIN, "小雨"),
)
NO_RAIN_LABEL = "无雨"

# 单日降水超过这个值先当异常报出来人工看一眼（本题实测最大值 66.29 mm）
EXTREME_MM = 200.0

# ---------------------------------------------------------------- 产物命名

LONG_NAME = "rain_all.csv"          # 长表：一城一年一天一行，420 行
WIDE_NAME = "rain_wide.csv"         # 宽表：一城一年一行，三日展开
SERIES_NAME = "series_rain.csv"     # 序列：建模直接读，一城一年一行
CITY_REPORT_NAME = "clean_report.csv"
YEAR_REPORT_NAME = "clean_by_year.csv"
SUMMARY_NAME = "clean_summary.json"
LOG_NAME = "clean_log.txt"

MONTH_DAY_LABEL: tuple[str, ...] = tuple(f"{m:02d}-{d:02d}" for m, d in MONTH_DAY)


# ---------------------------------------------------------------- 设置

@dataclass
class CleanSettings:
    """预处理的几个旋钮。默认值即可直接跑，改这里不用翻函数体。"""

    min_sample: int = 5     # 同期均值至少要有几年；不足就退到「三日全期均值」
    decimals: int = 2       # 填补值与输出精度
    strict: bool = False    # True：出现填不上的缺失就中断，不静默放过
