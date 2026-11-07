"""派生列、宽表与建模序列。

全部纯函数，不落盘、不打日志。
「雨纷纷」判定单独拎成 judge_yufengfen()：时长数据还没接上时它返回 None，
不替数据做决定——把降水量当成长度硬凑成布尔列，等于把结论建在假设上。
"""

from __future__ import annotations

import pandas as pd

from .config import (DURATION_MIN_H, MONTH_DAY_LABEL, NO_RAIN_LABEL,
                     RAIN_LEVELS, SMALL_RAIN_MAX, SMALL_RAIN_MIN)

FLAG_YES = "是"


# ---------------------------------------------------------------- 判据

def _to_number(value: object) -> float | None:
    """把可能是空串 / NaN / 数字的单元格统一成 float | None。"""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        value = text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) else number


def rain_level(prcp_mm: float | None) -> str:
    """GB/T 28592—2012 的 24 h 降水等级；缺失返回空串。"""
    value = _to_number(prcp_mm)
    if value is None:
        return ""
    for lower, label in RAIN_LEVELS:      # 已按从大到小排
        if value >= lower:
            return label
    return NO_RAIN_LABEL


def is_small_rain(prcp_mm: float | None) -> bool | None:
    """是否落在小雨量级（0.1–9.9 mm/24 h）。缺失返回 None。"""
    value = _to_number(prcp_mm)
    if value is None:
        return None
    return SMALL_RAIN_MIN <= value <= SMALL_RAIN_MAX


def judge_yufengfen(prcp_mm: float | None, dur_h: float | str | None) -> bool | None:
    """单日「雨纷纷」判定：小雨量级 且 降水时长 ≥ 3 h。

    任一维度缺失就返回 None（未知），不当 False 处理。
    时长数据（rp5.ru / ISD）尚未接入，本阶段整列留空，
    4.4 之后接上直接重跑即可，口径不用改。
    """
    small = is_small_rain(prcp_mm)
    hours = _to_number(dur_h)
    if small is None or hours is None:
        return None
    return bool(small and hours >= DURATION_MIN_H)


# ---------------------------------------------------------------- 长表派生列

def add_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """给长表加 quality / prcp_level / 判据列。"""
    data = frame.copy()
    status = data["prcp_status"].fillna("").astype(str)

    data["quality"] = status.where(data["is_filled"] != FLAG_YES, "imputed")
    data["prcp_level"] = data["prcp_mm"].map(rain_level)
    data["prcp_in_small_range"] = data["prcp_mm"].map(
        lambda value: FLAG_YES if is_small_rain(value) else "")

    # 时长与判定：本阶段没有时长数据，整列留空，口径先立在这里
    if "dur_h" not in data.columns:
        data["dur_h"] = ""
    data["is_yufengfen"] = [
        "" if verdict is None else (FLAG_YES if verdict else "否")
        for verdict in (judge_yufengfen(p, d)
                        for p, d in zip(data["prcp_mm"], data["dur_h"]))
    ]

    note = data.get("note", pd.Series([""] * len(data), index=data.index)).fillna("").astype(str)
    filled_note = "填补：" + data["impute_basis"].astype(str) + "；原状态 " + status
    data["note"] = note.where(data["is_filled"] != FLAG_YES, filled_note)
    return data


# ---------------------------------------------------------------- 宽表与序列

def to_wide(frame: pd.DataFrame) -> pd.DataFrame:
    """长表 → 城 × 年 一行，三日展开。论文表与判据都用这张。"""
    keys = ["city", "station_id", "station_role", "year"]
    day_cols = [f"prcp_{md.replace('-', '')}" for md in MONTH_DAY_LABEL]

    values = frame.pivot_table(index=keys, columns="month_day",
                               values="prcp_mm", aggfunc="first")
    marks = frame.pivot_table(index=keys, columns="month_day",
                             values="is_filled", aggfunc="first")
    values = values.reindex(columns=list(MONTH_DAY_LABEL))
    marks = marks.reindex(columns=list(MONTH_DAY_LABEL)).fillna("")

    # 在同一个 MultiIndex 上算，再一起 reset_index，否则列会对不齐
    values["filled_days"] = (marks == FLAG_YES).sum(axis=1).astype(int)
    values = values.reset_index()
    values.columns.name = None
    values = values.rename(columns={md: f"prcp_{md.replace('-', '')}"
                                    for md in MONTH_DAY_LABEL})
    values = values[keys + day_cols + ["filled_days"]]

    days = values[day_cols]
    values["prcp_sum_mm"] = days.sum(axis=1, skipna=False).round(2)
    values["prcp_max_mm"] = days.max(axis=1, skipna=True).round(2)
    values["rainy_days"] = (days > 0).sum(axis=1).astype(int)
    values["small_rain_days"] = days.map(
        lambda value: bool(is_small_rain(value))).sum(axis=1).astype(int)
    values["all_imputed"] = (values["filled_days"] == len(MONTH_DAY_LABEL)).map(
        lambda flag: FLAG_YES if flag else "")

    values["_city_order"] = values["city"].map(
        {city: i for i, city in enumerate(frame["city"].drop_duplicates())})
    values = values.sort_values(["_city_order", "year"]).drop(columns=["_city_order"])
    return values.reset_index(drop=True)


def to_series(wide: pd.DataFrame) -> pd.DataFrame:
    """宽表 → 建模序列（一城一年一行，只留序列本体与质量标记）。

    ARIMA 每城一条 20 点的年序列，prcp_sum_mm 是主序列；
    另外两列给敏感性分析用，不给模型当输入。
    """
    columns = ["city", "station_id", "station_role", "year", "prcp_sum_mm",
               "prcp_max_mm", "rainy_days", "small_rain_days",
               "filled_days", "all_imputed"]
    return wide.reindex(columns=columns).copy()
