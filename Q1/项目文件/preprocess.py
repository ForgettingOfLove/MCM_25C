#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Q1 数据预处理入口。

用法（虚拟环境激活后，在项目根目录执行）：
    python preprocess.py                                  # 全量：7 城 2006—2025
    python preprocess.py --input output/tables/rain_2020_2025.csv
    python preprocess.py --city 西安 武汉                  # 只处理指定城市
    python preprocess.py --years 2015 2025                # 只处理指定年份
    python preprocess.py --min-sample 8                   # 同期均值至少 8 年
    python preprocess.py --strict                         # 有填不上的缺失就中断
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from q1clean import (CleanReporter, CleanSettings, Preprocessor,
                     SMALL_RAIN_MAX, SMALL_RAIN_MIN)
from q1collect import MONTH_DAY, STATIONS, ProjectPaths

log = logging.getLogger("q1clean")


# ---------------------------------------------------------------- 参数

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q1-clean",
        description="把采集表清洗成可建模序列：缺失填补、派生列、宽表、质量体检",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", type=Path, metavar="文件",
                        help="采集表路径，默认 output/tables/rain_2006_2025.csv")
    parser.add_argument("--city", nargs="+", metavar="城市",
                        help=f"只处理指定城市，可选：{'、'.join(STATIONS)}")
    parser.add_argument("--years", nargs="+", type=int, metavar="年",
                        help="只处理指定年份，默认取表里全部年份")
    parser.add_argument("--min-sample", type=int, metavar="年数",
                        help="同期均值至少要几年，默认 5")
    parser.add_argument("--strict", action="store_true",
                        help="出现无法填补的缺失就中断，不静默放过")
    return parser  # 参数容器


def setup_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)


def report_to_console(result, cities: list[str]) -> None:
    """终端汇总：每城一行 + 填补明细 + 需注意项。"""
    city_frame = result.quality.city_frame.set_index("city")
    years = result.load.years

    log.info("")
    log.info("-" * 78)
    log.info("汇总：%d 条日记录，%d—%d 年，%d 城，填补 %d 条，填不上 %d 条",
             len(result.long), years[0], years[-1], len(cities),
             result.filled, result.unfilled)
    log.info("-" * 78)
    for city in cities:
        row = city_frame.loc[city]
        log.info("%s  %s  原始有效 %d/%d  填补 %d  均值 %.2f mm  零值年 %d/%d",
                 city, row["station_name"], int(row["days_obs"]), int(row["days_total"]),
                 int(row["days_filled"]), float(row["prcp_mean_mm"]),
                 int(row["series_zero_years"]), len(years))

    if result.fill.records:
        log.info("")
        log.info("填补明细（共 %d 条）：", result.filled)
        for record in result.fill.records:
            log.info("  · %s %s  %-9s → %5.2f mm（%s n=%d）",
                     record["city"], record["date"], record["status_before"],
                     record["filled_mm"], record["basis"], record["n_samples"])

    if result.quality.issues:
        log.info("")
        log.info("需注意：")
        for issue in result.quality.issues:
            log.info("  · %s", issue)

    log.info("")
    log.info("-" * 78)
    log.info("提示：本阶段只处理降水量维度。雨纷纷判据 = 小雨 %.1f–%.1f mm/24h",
             SMALL_RAIN_MIN, SMALL_RAIN_MAX)
    log.info("      时长数据（rp5.ru / ISD）未接入，dur_h 与 is_yufengfen 整列为空。")
    log.info("      清明三天：%s", "、".join(f"{m:02d}-{d:02d}" for m, d in MONTH_DAY))
    log.info("-" * 78)


# ---------------------------------------------------------------- 主流程

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    paths = ProjectPaths()
    paths.ensure()
    setup_logging(paths.log_file("clean_log.txt"))

    settings = CleanSettings()
    if args.min_sample is not None:
        settings.min_sample = args.min_sample
    settings.strict = args.strict

    cities = args.city or list(STATIONS)
    unknown = [c for c in cities if c not in STATIONS]
    if unknown:
        log.error("未知城市：%s；可选 %s", unknown, list(STATIONS))
        return 2

    preprocessor = Preprocessor(paths, settings)
    try:
        result = preprocessor.run(source=str(args.input) if args.input else None,
                                  cities=cities, years=args.years)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2
    except RuntimeError as exc:
        log.error("%s", exc)
        return 3

    reporter = CleanReporter(paths, settings)
    reporter.write_all(result.long, result.wide, result.series,
                       result.quality, result.fill, result.load)

    report_to_console(result, cities=list(cities))
    log.info("日志：%s", paths.rel(paths.log_file("clean_log.txt")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
