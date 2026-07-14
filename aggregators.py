from __future__ import annotations

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
    api_url = "https://api.wondercv.com/cv/v3/campus_recruits_v2"

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
            items: list[AggregatorItem] = []
            page = 1
            page_size = min(max(limit, 20), 100)
            while len(items) < limit:
                batch = await self._fetch_page(client, page=page, page_size=page_size)
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < page_size:
                    break
                page += 1
        return items[:limit]

    async def find_company(
        self,
        company: str,
        recruitment_spec: RecruitmentSpec | None = None,
        strict_batch: bool = False,
    ) -> AggregatorItem | None:
        items = await self.search_company(company, limit=30)
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

    async def search_company(self, keyword: str, limit: int = 20) -> list[AggregatorItem]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            items: list[AggregatorItem] = []
            page = 1
            page_size = min(max(limit, 12), 100)
            while len(items) < limit:
                batch = await self._fetch_page(
                    client,
                    page=page,
                    page_size=page_size,
                    keyword=keyword,
                )
                if not batch:
                    break
                items.extend(batch)
                if len(batch) < page_size:
                    break
                page += 1
        return items[:limit]

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page: int,
        page_size: int,
        keyword: str | None = None,
    ) -> list[AggregatorItem]:
        params = {"page": page, "page_size": page_size}
        if keyword:
            params["keyword"] = keyword
        response = await client.get(self.api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        raw_items = data.get("items") or []
        results: list[AggregatorItem] = []
        for item in raw_items:
            parsed = self._from_api_item(item)
            if parsed is not None:
                results.append(parsed)
        return results

    def _from_api_item(self, item: dict) -> AggregatorItem | None:
        token = item.get("token") or ""
        company = item.get("company_name") or ""
        title = item.get("title") or ""
        summary = item.get("summary") or ""
        collected_date = item.get("updated_date") or ""
        tags = tuple((item.get("info_tags") or [])[:])
        if not token or not company or not summary:
            return None
        return AggregatorItem(
            source="WonderCV",
            company=company,
            title=title,
            summary=summary,
            collected_date=collected_date,
            url=f"https://www.wondercv.com/xiaozhao/{token}/",
            tags=tags,
        )
