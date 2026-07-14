from __future__ import annotations

from dataclasses import dataclass

from .resolver import normalize_text


@dataclass(frozen=True)
class RecruitmentSpec:
    program: str | None = None
    season: str | None = None
    batch: str | None = None

    def label(self) -> str:
        if self.program == "internship" and self.season == "summer":
            return "暑期实习"
        if self.program == "internship":
            return "实习"

        season_label = {
            "autumn": "秋招",
            "spring": "春招",
        }.get(self.season, "校招")
        batch_label = {
            "early": "提前批",
            "formal": "正式批",
        }.get(self.batch, "")
        return f"{season_label}{batch_label}"


def extract_recruitment_spec(text: str) -> RecruitmentSpec:
    normalized = normalize_text(text)

    if any(token in normalized for token in ("暑期实习", "summerintern", "暑期岗位")):
        return RecruitmentSpec(program="internship", season="summer")
    if "实习" in normalized and "校招" not in normalized and "春招" not in normalized and "秋招" not in normalized:
        return RecruitmentSpec(program="internship")

    season = None
    if "秋招" in normalized:
        season = "autumn"
    elif "春招" in normalized:
        season = "spring"

    batch = None
    if any(token in normalized for token in ("提前批", "早鸟", "prebatch")):
        batch = "early"
    elif any(token in normalized for token in ("正式批", "正式启动", "正式开放")):
        batch = "formal"

    if "校招" in normalized or "校园招聘" in normalized or season or batch:
        return RecruitmentSpec(program="campus", season=season, batch=batch)
    return RecruitmentSpec()


def recruitment_matches(
    text: str,
    spec: RecruitmentSpec,
    strict_batch: bool = False,
) -> bool:
    normalized = normalize_text(text)

    if spec.program == "internship":
        if "实习" not in normalized:
            return False
        if spec.season == "summer":
            return any(token in normalized for token in ("暑期实习", "summerintern", "暑期岗位"))
        return True

    if spec.program == "campus":
        season_match = True
        if spec.season == "autumn":
            season_match = "秋招" in normalized or "提前批" in normalized
        elif spec.season == "spring":
            season_match = "春招" in normalized
        elif not any(token in normalized for token in ("校招", "校园招聘", "秋招", "春招", "提前批")):
            season_match = False

        if not season_match:
            return False

        if spec.batch == "early":
            return any(token in normalized for token in ("提前批", "早鸟"))
        if spec.batch == "formal":
            formal_hit = any(token in normalized for token in ("正式批", "正式启动", "正式开放", "网申中"))
            if strict_batch:
                return formal_hit
            return formal_hit or season_match
        return True

    return True


def describe_item_type(text: str) -> str:
    normalized = normalize_text(text)
    if any(token in normalized for token in ("暑期实习", "summerintern", "暑期岗位")):
        return "暑期实习"
    if "实习" in normalized and "秋招" not in normalized and "春招" not in normalized:
        return "实习"
    if "春招" in normalized and any(token in normalized for token in ("提前批", "早鸟")):
        return "春招提前批"
    if "春招" in normalized and any(token in normalized for token in ("正式批", "正式启动", "正式开放", "网申中")):
        return "春招正式批"
    if "春招" in normalized:
        return "春招"
    if "秋招" in normalized and any(token in normalized for token in ("提前批", "早鸟")):
        return "秋招提前批"
    if "秋招" in normalized and any(token in normalized for token in ("正式批", "正式启动", "正式开放", "网申中")):
        return "秋招正式批"
    if "秋招" in normalized:
        return "秋招"
    if "校招" in normalized and any(token in normalized for token in ("提前批", "早鸟")):
        return "校招提前批"
    if "校招" in normalized:
        return "校招"
    return "未知类型"
