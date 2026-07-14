from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Reply
from astrbot.api.platform import MessageType
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.star_tools import StarTools

from .aggregators import AggregatorItem, WonderCVAggregator
from .company_registry import canonical_companies
from .recruitment_types import RecruitmentSpec, describe_item_type, extract_recruitment_spec
from .resolver import resolve_companies_in_text, resolve_company


@star.register(
    "astrbot_plugin_campus_watch",
    "22353",
    "基于 WonderCV API 的校园招聘自然语言查询插件",
    "0.6.4",
)
class CampusWatchPlugin(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.wondercv = WonderCVAggregator()
        self._session_state: dict[str, dict] = {}

    @filter.command("校招")
    async def campus_ask(self, event: AstrMessageEvent, query: GreedyStr):
        answer = await self._answer_query(str(query), event)
        yield event.plain_result(answer)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def campus_natural_language(self, event: AstrMessageEvent):
        query = event.message_str.strip()
        if not self._should_handle_event(event, query):
            return
        answer = await self._answer_query(query, event)
        yield event.plain_result(answer).stop_event()

    async def terminate(self) -> None:
        return None

    def _data_dir(self) -> Path:
        return StarTools.get_data_dir("astrbot_plugin_campus_watch")

    def _should_handle_nl(self, query: str) -> bool:
        if not query or query.startswith("/"):
            return False
        keywords = ("校招", "校园招聘", "秋招", "春招", "实习", "提前批", "正式批", "补录", "寒假实习", "日常实习")
        if any(keyword in query for keyword in keywords):
            return True
        companies = resolve_companies_in_text(query)
        return bool(companies) and self._has_company_question_token(query)

    def _should_handle_event(self, event: AstrMessageEvent, query: str) -> bool:
        if not self._should_handle_nl(query):
            return False
        if event.get_message_type() == MessageType.FRIEND_MESSAGE:
            return True
        if event.is_at_or_wake_command:
            return True
        return self._is_reply_to_self(event)

    def _is_reply_to_self(self, event: AstrMessageEvent) -> bool:
        self_id = str(event.get_self_id() or "").strip()
        if not self_id:
            return False
        for comp in event.get_messages():
            if isinstance(comp, Reply) and str(getattr(comp, "sender_id", "") or "").strip() == self_id:
                return True
        return False

    async def _answer_query(self, query: str, event: AstrMessageEvent) -> str:
        parsed = await self._parse_query(query, event)
        intent = parsed.get("intent", "ignore")
        companies = parsed.get("companies") or []
        limit = max(1, min(int(parsed.get("limit") or 10), 20))
        days = max(1, min(int(parsed.get("days") or 7), 30))
        recruitment_spec = self._spec_from_query_and_json(query, parsed)

        if intent == "company_status":
            answer = await self._answer_company_status(companies, recruitment_spec)
            self._save_session_state(
                event,
                intent="company_status",
                companies=companies,
                recruitment_spec=recruitment_spec,
                days=days,
            )
            return answer
        if intent in {"current_openings", "today_openings"}:
            answer = await self._answer_company_list(recruitment_spec, limit=limit, days=days)
            self._save_session_state(
                event,
                intent=intent,
                companies=[],
                recruitment_spec=recruitment_spec,
                days=days,
            )
            return answer
        return (
            "你可以直接问我这些："
            "字节开校招了吗、腾讯秋招提前批开没开、百度春招正式批开没开、"
            "美团秋招补录开没开、阿里寒假实习开没开、日常实习哪些公司开了。"
        )

    async def _parse_query(self, query: str, event: AstrMessageEvent) -> dict:
        local = self._parse_query_local(query)
        llm_data = await self._parse_query_with_llm(query, event)
        if not llm_data:
            return self._merge_with_session_state(local, query, event)
        if not llm_data.get("companies") and local.get("companies"):
            llm_data["companies"] = local["companies"]
        if llm_data.get("intent") == "ignore" and local.get("intent") != "ignore":
            llm_data["intent"] = local["intent"]
        if not llm_data.get("days"):
            llm_data["days"] = local.get("days", 7)
        if not llm_data.get("limit"):
            llm_data["limit"] = local.get("limit", 10)
        return self._merge_with_session_state(llm_data, query, event)

    def _parse_query_local(self, query: str) -> dict:
        companies = resolve_companies_in_text(query)
        if companies and self._has_company_question_token(query):
            return {"intent": "company_status", "companies": companies, "limit": 5, "days": 30}
        if "今天" in query and any(token in query for token in ("哪些", "哪几家", "什么公司")):
            return {"intent": "today_openings", "companies": [], "limit": 10, "days": 1}
        if any(token in query for token in ("哪些", "哪几家", "目前", "现在", "当前", "近7天", "最近")):
            return {"intent": "current_openings", "companies": [], "limit": 10, "days": 7}
        if companies:
            return {"intent": "company_status", "companies": companies, "limit": 5, "days": 30}
        return {"intent": "ignore", "companies": [], "limit": 10, "days": 7}

    async def _parse_query_with_llm(self, query: str, event: AstrMessageEvent) -> dict | None:
        provider = self.context.provider_manager.get_using_provider(
            ProviderType.CHAT_COMPLETION,
            getattr(event, "unified_msg_origin", None),
        )
        if not provider:
            return None
        provider_id = provider.provider_config.get("id")
        if not provider_id:
            return None

        prompt = (
            "你是校园招聘查询参数解析器。"
            "把用户问题解析成 JSON。"
            "只输出 JSON，不要解释。"
            '\n格式: {"intent":"company_status","companies":["腾讯"],"program":"campus","season":"autumn","batch":"early","days":7,"limit":10}'
            "\nintent 只能是 company_status current_openings today_openings ignore。"
            "\n如果问题里出现了明确公司名，优先使用 company_status，不要返回 current_openings。"
            "\n像“拼多多呢”“那腾讯呢”这种续问，若上下文在问招聘状态，也按 company_status 处理。"
            "\nprogram 只能是 campus internship null。"
            "\nseason 只能是 autumn spring summer winter null。"
            "\nbatch 只能是 early formal supplement daily null。"
            "\ndays 表示用户想看最近几天，默认 7，今天就是 1。"
            f"\n标准公司名参考：{', '.join(canonical_companies())}"
            f"\n用户问题：{query}"
        )
        try:
            response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt="你只做结构化信息抽取，只输出 JSON。",
            )
            return self._parse_json_block(response.completion_text)
        except Exception:
            return None

    def _parse_json_block(self, text: str) -> dict | None:
        if not text:
            return None
        cleaned = text.strip()
        cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None

    def _spec_from_query_and_json(self, query: str, parsed: dict) -> RecruitmentSpec:
        local = extract_recruitment_spec(query)
        return RecruitmentSpec(
            program=parsed.get("program") or local.program,
            season=parsed.get("season") or local.season,
            batch=parsed.get("batch") or local.batch,
        )

    async def _answer_company_status(
        self,
        companies: list[str],
        recruitment_spec: RecruitmentSpec,
    ) -> str:
        if not companies:
            return "我没识别出你问的是哪家公司。"

        lines: list[str] = []
        for company in companies[:5]:
            resolution = resolve_company(company)
            canonical = resolution.canonical or company.strip()
            item = await self.wondercv.find_company(
                canonical,
                recruitment_spec=recruitment_spec,
                strict_batch=recruitment_spec.batch == "formal",
            )
            if item:
                lines.append(self._format_company_hit(canonical, recruitment_spec, item))
                continue

            if recruitment_spec.batch == "formal":
                loose_item = await self.wondercv.find_company(
                    canonical,
                    recruitment_spec=RecruitmentSpec(
                        program=recruitment_spec.program,
                        season=recruitment_spec.season,
                        batch=None,
                    ),
                    strict_batch=False,
                )
                if loose_item:
                    lines.append(
                        f"{canonical}暂未检测到{recruitment_spec.label()}，"
                        f"但检测到{describe_item_type(self._item_text(loose_item))}。"
                    )
                    continue

            lines.append(f"{canonical}暂未检测到{self._target_label(recruitment_spec)}。")
        return "\n".join(lines)

    async def _answer_company_list(
        self,
        recruitment_spec: RecruitmentSpec,
        limit: int,
        days: int,
    ) -> str:
        start_at = None
        if not self._list_query_should_skip_date_filter(recruitment_spec, days):
            start_at = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        items = await self.wondercv.search_company(
            keyword=None,
            limit=80,
            recruitment_spec=recruitment_spec,
            start_at=start_at,
        )
        items = self._dedupe_company_items(items)
        if not items:
            if start_at:
                return f"近{days}天还没有检测到新的{self._target_label(recruitment_spec)}公司。"
            return f"暂时还没有检测到新的{self._target_label(recruitment_spec)}公司。"

        if start_at:
            lines = [f"近{days}天开了{self._target_label(recruitment_spec)}的公司有这些："]
        else:
            lines = [f"开了{self._target_label(recruitment_spec)}的公司有这些："]
        for item in items[:limit]:
            lines.append(
                f"- {item.company}：{describe_item_type(self._item_text(item))}，收录于 {self._display_date(item.collected_date)}"
            )
        return "\n".join(lines)

    def _format_company_hit(
        self,
        company: str,
        recruitment_spec: RecruitmentSpec,
        item: AggregatorItem,
    ) -> str:
        actual_type = describe_item_type(self._item_text(item))
        target_label = self._target_label(recruitment_spec)
        if recruitment_spec.program == "campus" and recruitment_spec.season is None and recruitment_spec.batch is None:
            return f"{company}开了。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"
        if recruitment_spec.program == "campus" and recruitment_spec.batch == "early" and recruitment_spec.season is None:
            return f"{company}提前批开了。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"
        if recruitment_spec.program == "campus" and recruitment_spec.batch == "supplement" and recruitment_spec.season is None:
            return f"{company}补录开了。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"
        if recruitment_spec.program == "campus" and recruitment_spec.batch == "formal" and recruitment_spec.season is None:
            return f"{company}正式批开了。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"
        if recruitment_spec.program == "internship" and recruitment_spec.season is None:
            return f"{company}开了实习。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"
        return f"{company}{target_label}开了。目前检测到的是{actual_type}，收录于 {self._display_date(item.collected_date)}。"

    def _target_label(self, spec: RecruitmentSpec) -> str:
        label = spec.label()
        return label if label != "校招" else "校招"

    def _item_text(self, item: AggregatorItem) -> str:
        return f"{item.title} {item.summary} {' '.join(item.tags)}"

    def _display_date(self, value: str) -> str:
        if not value:
            return "未知时间"
        return value.replace("-", ".")

    def _dedupe_company_items(self, items: list[AggregatorItem]) -> list[AggregatorItem]:
        chosen: dict[str, AggregatorItem] = {}
        for item in items:
            current = chosen.get(item.company)
            if current is None or (item.collected_date or "") > (current.collected_date or ""):
                chosen[item.company] = item
        return sorted(
            chosen.values(),
            key=lambda item: (item.collected_date or "", item.company),
            reverse=True,
        )

    def _has_company_question_token(self, query: str) -> bool:
        question_tokens = (
            "开没开",
            "开了吗",
            "有没有开",
            "开了没",
            "开始了吗",
            "有吗",
            "有无",
            "在招",
            "招吗",
            "呢",
        )
        return any(token in query for token in question_tokens)

    def _save_session_state(
        self,
        event: AstrMessageEvent,
        intent: str,
        companies: list[str],
        recruitment_spec: RecruitmentSpec,
        days: int,
    ) -> None:
        self._session_state[event.unified_msg_origin] = {
            "intent": intent,
            "companies": companies[:5],
            "program": recruitment_spec.program,
            "season": recruitment_spec.season,
            "batch": recruitment_spec.batch,
            "days": days,
        }

    def _merge_with_session_state(self, parsed: dict, query: str, event: AstrMessageEvent) -> dict:
        state = self._session_state.get(event.unified_msg_origin) or {}
        companies = parsed.get("companies") or []
        if companies and parsed.get("intent") in {"ignore", "company_status", None}:
            if not parsed.get("program") and not parsed.get("season") and not parsed.get("batch"):
                if self._looks_like_follow_up(query) and state.get("intent") == "company_status":
                    parsed["intent"] = "company_status"
                    parsed["program"] = state.get("program")
                    parsed["season"] = state.get("season")
                    parsed["batch"] = state.get("batch")
                    parsed["days"] = parsed.get("days") or state.get("days") or 30
        return parsed

    def _looks_like_follow_up(self, query: str) -> bool:
        query = query.strip()
        return any(token in query for token in ("呢", "那", "有没有", "开了吗", "开没开", "开了没"))

    def _list_query_should_skip_date_filter(self, spec: RecruitmentSpec, days: int) -> bool:
        return spec.program == "internship" and spec.batch == "daily" and days == 7
