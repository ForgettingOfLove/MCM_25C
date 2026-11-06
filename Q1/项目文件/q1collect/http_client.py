"""GSOD 下载客户端（requests）。

两种取数通道：
    access  —— /access/{year}/{station_id}.csv，单站单年切片，几十 KB，首选
    archive —— /archive/{year}.tar.gz，逐年全站打包（约 80 MB），流式抽取单个成员

默认 auto：先走 access，404 再回退 archive。
"""

from __future__ import annotations

import logging
import tarfile
import time
from pathlib import Path

import requests

from .config import ACCESS_BASE, ARCHIVE_BASE, DEFAULT_SETTINGS, RequestSettings

log = logging.getLogger(__name__)


class GsodClient:
    """负责“把某个站某年的 CSV 拿到手”，不负责解析。"""

    def __init__(self, settings: RequestSettings | None = None) -> None:
        self.settings = settings or DEFAULT_SETTINGS
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.settings.user_agent})

    # ------------------------------------------------------------ 底层

    def _get_bytes(self, url: str) -> bytes:
        """带指数退避的 GET。404 直接抛，交给上层判断是否回退。"""
        last_error: Exception | None = None
        for attempt in range(1, self.settings.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.settings.timeout)
                if resp.status_code == 404:
                    resp.close()
                    raise requests.HTTPError(f"404 {url}", response=resp)
                resp.raise_for_status()
                return resp.content
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    raise
                last_error = exc
            except requests.RequestException as exc:
                last_error = exc
            if attempt < self.settings.retries:
                wait = self.settings.backoff ** attempt
                log.warning("    请求失败，%.1fs 后重试 %d/%d：%s",
                            wait, attempt, self.settings.retries - 1, url)
                time.sleep(wait)
        raise last_error  # type: ignore[misc]

    def _get_from_archive(self, year: int, station_id: str) -> bytes | None:
        """流式读 tar.gz，命中目标成员即断开，不落盘整个压缩包。"""
        url = f"{ARCHIVE_BASE}/{year}.tar.gz"
        member_name = f"{station_id}.csv"
        log.info("    回退 archive：%s → 抽取 %s", url, member_name)
        resp = self.session.get(url, timeout=self.settings.timeout, stream=True)
        try:
            resp.raise_for_status()
            with tarfile.open(fileobj=resp.raw, mode="r|gz") as tar:
                for member in tar:
                    if Path(member.name).name == member_name:
                        handle = tar.extractfile(member)
                        return handle.read() if handle else None
        finally:
            resp.close()
        return None

    # ------------------------------------------------------------ 对外

    def fetch(self, station_id: str, year: int, cache_file: Path,
              source: str = "auto", use_cache: bool = True) -> tuple[bytes | None, str]:
        """取回某站某年 CSV，并写入缓存。

        返回 (内容, 来源标记)。来源标记 ∈ {cache, access, archive, 404, error}。
        """
        if use_cache and cache_file.is_file() and cache_file.stat().st_size > 0:
            return cache_file.read_bytes(), "cache"

        data: bytes | None = None
        origin = "404"

        if source in ("auto", "access"):
            url = f"{ACCESS_BASE}/{year}/{station_id}.csv"
            try:
                data = self._get_bytes(url)
                origin = "access"
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 404:
                    raise
                if source == "access":
                    return None, "404"
            except requests.RequestException as exc:
                log.warning("    access 请求失败：%s", exc)
                if source == "access":
                    return None, "error"

        if data is None and source in ("auto", "archive"):
            try:
                data = self._get_from_archive(year, station_id)
                origin = "archive" if data else "404"
            except (requests.RequestException, tarfile.TarError) as exc:
                log.warning("    archive 抽取失败：%s", exc)
                return None, "404"

        if data is None:
            return None, "404"

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(data)
        return data, origin

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "GsodClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
