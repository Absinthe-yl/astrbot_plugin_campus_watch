from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from urllib.parse import parse_qs, urlparse

import httpx

from .company_registry import aliases_for_company
from .resolver import normalize_text


SEARCH_ENDPOINTS = (
    "https://www.bing.com/search",
    "https://cn.bing.com/search",
)
BLOCKED_HOST_KEYWORDS = (
    "baidu.com",
    "bendibao.com",
    "zhihu.com",
    "weixin.qq.com",
    "mp.weixin.qq.com",
    "zhipin.com",
    "51job.com",
    "lagou.com",
    "liepin.com",
    "kanzhun.com",
    "maimai.cn",
    "linkedin.com",
    "xiaohongshu.com",
    "bilibili.com",
)
CAMPUS_KEYWORDS = ("校园招聘", "校招", "应届生", "campus", "graduate", "graduates")
OFFICIAL_URL_TOKENS = ("campus", "career", "careers", "jobs", "job", "talent", "join", "recruit")


@dataclass(frozen=True)
class DiscoveredSource:
    company: str
    url: str
    title: str
    discovery_query: str
    verified_at: str
    evidence: str


class CampusSourceDiscovery:
    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            )
        }

    async def discover(self, company: str) -> DiscoveredSource | None:
        queries = self._build_queries(company)
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers=self.headers,
        ) as client:
            for query in queries:
                candidates = await self._search_candidates(client, query)
                for candidate in candidates:
                    verified = await self._validate_candidate(client, company, candidate, query)
                    if verified:
                        return verified
        return None

    def _build_queries(self, company: str) -> list[str]:
        return [
            f"{company} 校园招聘 官网",
            f"{company} 校招 官网",
            f"{company} campus recruitment official",
        ]

    async def _search_candidates(self, client: httpx.AsyncClient, query: str) -> list[tuple[str, str]]:
        results: list[tuple[str, str]] = []
        for endpoint in SEARCH_ENDPOINTS:
            response = await client.get(endpoint, params={"q": query})
            response.raise_for_status()
            html = response.text
            matches = re.findall(
                r'target="_blank"\s+href="([^"]+)"',
                html,
                flags=re.IGNORECASE,
            )
            for href in matches:
                url = self._extract_target_url(unescape(href))
                if not url or self._is_blocked_host(url):
                    continue
                results.append((url, url))
                if len(results) >= 8:
                    return self._dedupe_results(results)
        return self._dedupe_results(results)

    async def _validate_candidate(
        self,
        client: httpx.AsyncClient,
        company: str,
        candidate: tuple[str, str],
        query: str,
    ) -> DiscoveredSource | None:
        url, title = candidate
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception:
            return None

        final_url = str(response.url)
        if self._is_blocked_host(final_url):
            return None

        text = self._strip_html(response.text)
        score, evidence = self._score_page(company, title, text, final_url)
        if score < 4:
            return None

        return DiscoveredSource(
            company=company,
            url=final_url,
            title=title or final_url,
            discovery_query=query,
            verified_at=datetime.now().isoformat(timespec="seconds"),
            evidence=evidence,
        )

    def _score_page(self, company: str, title: str, text: str, url: str) -> tuple[int, str]:
        normalized_text = normalize_text(f"{title} {text[:4000]}")
        normalized_url = normalize_text(url)
        score = 0
        reasons: list[str] = []

        if any(keyword in normalized_text for keyword in map(normalize_text, CAMPUS_KEYWORDS)):
            score += 2
            reasons.append("命中校招关键词")

        company_aliases = aliases_for_company(company)
        alias_hits = [
            alias for alias in company_aliases if normalize_text(alias) and normalize_text(alias) in normalized_text
        ]
        if alias_hits:
            score += 2
            reasons.append(f"命中公司名: {alias_hits[0]}")
        else:
            return 0, "页面内容未命中公司名"

        has_official_url_token = any(token in normalized_url for token in OFFICIAL_URL_TOKENS)
        if has_official_url_token:
            score += 1
            reasons.append("URL 形态像招聘页")
        else:
            return 0, "URL 形态不像官方招聘入口"

        if any(token in normalized_url for token in ("official", "join", "career", "careers", "talent")):
            score += 1
            reasons.append("URL 形态像官方入口")

        evidence = "；".join(reasons) if reasons else "未达到官方校招页置信度"
        return score, evidence

    def _extract_target_url(self, href: str) -> str | None:
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            params = parse_qs(parsed.query)
            if "uddg" in params and params["uddg"]:
                return params["uddg"][0]
            return href
        if href.startswith("http://") or href.startswith("https://"):
            return href
        return None

    def _is_blocked_host(self, url: str) -> bool:
        host = (urlparse(url).netloc or "").lower()
        return any(keyword in host for keyword in BLOCKED_HOST_KEYWORDS)

    def _dedupe_results(self, results: list[tuple[str, str]]) -> list[tuple[str, str]]:
        seen: set[str] = set()
        deduped: list[tuple[str, str]] = []
        for url, title in results:
            if url in seen:
                continue
            seen.add(url)
            deduped.append((url, title))
        return deduped

    def _strip_html(self, html: str) -> str:
        text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
