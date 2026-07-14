from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from .company_registry import aliases_for_company
from .recruitment_types import RecruitmentSpec, recruitment_matches, wondercv_batch_params
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

    def __init__(self, timeout: float = 20.0, cache_path: Path | None = None) -> None:
        self.timeout = timeout
        self.cache_path = cache_path
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            )
        }
        self._cache = self._load_cache()

    async def fetch_latest_items(self, limit: int = 20) -> list[AggregatorItem]:
        return await self.search_company(keyword=None, limit=limit)

    async def search_company(
        self,
        keyword: str | None,
        limit: int = 20,
        recruitment_spec: RecruitmentSpec | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[AggregatorItem]:
        spec = recruitment_spec or RecruitmentSpec()
        batch = wondercv_batch_params(spec)
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            items: list[AggregatorItem] = []
            page = 1
            page_size = min(max(limit, 20), 100)
            while len(items) < limit:
                page_items = await self._fetch_page(
                    client,
                    page=page,
                    page_size=page_size,
                    keyword=keyword,
                    batch=batch,
                    start_at=start_at,
                    end_at=end_at,
                )
                if not page_items:
                    break
                items.extend(page_items)
                if len(page_items) < page_size:
                    break
                page += 1
        return items[:limit]

    async def find_company(
        self,
        company: str,
        recruitment_spec: RecruitmentSpec | None = None,
        strict_batch: bool = False,
    ) -> AggregatorItem | None:
        spec = recruitment_spec or RecruitmentSpec()
        use_authoritative_filter = bool(
            spec.program == "internship"
            or spec.season is not None
            or spec.batch is not None
        )
        items = await self.search_company(
            company,
            limit=30,
            recruitment_spec=spec if use_authoritative_filter else None,
        )
        aliases = [normalize_text(alias) for alias in aliases_for_company(company)]
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

    async def _fetch_page(
        self,
        client: httpx.AsyncClient,
        page: int,
        page_size: int,
        keyword: str | None = None,
        batch: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[AggregatorItem]:
        params = {"page": page, "page_size": page_size}
        if keyword:
            params["keyword"] = keyword
        if batch:
            params["batch"] = batch
        if start_at:
            params["start_at"] = start_at
        if end_at:
            params["end_at"] = end_at

        cache_key = self._cache_key(params)
        cached_items = self._cache.get("requests", {}).get(cache_key)
        if cached_items:
            results: list[AggregatorItem] = []
            for item in cached_items:
                parsed = self._from_cache_item(item)
                if parsed is not None:
                    results.append(parsed)
            return results

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
        self._save_cache_items(cache_key, results)
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

    def _from_cache_item(self, item: dict) -> AggregatorItem | None:
        company = item.get("company") or ""
        summary = item.get("summary") or ""
        if not company or not summary:
            return None
        return AggregatorItem(
            source=item.get("source") or "WonderCV",
            company=company,
            title=item.get("title") or "",
            summary=summary,
            collected_date=item.get("collected_date") or "",
            url=item.get("url") or "",
            tags=tuple(item.get("tags") or []),
        )

    def _cache_key(self, params: dict) -> str:
        return json.dumps(params, sort_keys=True, ensure_ascii=False)

    def _load_cache(self) -> dict:
        if not self.cache_path:
            return {"requests": {}}
        if not self.cache_path.exists():
            return {"requests": {}}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {"requests": {}}

    def _save_cache_items(self, cache_key: str, items: list[AggregatorItem]) -> None:
        if not self.cache_path:
            return
        requests = self._cache.setdefault("requests", {})
        deduped = self._dedupe_cache_items(items)
        requests[cache_key] = [
            {
                "source": item.source,
                "company": item.company,
                "title": item.title,
                "summary": item.summary,
                "collected_date": item.collected_date,
                "url": item.url,
                "tags": list(item.tags),
            }
            for item in deduped
        ]
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._cache, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _dedupe_cache_items(self, items: list[AggregatorItem]) -> list[AggregatorItem]:
        seen: set[tuple[str, str, str]] = set()
        result: list[AggregatorItem] = []
        for item in items:
            key = (item.company, item.url, item.collected_date)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
