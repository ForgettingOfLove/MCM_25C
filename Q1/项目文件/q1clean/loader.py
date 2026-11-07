"""读采集表 → 校验 → 补齐网格。

采集表理论上 7 城 × 20 年 × 3 天 = 420 行，但用 --city / --years 跑过、
或者中途中断，行数就会少。「文件里没有这一天」在采集表里是有行的（状态 no_row），
真正缺行只可能来自筛选参数，这里统一补齐成 no_row，交给填补环节处理。

只读不写，不改磁盘上的采集表。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from q1collect.config import STATIONS
from q1collect.paths import ProjectPaths

from .config import MISSING_STATUS, MONTH_DAY_LABEL

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("city", "date", "prcp_status", "prcp_mm")


@dataclass
class LoadResult:
    """读进来的采集表 + 体检结论。"""

    frame: pd.DataFrame
    source: Path
    rows_expected: int = 0
    rows_found: int = 0
    rows_added: int = 0
    duplicates: int = 0
    cities: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CollectTableLoader:
    """把采集表读成「完整网格 + 干净类型」的 DataFrame。"""

    def __init__(self, paths: ProjectPaths) -> None:
        self.paths = paths

    # ------------------------------------------------------------ 定位输入

    def resolve(self, name: str | Path | None = None) -> Path:
        """输入表路径。

        不给就用全量表；全量表不在，退而取 tables 下最新的 rain_*.csv，
        这样 --years 跑出来的子集也能直接喂进来。
        """
        if name:
            path = Path(name)
            if not path.is_absolute():
                path = (self.paths.root / path).resolve()
            if not path.exists():
                raise FileNotFoundError(f"输入表不存在：{path}")
            return path

        preferred = self.paths.table("rain_2006_2025.csv")
        if preferred.exists():
            return preferred

        candidates = sorted(self.paths.tables.glob("rain_*.csv"))
        if not candidates:
            raise FileNotFoundError(
                f"{self.paths.rel(self.paths.tables)} 下没有 rain_*.csv，先跑 main.py"
            )
        log.warning("未找到全量表，改用 %s", self.paths.rel(candidates[-1]))
        return candidates[-1]

    # ------------------------------------------------------------ 主流程

    def load(self, source: str | Path | None = None,
             cities: list[str] | None = None,
             years: list[int] | None = None) -> LoadResult:
        path = self.resolve(source)
        raw = self._read_csv(path)
        self._check_columns(raw, path)

        frame = self._normalize(raw)
        cities = list(cities or [c for c in STATIONS if c in set(frame["city"])])
        unknown = [c for c in cities if c not in STATIONS]
        if unknown:
            raise ValueError(f"未知城市：{unknown}，可选：{list(STATIONS)}")
        years = sorted(years or sorted(frame["year"].unique().tolist()))

        result = LoadResult(frame=frame, source=path,
                            rows_found=len(frame), cities=cities, years=years)

        subset = frame[frame["city"].isin(cities) & frame["year"].isin(years)]
        duplicated = int(subset.duplicated(subset=["city", "date"]).sum())
        if duplicated:
            result.warnings.append(f"采集表有 {duplicated} 条重复的 city+date，保留首条")
            subset = subset.drop_duplicates(subset=["city", "date"], keep="first")

        result.duplicates = duplicated
        result.rows_expected = len(cities) * len(years) * len(MONTH_DAY_LABEL)
        result.frame = self._fill_grid(subset, cities, years, result)
        return result

    # ------------------------------------------------------------ 内部

    @staticmethod
    def _read_csv(path: Path) -> pd.DataFrame:
        """全部按字符串读入：采集表里空值表示缺失，不能让 pandas 自己猜类型。"""
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                return pd.read_csv(path, dtype=str, keep_default_na=False,
                                   encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError("utf-8/gbk", b"", 0, 1, f"无法解码 {path}")

    @staticmethod
    def _check_columns(frame: pd.DataFrame, path: Path) -> None:
        missing = [col for col in REQUIRED_COLUMNS if col not in frame.columns]
        if missing:
            raise ValueError(f"{path.name} 缺列 {missing}，不是有效的采集表")

    @staticmethod
    def _normalize(frame: pd.DataFrame) -> pd.DataFrame:
        """去空白、转数值、补派生列；不在这里做任何填补。"""
        data = frame.copy()
        data.columns = [str(col).strip() for col in data.columns]

        for col in data.columns:
            if data[col].dtype == object:
                data[col] = data[col].map(lambda v: str(v).strip() if v is not None else "")

        data["date"] = data["date"].str.replace("/", "-", regex=False)
        data["year"] = data["date"].str[:4].astype(int)
        data["month_day"] = data["date"].str[5:]
        data["prcp_mm"] = pd.to_numeric(data["prcp_mm"], errors="coerce")
        if "prcp_inch" in data.columns:
            data["prcp_inch"] = pd.to_numeric(data["prcp_inch"], errors="coerce")
        else:
            data["prcp_inch"] = pd.NA

        data["station_name"] = data.get("station_name", "")
        data["station_role"] = data.get("station_role", "")
        data["note"] = data.get("note", "")
        return data

    def _fill_grid(self, frame: pd.DataFrame, cities: list[str],
                   years: list[int], result: LoadResult) -> pd.DataFrame:
        """按 城市 × 年 × 三日 的完整网格左连接，缺的补成 no_row。"""
        dates = [f"{year}-{md}" for year in years for md in MONTH_DAY_LABEL]
        grid = pd.MultiIndex.from_product([cities, dates],
                                          names=["city", "date"]).to_frame(index=False)

        merged = grid.merge(frame, on=["city", "date"], how="left", indicator=True)
        added = merged["_merge"] == "left_only"
        result.rows_added = int(added.sum())
        if result.rows_added:
            result.warnings.append(f"网格缺 {result.rows_added} 行，已按 no_row 补齐")

        merged["year"] = merged["date"].str[:4].astype(int)
        merged["month_day"] = merged["date"].str[5:]
        merged["prcp_status"] = merged["prcp_status"].fillna("no_row")
        merged["prcp_mm"] = pd.to_numeric(merged["prcp_mm"], errors="coerce")
        merged.loc[added, "prcp_status"] = "no_row"
        merged.loc[added, "note"] = "采集表缺行，预处理补齐"

        # 站点信息按 config 兜底，避免补齐行缺字段
        for city in cities:
            station = STATIONS[city]
            mask = merged["city"] == city
            merged.loc[mask, "station_id"] = merged.loc[mask, "station_id"].fillna(
                station.station_id)
            merged.loc[mask, "station_name"] = merged.loc[mask, "station_name"].fillna(
                station.name)
            merged.loc[mask, "station_role"] = merged.loc[mask, "station_role"].fillna(
                station.role)

        merged = merged.drop(columns=["_merge"])
        merged["_city_order"] = merged["city"].map({city: i for i, city in enumerate(cities)})
        merged = merged.sort_values(["_city_order", "date"]).drop(columns=["_city_order"])

        flagged = merged["prcp_status"].isin(MISSING_STATUS) & merged["note"].eq("")
        if flagged.any():
            result.warnings.append(f"{int(flagged.sum())} 条缺失记录没有说明文字")
        return merged.reset_index(drop=True)
