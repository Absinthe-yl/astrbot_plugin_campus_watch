from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from .company_registry import aliases_for_company
from .recruitment_types import RecruitmentSpec, recruitment_matches
from .resolver import normalize_text


@dataclass(frozen=True)
class AggregatorItem:
    source: str
    company: str
    title: str
    summary: str
    collected_date: str
    url: str
    tags: tuple[str, ...]


class WonderCVAggregator:
    homepage = "https://www.wondercv.com/xiaozhao/"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            )
        }

    async def fetch_latest_items(self, limit: int = 20) -> list[AggregatorItem]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            response = await client.get(self.homepage)
            response.raise_for_status()
        return self._parse_items(response.text)[:limit]

    async def find_company(
        self,
        company: str,
        recruitment_spec: RecruitmentSpec | None = None,
        strict_batch: bool = False,
    ) -> AggregatorItem | None:
        items = await self.fetch_latest_items(limit=40)
        aliases = [normalize_text(alias) for alias in aliases_for_company(company)]
        spec = recruitment_spec or RecruitmentSpec()
        for item in items:
            haystack = normalize_text(
                f"{item.company} {item.title} {item.summary} {' '.join(item.tags)}"
            )
            if any(alias and alias in haystack for alias in aliases) and recruitment_matches(
                f"{item.title} {item.summary} {' '.join(item.tags)}",
                spec,
                strict_batch=strict_batch,
            ):
                return item
        return None

    def _parse_items(self, html: str) -> list[AggregatorItem]:
        blocks = re.findall(
            r'(<a href="/xiaozhao/[\s\S]*?class="campus-job-card job-card"[\s\S]*?</a>)',
            html,
            flags=re.IGNORECASE,
        )
        items: list[AggregatorItem] = []
        for block in blocks:
            url_match = re.search(r'href="(/xiaozhao/[^"]+/)"', block)
            company_match = re.search(r'<div class="company"[^>]*>([\s\S]*?)</div>', block)
            summary_match = re.search(r'<div class="summary"[^>]*><p[^>]*>([\s\S]*?)</p>', block)
            date_match = re.search(r'收录\s*([0-9]{4}\.[0-9]{2}\.[0-9]{2})', block)
            tag_matches = re.findall(r'<span class="info-tag"[^>]*>([\s\S]*?)</span>', block)

            url = f"https://www.wondercv.com{url_match.group(1)}" if url_match else ""
            company = self._clean(company_match.group(1)) if company_match else ""
            summary = self._clean(summary_match.group(1)) if summary_match else ""
            collected_date = date_match.group(1) if date_match else ""
            tags = tuple(self._clean(tag) for tag in tag_matches if self._clean(tag))
            title = summary[:40]

            if not url or not company or not summary:
                continue

            items.append(
                AggregatorItem(
                    source="WonderCV",
                    company=company,
                    title=title,
                    summary=summary,
                    collected_date=collected_date,
                    url=url,
                    tags=tags,
                )
            )
        return items

    def _clean(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value)
        text = (
            text.replace("&nbsp;", " ")
            .replace("&#x27;", "'")
            .replace("&amp;", "&")
            .replace("&quot;", '"')
        )
        text = re.sub(r"\s+", " ", text)
        return text.strip()
