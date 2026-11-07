"""缺失填补：同城、同月日、其余年份的可靠观测均值。   imputer填补器(impute归罪，填补)

为什么用「历年同期」而不是全城全期均值：清明三天的雨有日序结构，4/4 与 4/6
不是同一个分布，用全期均值会把日间差异抹平，序列的年内变化直接消失。
为什么不做邻站回归：本题每城只有一个代表站，缺失率约 4%，回归引入的方差
比省下的偏差更大；真要做，留在敏感性分析里。

原则：只填「没有数」的格子。trace / dry_I 是「有数但带标记」，一律不动，
      标记留在 quality 列，敏感性分析时再决定要不要剔。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .config import (IMPUTE_POOL_EXCLUDE, MISSING_STATUS, VALUE_STATUS,
                     CleanSettings)

log = logging.getLogger(__name__)

# 填补依据的取值，写进长表 impute_basis 列，下游一眼能看出这条数怎么来的
BASIS_SAME_DAY = "同期均值"
BASIS_SAME_DAY_TRACE = "同期均值(含trace)"
BASIS_WHOLE_HOLIDAY = "三日全期均值"


@dataclass
class FillResult:
    """填补后的长表 + 逐条填补记录。"""

    frame: pd.DataFrame
    records: list[dict] = field(default_factory=list)     # 一条 = 一次填补
    unfilled: list[dict] = field(default_factory=list)    # 填不上的格子
    basis_counts: dict[str, int] = field(default_factory=dict)

    @property
    def records_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.records)

    @property
    def fill_count(self) -> int:
        return len(self.records)


class ClimatologyImputer:
    """历年同期非缺测均值填补。"""

    def __init__(self, settings: CleanSettings | None = None) -> None:
        self.settings = settings or CleanSettings()

    # ------------------------------------------------------------ 对外

    def fill(self, frame: pd.DataFrame) -> FillResult:
        data = frame.copy()
        data["prcp_mm"] = pd.to_numeric(data["prcp_mm"], errors="coerce")
        data["prcp_raw_mm"] = data["prcp_mm"]          # 留一份原始值，填补值另放 prcp_mm
        data["is_filled"] = ""
        data["impute_basis"] = ""

        status = data["prcp_status"].fillna("").astype(str)
        hole = status.isin(MISSING_STATUS) | data["prcp_mm"].isna()

        result = FillResult(frame=data)
        if not hole.any():
            log.info("无缺失，跳过填补")
            return result

        for city, group in data.groupby("city", sort=False):
            for month_day, cell in group.groupby("month_day", sort=False):
                targets = cell.index[hole.loc[cell.index]]
                if len(targets) == 0:
                    continue

                value, basis, sample = self._baseline(group, cell)
                if value is None:
                    for index in targets:
                        result.unfilled.append({
                            "city": city, "date": data.at[index, "date"],
                            "status_before": data.at[index, "prcp_status"],
                        })
                    log.warning("  %s %s 无法填补：该城无任何可靠观测", city, month_day)
                    continue

                data.loc[targets, "prcp_mm"] = value
                data.loc[targets, "is_filled"] = "是"
                data.loc[targets, "impute_basis"] = f"{basis} n={sample}"
                for index in targets:
                    result.records.append({
                        "city": city,
                        "date": data.at[index, "date"],
                        "status_before": data.at[index, "prcp_status"],
                        "filled_mm": value,
                        "basis": basis,
                        "n_samples": sample,
                    })
                result.basis_counts[basis] = result.basis_counts.get(basis, 0) + len(targets)

        log.info("填补 %d 条（%s）", result.fill_count,
                 "、".join(f"{k} {v}" for k, v in result.basis_counts.items()) or "无")
        return result

    # ------------------------------------------------------------ 内部

    def _baseline(self, group: pd.DataFrame, cell: pd.DataFrame
                  ) -> tuple[float | None, str, int]:
        """给某城某一月日算填补基线，返回 (值, 依据, 参与年数)。

        三级回退：同期可靠均值 → 同期含 trace 均值 → 该城三日全期均值。
        样本量不够 min_sample 就降一级，直到没数可用返回 None。
        """
        min_sample = self.settings.min_sample
        decimals = self.settings.decimals

        def usable(part: pd.DataFrame, exclude_trace: bool) -> pd.Series:
            status = part["prcp_status"].fillna("").astype(str)
            mask = status.isin(VALUE_STATUS)
            if exclude_trace:
                mask &= ~status.isin(IMPUTE_POOL_EXCLUDE)
            return pd.to_numeric(part.loc[mask, "prcp_mm"], errors="coerce").dropna()

        same_strict = usable(cell, exclude_trace=True)
        if len(same_strict) >= min_sample:
            return round(float(same_strict.mean()), decimals), BASIS_SAME_DAY, len(same_strict)

        same_all = usable(cell, exclude_trace=False)
        if len(same_all) >= min_sample:
            return (round(float(same_all.mean()), decimals),
                    BASIS_SAME_DAY_TRACE, len(same_all))

        whole = usable(group, exclude_trace=False)
        if len(whole) > 0:
            return (round(float(whole.mean()), decimals),
                    BASIS_WHOLE_HOLIDAY, len(whole))

        return None, "", 0
