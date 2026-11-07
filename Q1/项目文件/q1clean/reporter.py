"""预处理落盘：三张数据表 + 两张报告 + 一份 JSON。

列顺序同样在这里定死，下游 04_arima.py 按此读取。
数据表进 data/processed/，报告进 output/tables/，与采集阶段的分工保持一致。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from q1collect.config import STATIONS
from q1collect.paths import ProjectPaths

from .config import (CITY_REPORT_NAME, DURATION_MIN_H, LONG_NAME,
                     MONTH_DAY_LABEL, SERIES_NAME, SMALL_RAIN_MAX,
                     SMALL_RAIN_MIN, SUMMARY_NAME, WIDE_NAME, YEAR_REPORT_NAME,
                     CleanSettings)
from .features import FLAG_YES
from .imputer import FillResult
from .loader import LoadResult
from .quality import QualityResult

log = logging.getLogger(__name__)

LONG_COLUMNS = [
    "city", "station_id", "station_name", "station_role", "year", "date", "month_day",
    "prcp_inch", "prcp_raw_mm", "prcp_mm", "prcp_level", "prcp_status", "prcp_attr",
    "quality", "prcp_in_small_range", "is_filled", "impute_basis", "dur_h",
    "is_yufengfen", "source", "note",
]

WIDE_COLUMNS = [
    "city", "station_id", "station_role", "year",
    "prcp_0404", "prcp_0405", "prcp_0406",
    "prcp_sum_mm", "prcp_max_mm", "rainy_days", "small_rain_days",
    "filled_days", "all_imputed",
]

SERIES_COLUMNS = [
    "city", "station_id", "station_role", "year", "prcp_sum_mm", "prcp_max_mm",
    "rainy_days", "small_rain_days", "filled_days", "all_imputed",
]

CITY_COLUMNS = [
    "city", "station_id", "station_name", "station_role",
    "days_total", "days_obs", "days_filled", "fill_rate", "days_trace",
    "days_dry_I", "days_missing_raw", "prcp_mean_mm", "prcp_max_mm", "zero_ratio",
    "series_zero_years", "series_std", "usable_for_arima", "issue",
]

YEAR_COLUMNS = [
    "city", "year", "prcp_0404", "prcp_0405", "prcp_0406", "prcp_sum_mm",
    "rainy_days", "small_rain_days", "filled_days", "all_imputed",
    "raw_missing_days", "issue",
]


class CleanReporter:
    """把清洗结果写成文件，并生成汇总。"""

    def __init__(self, paths: ProjectPaths, settings: CleanSettings | None = None) -> None:
        self.paths = paths
        self.settings = settings or CleanSettings()

    # ------------------------------------------------------------ 对外

    def write_all(self, long: pd.DataFrame, wide: pd.DataFrame, series: pd.DataFrame,
                  quality: QualityResult, fill: FillResult, load: LoadResult
                  ) -> dict[str, Path]:
        self.paths.ensure()

        long_path = self.paths.processed_file(LONG_NAME)
        wide_path = self.paths.processed_file(WIDE_NAME)
        series_path = self.paths.processed_file(SERIES_NAME)
        city_path = self.paths.table(CITY_REPORT_NAME)
        year_path = self.paths.table(YEAR_REPORT_NAME)
        summary_path = self.paths.table(SUMMARY_NAME)

        self._write_csv(long, LONG_COLUMNS, long_path)
        self._write_csv(wide, WIDE_COLUMNS, wide_path)
        self._write_csv(series, SERIES_COLUMNS, series_path)
        self._write_csv(quality.city_frame, CITY_COLUMNS, city_path)
        self._write_csv(quality.year_frame, YEAR_COLUMNS, year_path)

        summary = self._build_summary(quality, fill, load)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        files = {
            "长表": long_path,
            "宽表": wide_path,
            "序列": series_path,
            "城市报告": city_path,
            "年度报告": year_path,
            "汇总": summary_path,
        }
        for label, path in files.items():
            log.info("  %-9s → %s", label, self.paths.rel(path))
        return files

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _write_csv(frame: pd.DataFrame, columns: list[str], path: Path) -> None:
        order = [col for col in columns if col in frame.columns]
        extra = [col for col in frame.columns if col not in columns and not col.startswith("_")]
        out = frame.reindex(columns=order + extra).fillna("")
        out.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")

    def _build_summary(self, quality: QualityResult, fill: FillResult,
                       load: LoadResult) -> dict:
        by_city: dict[str, dict] = {}
        for row in quality.city_rows:
            city = row["city"]
            station = STATIONS[city]
            by_city[city] = {
                "station_id": station.station_id,
                "station_name": station.name,
                "station_role": station.role,
                "days_total": row["days_total"],
                "days_filled": row["days_filled"],
                "fill_rate": row["fill_rate"],
                "days_trace": row["days_trace"],
                "prcp_mean_mm": row["prcp_mean_mm"],
                "series_zero_years": row["series_zero_years"],
                "series_std": row["series_std"],
                "usable_for_arima": row["usable_for_arima"] == FLAG_YES,
                "issue": row["issue"],
            }

        imputed_years = quality.year_frame.loc[
            quality.year_frame["all_imputed"] == FLAG_YES, ["city", "year"]]

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "input": self.paths.rel(load.source),
            "years": [load.years[0], load.years[-1]] if load.years else [],
            "days": list(MONTH_DAY_LABEL),
            "cities": load.cities,
            "prcp_unit": "mm（采集阶段已由英寸 ×25.4 换算）",
            "criteria": {
                "small_rain_mm": [SMALL_RAIN_MIN, SMALL_RAIN_MAX],
                "duration_min_h": DURATION_MIN_H,
                "duration_available": False,
                "note": "时长数据未接入，dur_h 与 is_yufengfen 整列为空；"
                        "本阶段只落降水量维度（prcp_in_small_range）",
            },
            "impute": {
                "method": "同城同月日、其余年份可靠观测均值",
                "min_sample": self.settings.min_sample,
                "filled": fill.fill_count,
                "unfilled": len(fill.unfilled),
                "basis_counts": fill.basis_counts,
                "records": fill.records,
                "unfilled_records": fill.unfilled,
                "all_imputed_years": [
                    f"{row.city} {int(row.year)}" for row in imputed_years.itertuples()
                ],
            },
            "grid": {
                "rows_expected": load.rows_expected,
                "rows_found": load.rows_found,
                "rows_added": load.rows_added,
                "duplicates": load.duplicates,
                "warnings": load.warnings,
            },
            "stats": quality.stats,
            "issues": quality.issues,
            "by_city": by_city,
        }
