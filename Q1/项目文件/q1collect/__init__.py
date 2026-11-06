"""Q1 数据采集包。

用途：从 NOAA GSOD 抓取七城 2006—2025 年清明三日（4/4—4/6）日降水量。
只做采集，不做预处理。

模块职责
    paths.py       ProjectPaths     目录与文件路径（pathlib）
    config.py      Station 等       年份、站点映射、请求参数（唯一改参数的地方）
    http_client.py GsodClient       requests 下载 + 重试 + 缓存 + archive 回退
    parser.py      —                原始 CSV 解析、PRCP 语义、三日提取
    collector.py   RainCollector    城市 × 年份循环编排
    reporter.py    ResultReporter   三张表 + JSON 汇总落盘
"""

from __future__ import annotations

__version__ = "0.1.0"

from .collector import CollectResult, RainCollector
from .config import MONTH_DAY, STATIONS, RequestSettings, Station, YEARS
from .http_client import GsodClient
from .paths import ProjectPaths
from .reporter import ResultReporter

__all__ = [
    "CollectResult",
    "RainCollector",
    "GsodClient",
    "ProjectPaths",
    "ResultReporter",
    "Station",
    "RequestSettings",
    "STATIONS",
    "YEARS",
    "MONTH_DAY",
    "__version__",
]
