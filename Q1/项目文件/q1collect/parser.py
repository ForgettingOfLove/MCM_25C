"""GSOD 原始文件解析（pandas）。

只做三件事：
    1. 读一个单站全年 CSV
    2. 把 PRCP + PRCP_ATTRIBUTES 翻译成 (毫米值, 状态)
    3. 挑出清明三天、统计全年可用性

不写文件、不发请求，纯函数。
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

from .config import INCH_TO_MM, MONTH_DAY, PRCP_MISSING

# GSOD readme 对 PRCP_ATTRIBUTES 的定义（决定这个数能不能当“日降水总量”用）
#   A 1 次 6 小时报告      B/C/D 2/3/4 次 6 小时报告之和
#   E 1 次 12 小时报告     F 2 次 12 小时报告之和
#   G 1 次 24 小时报告     ← 标准的当日总量，最理想
#   H 报 0 但观测里有降水现象 → 可能只是微量，属不完整数据
#   I 当日根本没有降水报告 → 数值不可直接当 0 用
ATTR_NOTE = {
    "H": "属性 H：报 0 但观测有降水现象，按 0 记，数据不完整",
    "I": "属性 I：无降水报告（逐时观测亦无降水），按 0 记，已标记",
}


def _clean(value: object) -> str:
    """去掉字段两侧的空白和引号；None / NaN 归空串。"""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("nan", "none"):
        return ""
    return text.strip('"').strip()


def to_inch(value: object) -> float | None:
    """把原始 PRCP 字符串转成英寸浮点数；缺测返回 None。"""
    text = _clean(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if abs(number - PRCP_MISSING) < 1e-6 or number >= 99.0:
        return None
    return number


def parse_prcp(raw: object, attr: object = "") -> tuple[float | None, str]:
    """PRCP 字段 → (毫米值, 状态)。

    状态：
        ok         A–G，正常的日总量，可直接用
        trace      H，按 0 记但数据不完整
        dry_I      I，按 0 记，需带标记
        missing    缺测（99.99 或空）
        no_report  I 且无任何数值
    """
    code = _clean(attr).upper()
    inch = to_inch(raw)
    if inch is None:
        return None, ("no_report" if code == "I" else "missing")
    if code == "H":
        return 0.0, "trace"
    if code == "I":
        return 0.0, "dry_I"
    return round(inch * INCH_TO_MM, 2), "ok"


def load_station_year(source: Path | bytes) -> pd.DataFrame:
    """读单站全年 CSV，全部按字符串读入，避免 pandas 擅自改数值。

    source 可以是磁盘路径，也可以是下载到的原始字节（省一次读盘）。
    """
    handle = io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    try:
        frame = pd.read_csv(handle, dtype=str, keep_default_na=False, encoding="utf-8")
    except (pd.errors.ParserError, UnicodeDecodeError):
        # 少数年份字段分隔符不统一，退回 Python 引擎自动嗅探
        if isinstance(handle, io.BytesIO):
            handle.seek(0)
        frame = pd.read_csv(handle, dtype=str, keep_default_na=False,
                            encoding="utf-8", sep=None, engine="python")
    frame.columns = [_clean(col).upper() for col in frame.columns]
    return frame


def _dates(frame: pd.DataFrame) -> pd.Series:
    """取 DATE 列并清洗成 YYYY-MM-DD 字符串。"""
    if "DATE" not in frame.columns:
        return pd.Series([], dtype=str)
    return frame["DATE"].map(_clean)


def profile_year(frame: pd.DataFrame) -> dict:
    """全年统计，用于站级可用性校验。

    若一整年没有一天 PRCP>0，说明该站降水字段没实际上报（西安咸阳站即属此类），
    这条序列不能用于建模。
    """
    if frame.empty:
        return {"rows": 0, "rainy_days": 0, "i_days": 0, "suspect": True}

    attributes = frame["PRCP_ATTRIBUTES"].map(_clean).str.upper() \
        if "PRCP_ATTRIBUTES" in frame.columns else pd.Series([""] * len(frame))
    rainy = frame["PRCP"].map(to_inch).apply(lambda v: (v or 0.0) > 0) \
        if "PRCP" in frame.columns else pd.Series([False] * len(frame))

    return {
        "rows": int(len(frame)),
        "rainy_days": int(rainy.sum()),
        "i_days": int((attributes == "I").sum()),
        "suspect": bool(rainy.sum() == 0),
    }


def extract_window(frame: pd.DataFrame, year: int,
                   month_days: tuple[tuple[int, int], ...] = MONTH_DAY) -> dict[str, dict]:
    """挑出清明假期三天的记录，键为 YYYY-MM-DD。找不到的日期不出现在返回值里。"""
    if frame.empty or "DATE" not in frame.columns:
        return {}

    dates = _dates(frame)
    found: dict[str, dict] = {}
    for month, day in month_days:
        target = f"{year}-{month:02d}-{day:02d}"
        hits = frame.loc[dates == target]
        if hits.empty:
            continue
        row = hits.iloc[0]
        attr = _clean(row.get("PRCP_ATTRIBUTES"))
        raw = _clean(row.get("PRCP"))
        mm, status = parse_prcp(raw, attr)
        found[target] = {
            "prcp_inch": raw,
            "prcp_mm": mm,
            "prcp_status": status,
            "prcp_attr": attr,
            "station_name_in_file": _clean(row.get("NAME")),
        }
    return found
