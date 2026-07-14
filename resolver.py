from __future__ import annotations

import re
from dataclasses import dataclass

from .company_registry import COMPANY_ALIASES


@dataclass
class CompanyResolution:
    query: str
    canonical: str | None
    matched_alias: str | None
    candidates: list[str]

    @property
    def resolved(self) -> bool:
        return self.canonical is not None and len(self.candidates) <= 1

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1


def normalize_text(value: str) -> str:
    text = re.sub(r"\s+", "", value).lower()
    text = text.replace("（", "(").replace("）", ")")
    return text


def resolve_company(query: str) -> CompanyResolution:
    normalized = normalize_text(query)
    if not normalized:
        return CompanyResolution(query=query, canonical=None, matched_alias=None, candidates=[])

    exact_matches: list[tuple[str, str]] = []
    fuzzy_matches: list[tuple[str, str]] = []

    for canonical, aliases in COMPANY_ALIASES.items():
        all_names = (canonical, *aliases)
        for alias in all_names:
            alias_norm = normalize_text(alias)
            if normalized == alias_norm:
                exact_matches.append((canonical, alias))
                break
            if normalized in alias_norm or alias_norm in normalized:
                fuzzy_matches.append((canonical, alias))
                break

    if exact_matches:
        unique = _dedupe([item[0] for item in exact_matches])
        return CompanyResolution(
            query=query,
            canonical=unique[0] if len(unique) == 1 else None,
            matched_alias=exact_matches[0][1] if len(unique) == 1 else None,
            candidates=unique,
        )

    unique_fuzzy = _dedupe([item[0] for item in fuzzy_matches])
    return CompanyResolution(
        query=query,
        canonical=unique_fuzzy[0] if len(unique_fuzzy) == 1 else None,
        matched_alias=fuzzy_matches[0][1] if len(unique_fuzzy) == 1 and fuzzy_matches else None,
        candidates=unique_fuzzy,
    )


def resolve_companies_in_text(text: str) -> list[str]:
    normalized = normalize_text(text)
    matches: list[str] = []
    for canonical, aliases in COMPANY_ALIASES.items():
        for alias in (canonical, *aliases):
            if normalize_text(alias) in normalized:
                matches.append(canonical)
                break
    return _dedupe(matches)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
