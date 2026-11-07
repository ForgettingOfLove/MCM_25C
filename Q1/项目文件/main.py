#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Q1 数据采集入口。

用法（虚拟环境激活后，在项目根目录执行）：
    python main.py                          # 七城 2006—2025 全抓
    python main.py --city 杭州 洛阳          # 只抓指定城市
    python main.py --years 2020 2021 2025   # 只抓指定年份
    python main.py --source archive         # 强制走 /archive/*.tar.gz
    python main.py --no-cache               # 忽略 data/raw 缓存重新下载
    python main.py --raw-dir ../code/raw    # 复用别处的缓存，不重复下载
"""

from __future__ import annotations

import argparse        # argument parse参数解析
import logging
import sys
from pathlib import Path

from q1collect import (MONTH_DAY, STATIONS, YEARS, GsodClient, ProjectPaths,
                       RainCollector, RequestSettings, ResultReporter)

log = logging.getLogger("q1collect")


# ---------------------------------------------------------------- 参数

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q1-collect",
        description="抓取 NOAA GSOD 七城 2006—2025 年清明三日降水量（只采集，不预处理）",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--city", nargs="+", metavar="城市",
                        help=f"只抓指定城市，可选：{'、'.join(STATIONS)}")
    parser.add_argument("--years", nargs="+", type=int, metavar="年",
                        help="只抓指定年份，默认 2006—2025")
    parser.add_argument("--source", choices=["auto", "access", "archive"], default="auto",
                        help="auto=优先分站切片，404 回退打包文件")
    parser.add_argument("--no-cache", action="store_true",
                        help="忽略 data/raw 缓存，全部重新下载")
    parser.add_argument("--raw-dir", type=Path, metavar="目录",
                        help="原始文件缓存目录，默认 data/raw")
    parser.add_argument("--pause", type=float, metavar="秒",
                        help="相邻请求间隔，默认 0.6")
    parser.add_argument("--no-progress", action="store_true", help="关闭进度条")
    parser.add_argument("--list-cities", action="store_true", help="打印站点映射后退出")
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


def print_cities() -> None:
    print(f"{'城市':<6}{'站号':<13}{'站点名称':<22}{'性质':<10}坐标")
    for city, st in STATIONS.items():
        print(f"{city:<6}{st.station_id:<13}{st.name:<22}{st.role:<10}"
              f"{st.lat:.3f}, {st.lon:.3f}")


def report_to_console(result, cities: list[str], years: list[int]) -> None:
    """终端汇总：每城一行，比对齐表格更耐看（中文列宽对不齐）。"""
    report = result.report_frame
    log.info("")
    log.info("-" * 70)
    log.info("汇总：共 %d 条日记录，%d—%d 年，%d 城",
             len(result.records), years[0], years[-1], len(cities))
    log.info("-" * 70)
    for city in cities:
        st = STATIONS[city]
        sub = report[report["city"] == city]
        ok_years = int((sub["status"] == "完整").sum())
        log.info("%-4s %-20s 完整年 %2d/%d  日有效 %2d/%d",
                 city, st.name[:18], ok_years, len(sub),
                 int(sub["days_ok"].sum()), int(sub["days_total"].sum()))
    bad = report[report["status"] != "完整"]
    if bad.empty:
        log.info("所有城市全部完整，无缺失。")
    else:
        log.info("需注意：")
        for _, row in bad.iterrows():
            log.info("  · %s %d（%s）：%s", row["city"], row["year"],
                     row["status"], row["reason"])
    log.info("-" * 70)
    log.info("提示：本脚本只负责采集，缺失填补与序列构造在预处理阶段完成。")
    log.info("      清明三天：%s", "、".join(f"{m:02d}-{d:02d}" for m, d in MONTH_DAY))


# ---------------------------------------------------------------- 主流程

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_cities:
        print_cities()
        return 0

    paths = ProjectPaths()
    if args.raw_dir:
        paths.raw = args.raw_dir.resolve()
    paths.ensure()
    setup_logging(paths.log_file())

    cities = args.city or list(STATIONS)
    unknown = [c for c in cities if c not in STATIONS]
    if unknown:
        log.error("未知城市：%s；可选 %s", unknown, list(STATIONS))
        return 2

    years = tuple(args.years) if args.years else YEARS
    years = tuple(sorted(set(years)))
    bad_years = [y for y in years if y < 1929 or y > 2025]
    if bad_years:
        log.error("GSOD 覆盖 1929—2025，这些年份越界：%s", bad_years)
        return 2

    settings = RequestSettings()
    if args.pause is not None:
        settings.pause = args.pause

    with GsodClient(settings) as client:
        collector = RainCollector(paths, client=client, settings=settings)
        try:
            result = collector.collect(
                cities=cities, years=years, source=args.source,
                use_cache=not args.no_cache, show_progress=not args.no_progress,
            )
        except KeyboardInterrupt:
            log.warning("已手动中断，本次结果不落盘。")
            return 130

    reporter = ResultReporter(paths)
    reporter.write_all(result, cities=list(cities), years=list(years),
                       source_mode=args.source)

    report_to_console(result, cities=list(cities), years=list(years))
    log.info("日志：%s", paths.rel(paths.log_file()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
