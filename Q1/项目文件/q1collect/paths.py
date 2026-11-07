"""项目目录管理。

全部路径统一用 pathlib.Path 处理，不出现 os.path.join 或手写字符串拼接。
任何模块需要落盘，都从这里拿目录，不要在别处硬编码。
"""

from __future__ import annotations

from pathlib import Path

# 本文件位于 <项目根>/q1collect/paths.py，向上两级即项目根
DEFAULT_ROOT = Path(__file__).resolve().parent.parent


class ProjectPaths:
    """项目目录树。

        <root>/
        ├── data/
        │   ├── raw/         原始下载缓存，一站一年一个文件
        │   └── processed/   预处理产物（本阶段留空）
        ├── output/
        │   ├── tables/      结构化结果表
        │   └── logs/        运行日志
    """

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root).resolve() if root else DEFAULT_ROOT
        self.data = self.root / "data"
        self.raw = self.data / "raw"
        self.processed = self.data / "processed"
        self.output = self.root / "output"
        self.tables = self.output / "tables"
        self.logs = self.output / "logs"

    # ---- 目录 ----

    def ensure(self) -> "ProjectPaths":
        """创建全部目录（幂等），返回自身以便链式调用。"""
        for folder in (self.raw, self.processed, self.tables, self.logs):
            folder.mkdir(parents=True, exist_ok=True)
        return self

    # ---- 文件 ----

    def raw_file(self, station_id: str, year: int) -> Path:
        """单站单年的原始文件路径。"""
        return self.raw / f"{station_id}_{year}.csv"

    def table(self, name: str) -> Path:
        """结果表路径，如 table("fetch_report.csv")。"""
        return self.tables / name

    def processed_file(self, name: str) -> Path:
        """预处理产物路径，如 processed_file("rain_all.csv")。"""
        return self.processed / name

    def log_file(self, name: str = "fetch_log.txt") -> Path:
        return self.logs / name

    def rel(self, path: Path) -> str:
        """相对项目根的展示路径，日志里用，避免刷屏绝对路径。"""
        try:
            return str(Path(path).resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def __repr__(self) -> str:  # pragma: no cover
        return f"ProjectPaths(root={self.root})"
