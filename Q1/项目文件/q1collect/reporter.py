"""结果落盘：三张表 + 一份 JSON 汇总。

列顺序、字段命名在这里定死，下游清洗脚本按此读取，不要随意改动。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from .collector import CollectResult
from .config import MONTH_DAY, STATIONS, VALID_STATUS
from .paths import ProjectPaths

log = logging.getLogger(__name__)

RECORD_COLUMNS = [
    "city", "station_id", "station_name", "station_role", "year", "date",
    "prcp_inch", "prcp_mm", "prcp_status", "prcp_attr", "source", "note",
]

REPORT_COLUMNS = [
    "city", "station_id", "station_name", "station_role", "year",
    "days_total", "days_ok", "days_missing", "status",
    "year_rows", "year_rainy_days", "year_I_days", "station_suspect", "reason",
]

STATION_COLUMNS = [
    "city", "station_id", "station_name", "role",
    "lat", "lon", "city_lat", "city_lon", "note",
]


class ResultReporter:
    """把 CollectResult 写成文件，并生成汇总。"""

    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    # ------------------------------------------------------------ 对外

    def write_all(self, result: CollectResult, cities: list[str],
                  years: list[int], source_mode: str) -> dict[str, Path]:
        self.paths.ensure()

        records = result.records_frame
        report = result.report_frame

        main_path = self.paths.table(f"rain_{years[0]}_{years[-1]}.csv")
        report_path = self.paths.table("fetch_report.csv")
        station_path = self.paths.table("stations.csv")
        summary_path = self.paths.table("fetch_summary.json")

        self._write_csv(records, RECORD_COLUMNS, main_path)
        self._write_csv(report, REPORT_COLUMNS, report_path)
        self._write_csv(self._station_frame(cities), STATION_COLUMNS, station_path)

        summary = self._build_summary(result, records, report, cities, years, source_mode)
        summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        files = {
            "records": main_path,
            "report": report_path,
            "stations": station_path,
            "summary": summary_path,
        }
        for label, path in files.items():
            log.info("  %-9s → %s", label, self.paths.rel(path))
        return files

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _write_csv(frame: pd.DataFrame, columns: list[str], path: Path) -> None:
        """按固定列序写 CSV；utf-8-sig 便于 Excel 直接打开不乱码。"""
        out = frame.reindex(columns=columns).fillna("")
        out.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")

    @staticmethod
    def _station_frame(cities: list[str]) -> pd.DataFrame:
        rows = []
        for city in cities:
            st = STATIONS[city]
            rows.append({
                "city": st.city,
                "station_id": st.station_id,
                "station_name": st.name,
                "role": st.role,
                "lat": st.lat,
                "lon": st.lon,
                "city_lat": st.city_lat,
                "city_lon": st.city_lon,
                "note": st.note,
            })
        return pd.DataFrame(rows)

    def _build_summary(self, result: CollectResult, records: pd.DataFrame,
                       report: pd.DataFrame, cities: list[str],
                       years: list[int], source_mode: str) -> dict:
        by_city: dict[str, dict] = {}
        for city in cities:
            sub = report[report["city"] == city]
            ok_years = sub.loc[sub["status"] == "完整", "year"].tolist()
            partial_years = sub.loc[sub["status"] == "部分缺失", "year"].tolist()
            fail_years = sub.loc[sub["status"] == "全缺", "year"].tolist()
            st = STATIONS[city]
            by_city[city] = {
                "station_id": st.station_id,
                "station_name": st.name,
                "station_role": st.role,
                "years_total": int(len(sub)),
                "years_ok": len(ok_years),
                "years_partial": len(partial_years),
                "years_fail": len(fail_years),
                "ok_years": [int(y) for y in ok_years],
                "partial_years": [int(y) for y in partial_years],
                "fail_years": [int(y) for y in fail_years],
                "days_ok": int(sub["days_ok"].sum()),
                "days_expected": int(sub["days_total"].sum()),
                "suspect_years": [int(y) for y in sub.loc[
                    sub["station_suspect"] == "是", "year"]],
            }

        status_counts = {
            status: int((records["prcp_status"] == status).sum())
            for status in ("ok", "trace", "dry_I", "no_report", "missing", "no_row", "no_file")
        }

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_mode": source_mode,
            "years": [years[0], years[-1]],
            "days": [f"{m:02d}-{d:02d}" for m, d in MONTH_DAY],
            "prcp_unit": "mm（原始文件为英寸，已 ×25.4 换算）",
            "elapsed_seconds": round(result.elapsed, 1),
            "source_counts": result.source_counts,
            "total_records": int(len(records)),
            "total_ok": int(records["prcp_status"].isin(VALID_STATUS).sum()),
            "total_trace": int((records["prcp_status"] == "trace").sum()),
            "total_dry_I": int((records["prcp_status"] == "dry_I").sum()),
            "total_missing": int((~records["prcp_status"].isin(VALID_STATUS)).sum()),
            "status_counts": status_counts,
            "by_city": by_city,
        }
