"""抓取编排：城市 × 年份循环 → 原始缓存 → 三日记录 + 年度报告。

只负责「跑流程」，落盘交给 reporter，解析交给 parser。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pandas as pd
from tqdm import tqdm

from .config import (DEFAULT_SETTINGS, MONTH_DAY, STATIONS, RequestSettings,
                     Station)
from .http_client import GsodClient
from .parser import ATTR_NOTE, extract_window, load_station_year, profile_year
from .paths import ProjectPaths

log = logging.getLogger(__name__)

# 没有取到数值时的说明文字
STATUS_NOTE = {
    "no_file": "该站该年数据文件不存在(404)",
    "no_row": "文件中无该日期记录",
    "no_report": "属性 I：当日无降水报告，不可当作 0",
    "missing": "PRCP 为缺测值",
}
NOTE_H = ATTR_NOTE["H"]
NOTE_I = ATTR_NOTE["I"]


@dataclass
class CollectResult:
    """一次抓取的全部产物。"""

    records: list[dict] = field(default_factory=list)   # 一行 = 一城一年一天
    report: list[dict] = field(default_factory=list)    # 一行 = 一城一年
    source_counts: dict[str, int] = field(default_factory=dict)
    elapsed: float = 0.0

    @property
    def records_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    @property
    def report_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.report)


class RainCollector:
    """把「七城二十年的清明三日降水」抓下来。"""

    def __init__(self, paths: ProjectPaths, client: GsodClient | None = None,
                 settings: RequestSettings | None = None) -> None:
        self.paths = paths
        self.settings = settings or DEFAULT_SETTINGS
        self.client = client or GsodClient(self.settings)

    # ------------------------------------------------------------ 主流程

    def collect(self, cities: list[str] | None = None, years: tuple[int, ...] | list[int] | None = None,
                source: str = "auto", use_cache: bool = True,
                show_progress: bool = True) -> CollectResult:
        cities = list(cities or STATIONS.keys())
        unknown = [c for c in cities if c not in STATIONS]
        if unknown:
            raise ValueError(f"未知城市：{unknown}，可选：{list(STATIONS.keys())}")
        years = list(years or range(2006, 2026))

        self.paths.ensure()
        result = CollectResult(source_counts={"cache": 0, "access": 0, "archive": 0, "404": 0, "error": 0})
        started = time.perf_counter()

        log.info("=" * 70)
        log.info("GSOD 清明三日降水量抓取 | 城市 %d 个 | 年份 %d—%d | 数据源 %s | 缓存 %s",
                 len(cities), years[0], years[-1], source, "关闭" if not use_cache else "启用")
        log.info("=" * 70)

        tasks = [(city, year) for city in cities for year in years]
        bar = tqdm(tasks, desc="下载", unit="站年", disable=not show_progress, ncols=88)
        current_city = None

        for city, year in bar:
            station = STATIONS[city]
            if city != current_city:
                current_city = city
                bar.set_postfix_str(city)
                log.info("")
                log.info("【%s】%s  %s（%s）", city, station.station_id,
                         station.name, station.role)

            content, origin = self._fetch_one(station, year, source, use_cache)
            result.source_counts[origin] = result.source_counts.get(origin, 0) + 1
            time.sleep(self.settings.pause)

            day_rows, year_row = self._build_rows(station, year, content, origin)
            result.records.extend(day_rows)
            result.report.append(year_row)

            ok_days = year_row["days_ok"]
            flag = "OK " if ok_days == len(MONTH_DAY) else ("!! " if ok_days == 0 else "~  ")
            log.info("  %s%d  有效 %d/%d  来源 %-7s %s", flag, year, ok_days,
                     len(MONTH_DAY), origin, year_row["reason"])

        bar.close()
        result.elapsed = time.perf_counter() - started
        log.info("")
        log.info("抓取结束，用时 %.1f 秒", result.elapsed)
        return result

    # ------------------------------------------------------------ 单站单年

    def _fetch_one(self, station: Station, year: int,
                   source: str, use_cache: bool) -> tuple[bytes | None, str]:
        # use_cache 表示是否使用缓存文件，若为 True，则优先读取缓存文件；若为 False，则强制重新下载。
        cache_file = self.paths.raw_file(station.station_id, year)
        try:
            return self.client.fetch(station.station_id, year, cache_file,
                                     source=source, use_cache=use_cache)
        except Exception as exc:                      # 单个文件失败不该中断全局
            log.warning("  %d 下载异常：%s", year, exc)
            return None, "error"

    def _build_rows(self, station: Station, year: int, content: bytes | None,
                    origin: str) -> tuple[list[dict], dict]:
        """返回 (三天的记录, 该站该年的报告行)。"""
        found: dict[str, dict] = {}
        meta = {"rows": 0, "rainy_days": 0, "i_days": 0, "suspect": False}
        reasons: list[str] = []

        if content is None:
            reasons.append("下载失败" if origin == "error" else STATUS_NOTE["no_file"])
        else:
            frame = load_station_year(content)
            meta = profile_year(frame)
            if frame.empty:
                reasons.append("文件为空或列结构异常")
            found = extract_window(frame, year)

        day_rows: list[dict] = []
        ok_days = missing_days = 0

        for month, day in MONTH_DAY:
            date_str = f"{year}-{month:02d}-{day:02d}"
            base = {
                "city": station.city,
                "station_id": station.station_id,
                "station_name": station.name,
                "station_role": station.role,
                "year": year,
                "date": date_str,
            }

            if content is None:
                base.update(prcp_inch="", prcp_mm="", prcp_status="no_file",
                            prcp_attr="", source=origin, note=STATUS_NOTE["no_file"])
                missing_days += 1
                reasons.append(f"{date_str} 数据文件缺失")
                day_rows.append(base)
                continue

            hit = found.get(date_str)
            if hit is None:
                base.update(prcp_inch="", prcp_mm="", prcp_status="no_row",
                            prcp_attr="", source=origin, note=STATUS_NOTE["no_row"])
                missing_days += 1
                reasons.append(f"{date_str} 无记录")
                day_rows.append(base)
                continue

            status = hit["prcp_status"]
            if status == "no_report":
                base.update(prcp_inch=hit["prcp_inch"], prcp_mm="", prcp_status="no_report",
                            prcp_attr=hit["prcp_attr"], source=origin,
                            note=STATUS_NOTE["no_report"])
                missing_days += 1
                reasons.append(f"{date_str} 无降水报告(属性I)")
            elif status == "missing":
                base.update(prcp_inch=hit["prcp_inch"], prcp_mm="", prcp_status="missing",
                            prcp_attr=hit["prcp_attr"], source=origin,
                            note=f"PRCP 为缺测值(原始 {hit['prcp_inch']})")
                missing_days += 1
                reasons.append(f"{date_str} PRCP 缺测")
            elif status == "trace":
                base.update(prcp_inch=hit["prcp_inch"], prcp_mm=hit["prcp_mm"],
                            prcp_status="trace", prcp_attr=hit["prcp_attr"],
                            source=origin, note=NOTE_H)
                ok_days += 1
            elif status == "dry_I":
                base.update(prcp_inch=hit["prcp_inch"], prcp_mm=hit["prcp_mm"],
                            prcp_status="dry_I", prcp_attr=hit["prcp_attr"],
                            source=origin, note=NOTE_I)
                ok_days += 1
            else:
                base.update(prcp_inch=hit["prcp_inch"], prcp_mm=hit["prcp_mm"],
                            prcp_status="ok", prcp_attr=hit["prcp_attr"],
                            source=origin, note="")
                ok_days += 1
            day_rows.append(base)

        suspect = bool(meta["suspect"]) and content is not None
        if suspect:
            reasons.append("★站点降水字段疑似不可用（全年 0 天降水>0）")

        if missing_days == 0:
            status_text = "完整"
        elif ok_days == 0:
            status_text = "全缺"
        else:
            status_text = "部分缺失"

        year_row = {
            "city": station.city,
            "station_id": station.station_id,
            "station_name": station.name,
            "station_role": station.role,
            "year": year,
            "days_total": len(MONTH_DAY),
            "days_ok": ok_days,
            "days_missing": missing_days,
            "status": status_text,
            "year_rows": meta["rows"],
            "year_rainy_days": meta["rainy_days"],
            "year_I_days": meta["i_days"],
            "station_suspect": "是" if suspect else "",
            "reason": "；".join(reasons),
        }
        return day_rows, year_row
