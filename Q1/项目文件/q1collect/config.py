"""全局配置：年份窗口、清明三天、城市→站点映射、请求参数。

整个项目**只在这里改参数**。数据口径、站号、年份写死于此，
其余模块一律 import，不重复定义。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- 时间窗口

YEARS: tuple[int, ...] = tuple(range(2006, 2026))   # 2006—2025
MONTH_DAY: tuple[tuple[int, int], ...] = ((4, 4), (4, 5), (4, 6))  # 清明假期三天

# ---------------------------------------------------------------- 数值约定

PRCP_MISSING = 99.99          # GSOD 缺测哨兵值（英寸）
INCH_TO_MM = 25.4             # 原始单位为英寸
VALID_STATUS = {"ok", "trace", "dry_I"}   # 视为“有值可用”的状态

# ---------------------------------------------------------------- 数据源

ACCESS_BASE = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access"
ARCHIVE_BASE = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive"


# ---------------------------------------------------------------- 站点

@dataclass(frozen=True)
class Station:
    """一个城市的代表站点。

    role 只有两种取值：
        "本市站点"    —— 站点在市区或近郊，可直接代表城市
        "邻近替代站"  —— 本市无可用站，用邻站代替，报告中必须交代
    """

    city: str
    station_id: str
    name: str
    lat: float
    lon: float
    role: str
    note: str
    city_lat: float
    city_lon: float


# GSOD 文件名 = USAF + WBAN 拼成 11 位；站点坐标取自 stations.txt
STATIONS: dict[str, Station] = {
    "西安": Station(
        city="西安", station_id="57131099999", name="JINGHE（西安泾河）",
        lat=34.433, lon=108.967, role="本市站点",
        city_lat=34.3416, city_lon=108.9398,
        note="距市中心约 10 km，为西安国家站现址。原 WMO 57036（咸阳）在 GSOD 中的 PRCP "
             "字段整体不可用——整年没有一天降水>0，且约 62% 的日期被标记为 I（无降水报告），"
             "不能用于序列建模。泾河站 2006-10 建站，故 2006 年清明三天缺测（n=19），"
             "可在预处理阶段以邻站补充。",
    ),
    "吐鲁番": Station(
        city="吐鲁番", station_id="51573099999", name="TURPAN（吐鲁番）",
        lat=42.950, lon=89.230, role="本市站点",
        city_lat=42.9513, city_lon=89.1895,
        note="WMO 51573，距市中心约 3 km。",
    ),
    "婺源": Station(
        city="婺源", station_id="58527099999", name="JINGDEZHEN（景德镇）",
        lat=29.300, lon=117.200, role="邻近替代站",
        city_lat=29.2479, city_lon=117.8617,
        note="GSOD 无婺源本站（原 58529 仅有 1980—1984 年残段）。取最近活跃站景德镇，"
             "直线距离约 64 km，同属赣东北、地形与气候区接近；婺源本地降水存在系统偏差风险，"
             "结论中需说明。",
    ),
    "杭州": Station(
        city="杭州", station_id="58457099999", name="XIAOSHAN（杭州萧山）",
        lat=30.228, lon=120.432, role="本市站点",
        city_lat=30.2741, city_lon=120.1551,
        note="WMO 58457，即杭州本站（萧山），距市中心约 27 km。",
    ),
    "毕节": Station(
        city="毕节", station_id="57707099999", name="BIJIE（毕节）",
        lat=27.300, lon=105.233, role="本市站点",
        city_lat=27.3017, city_lon=105.2853,
        note="WMO 57707，距市中心约 5 km。",
    ),
    "武汉": Station(
        city="武汉", station_id="57494099999", name="TIANHE（武汉天河）",
        lat=30.784, lon=114.208, role="本市站点",
        city_lat=30.5928, city_lon=114.3055,
        note="WMO 57494，即武汉天河站，距市中心约 23 km。",
    ),
    "洛阳": Station(
        city="洛阳", station_id="57071099999", name="MENGJIN（洛阳孟津）",
        lat=34.817, lon=112.433, role="邻近替代站",
        city_lat=34.6197, city_lon=112.4540,
        note="洛阳本站 570730 LUO-YANG 于 2004-07-28 停测，2006—2025 无数据；"
             "改用同属洛阳市辖的孟津站，直线距离约 22 km。",
    ),
}


# ---------------------------------------------------------------- 请求参数

@dataclass
class RequestSettings:
    """HTTP 行为。公共服务器，限速是礼貌也是自保。"""

    timeout: int = 90                 # 单请求超时（秒）
    retries: int = 3                  # 失败重试次数
    backoff: float = 2.0              # 退避基数：第 n 次失败等 backoff**n 秒
    pause: float = 0.6                # 相邻请求间隔（秒）
    user_agent: str = "Mozilla/5.0 (ZUST MCM Q1 collector; academic use)"


DEFAULT_SETTINGS = RequestSettings()
