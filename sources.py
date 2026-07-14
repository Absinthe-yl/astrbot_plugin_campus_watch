from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

import httpx


YEAR_PATTERNS = (
    "2027届",
    "27届",
    "2027 campus",
    "2027 graduate",
    "2027届校招",
    "2027届实习",
    "27届实习",
    "27届校招",
    "27届及以后",
    "2027届及以后",
)
GENERAL_PATTERNS = (
    "校园招聘",
    "campus",
    "应届生",
    "校招",
    "graduate",
)


@dataclass
class SourceResult:
    company: str
    url: str
    opened: bool
    checked_at: str
    content_hash: str
    evidence: str
    error: str | None = None


@dataclass(frozen=True)
class SourceDefinition:
    company: str
    url: str


DEFAULT_SOURCES = [
    SourceDefinition("腾讯", "https://join.qq.com/"),
    SourceDefinition("字节跳动", "https://jobs.bytedance.com/campus"),
    SourceDefinition("华为", "https://career.huawei.com/cn/campus-recruitment"),
    SourceDefinition("阿里巴巴", "https://talent.alibaba.com/campus"),
    SourceDefinition("京东", "https://campus.jd.com/"),
    SourceDefinition("小米", "https://hr.xiaomi.com/campus"),
    SourceDefinition("网易", "https://campus.163.com/"),
    SourceDefinition("拼多多", "https://careers.pinduoduo.com/campus"),
    SourceDefinition("百度", "https://talent.baidu.com/jobs/trend"),
    SourceDefinition("美团", "https://zhaopin.meituan.com/web/official/home"),
]


class OfficialCampusSourceAdapter:
    """Fetches official campus pages and detects 27th-cohort keywords."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def fetch(self, source: SourceDefinition) -> SourceResult:
        checked_at = datetime.now().isoformat(timespec="seconds")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    )
                },
            ) as client:
                response = await client.get(source.url)
                response.raise_for_status()
        except Exception as exc:
            return SourceResult(
                company=source.company,
                url=source.url,
                opened=False,
                checked_at=checked_at,
                content_hash="",
                evidence="",
                error=str(exc),
            )

        text = self._normalize_text(response.text)
        content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        opened, evidence = self._detect_opening(text)
        return SourceResult(
            company=source.company,
            url=source.url,
            opened=opened,
            checked_at=checked_at,
            content_hash=content_hash,
            evidence=evidence,
            error=None,
        )

    def _normalize_text(self, html: str) -> str:
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _detect_opening(self, text: str) -> tuple[bool, str]:
        lower_text = text.lower()
        year_hits = [pattern for pattern in YEAR_PATTERNS if pattern.lower() in lower_text]
        general_hits = [
            pattern for pattern in GENERAL_PATTERNS if pattern.lower() in lower_text
        ]
        if not year_hits:
            if general_hits:
                return False, f"仅检测到泛校招关键词: {', '.join(general_hits[:4])}"
            return False, "未检测到 27 届相关关键词"

        evidence = self._build_evidence(text, year_hits[0])
        if general_hits:
            evidence = f"{evidence} | 伴随关键词: {', '.join(general_hits[:3])}"
        return True, evidence

    def _build_evidence(self, text: str, keyword: str) -> str:
        index = text.lower().find(keyword.lower())
        if index < 0:
            return f"命中关键词: {keyword}"
        start = max(index - 40, 0)
        end = min(index + len(keyword) + 60, len(text))
        snippet = text[start:end].strip()
        return f"命中关键词: {keyword} | 上下文: {snippet}"
