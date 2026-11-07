"""质量体检：填补率、量级分布、零方差、三日全填补年份。

只看和报，不改任何值。结论分两层：
    逐城  —— 这条序列能不能进 ARIMA（全零/零方差直接判死）
    逐年  —— 这个点是不是真实观测（三日全靠填补的年份，建模时要标出来）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from q1collect.config import STATIONS

from .config import EXTREME_MM, MISSING_STATUS, MONTH_DAY_LABEL, VALUE_STATUS
from .features import FLAG_YES

log = logging.getLogger(__name__)

# 城市级问题的阈值，写在这里方便调
FILL_RATE_WARN = 0.10        # 填补率超过 10% 提一句
TRACE_RATE_WARN = 0.50       # trace 占比过高说明该站观测习惯有问题
ZERO_YEAR_WARN = 0.50        # 一半以上年份假期无雨，序列信息量有限


@dataclass
class QualityResult:
    """体检结论。"""

    city_rows: list[dict] = field(default_factory=list)
    year_rows: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def city_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.city_rows)

    @property
    def year_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.year_rows)


class QualityChecker:
    """逐城逐年的可用性检查。"""

    def check(self, long: pd.DataFrame, wide: pd.DataFrame) -> QualityResult:
        result = QualityResult()
        result.city_rows = self._by_city(long, wide, result.issues)
        result.year_rows = self._by_year(long, wide)
        for row in result.year_rows:
            if row["all_imputed"] == FLAG_YES:
                result.issues.append(
                    f"{row['city']} {row['year']}：三日全为填补值，该年不是真实观测")
        result.stats = self._global(long, wide, result)
        return result

    # ------------------------------------------------------------ 逐城

    def _by_city(self, long: pd.DataFrame, wide: pd.DataFrame,
                 issues: list[str]) -> list[dict]:
        rows: list[dict] = []
        for city, sub in long.groupby("city", sort=False):
            station = STATIONS[city]
            status = sub["prcp_status"].fillna("").astype(str)
            series = wide.loc[wide["city"] == city, "prcp_sum_mm"].astype(float)

            days = len(sub)
            filled = int((sub["is_filled"] == FLAG_YES).sum())
            values = pd.to_numeric(sub["prcp_mm"], errors="coerce")
            zero_years = int((series <= 0).sum())
            std = float(series.std(ddof=1)) if len(series) > 1 else 0.0

            problems: list[str] = []
            if std == 0 or float(series.abs().sum()) == 0:
                problems.append("全零序列（假期降水 20 年恒为 0，ARIMA 无信息可提取）")
            if filled / days > FILL_RATE_WARN:
                problems.append(f"填补率 {filled / days:.1%}（{filled}/{days}）")
            if int((status == "trace").sum()) / days > TRACE_RATE_WARN:
                problems.append("trace 占比过半，该站降水字段上报不积极")
            if zero_years / len(series) > ZERO_YEAR_WARN:
                problems.append(f"{zero_years}/{len(series)} 年假期无雨，序列稀疏")
            if station.role == "邻近替代站":
                problems.append(f"替代站（{station.name}），非本市实测")

            rows.append({
                "city": city,
                "station_id": station.station_id,
                "station_name": station.name,
                "station_role": station.role,
                "days_total": days,
                "days_obs": int(status.isin(VALUE_STATUS).sum()),
                "days_filled": filled,
                "fill_rate": round(filled / days, 4),
                "days_trace": int((status == "trace").sum()),
                "days_dry_I": int((status == "dry_I").sum()),
                "days_missing_raw": int(status.isin(MISSING_STATUS).sum()),
                "prcp_mean_mm": round(float(values.mean()), 2),
                "prcp_max_mm": round(float(values.max()), 2),
                "zero_ratio": round(float((values <= 0).sum()) / days, 4),
                "series_zero_years": zero_years,
                "series_std": round(std, 3),
                "usable_for_arima": "" if (std == 0 or float(series.abs().sum()) == 0) else FLAG_YES,
                "issue": "；".join(problems),
            })
            issues.extend(f"{city}：{text}" for text in problems)
        return rows

    # ------------------------------------------------------------ 逐年

    def _by_year(self, long: pd.DataFrame, wide: pd.DataFrame) -> list[dict]:
        rows: list[dict] = []
        status = long["prcp_status"].fillna("").astype(str)
        missing = long.loc[status.isin(MISSING_STATUS)].groupby(
            ["city", "year"]).size().to_dict()

        for _, row in wide.iterrows():
            filled = int(row["filled_days"])
            raw_missing = int(missing.get((row["city"], int(row["year"])), 0))
            problems: list[str] = []
            if filled == len(MONTH_DAY_LABEL):
                problems.append("三日全为填补值，本年不是真实观测")
            elif filled > 0:
                problems.append(f"填补 {filled} 天")
            if float(row["prcp_sum_mm"]) >= EXTREME_MM:
                problems.append("假期降水超过 200 mm，需核对原始值")

            rows.append({
                "city": row["city"],
                "year": int(row["year"]),
                "prcp_0404": row["prcp_0404"],
                "prcp_0405": row["prcp_0405"],
                "prcp_0406": row["prcp_0406"],
                "prcp_sum_mm": row["prcp_sum_mm"],
                "rainy_days": int(row["rainy_days"]),
                "small_rain_days": int(row["small_rain_days"]),
                "filled_days": filled,
                "all_imputed": FLAG_YES if filled == len(MONTH_DAY_LABEL) else "",
                "raw_missing_days": raw_missing,
                "issue": "；".join(problems),
            })
        return rows

    # ------------------------------------------------------------ 全局

    def _global(self, long: pd.DataFrame, wide: pd.DataFrame,
                result: QualityResult) -> dict:
        status = long["prcp_status"].fillna("").astype(str)
        values = pd.to_numeric(long["prcp_mm"], errors="coerce")
        extreme = long.loc[values >= EXTREME_MM, ["city", "date", "prcp_mm"]]
        for _, row in extreme.iterrows():
            result.issues.append(
                f"{row['city']} {row['date']} 降水 {row['prcp_mm']} mm 超阈值，人工核对")

        return {
            "rows": int(len(long)),
            "cities": int(long["city"].nunique()),
            "years": int(long["year"].nunique()),
            "days_per_year": len(MONTH_DAY_LABEL),
            "days_filled": int((long["is_filled"] == FLAG_YES).sum()),
            "days_all_imputed": int((wide["all_imputed"] == FLAG_YES).sum()),
            "status_counts": {key: int((status == key).sum()) for key in
                              ("ok", "trace", "dry_I", "no_report", "missing", "no_row", "no_file")},
            "series_total": int(len(wide)),
            "series_zero": int((wide["prcp_sum_mm"].astype(float) == 0).sum()),
            "extreme_days": int(len(extreme)),
            "mean_mm": round(float(values.mean()), 3),
            "max_mm": round(float(values.max()), 3),
            "min_mm": round(float(values.min()), 3),
        }
