from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.provider.entities import ProviderType
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.star_tools import StarTools

from .company_registry import canonical_companies
from .resolver import resolve_companies_in_text, resolve_company
from .sources import OfficialCampusSourceAdapter
from .store import CampusWatchStore


@star.register(
    "astrbot_plugin_campus_watch",
    "22353",
    "监控 27 届校园招聘开启状态的官方源插件",
    "0.1.0",
)
class CampusWatchPlugin(star.Star):
    def __init__(self, context: star.Context) -> None:
        super().__init__(context)
        self.adapter = OfficialCampusSourceAdapter()
        self.store = CampusWatchStore(self._data_dir() / "campus_watch.db")

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self) -> None:
        self.store.seed_defaults()

    @filter.command("campus_refresh")
    async def campus_refresh(
        self,
        event: AstrMessageEvent,
        company: GreedyStr | None = None,
    ):
        """刷新校招源并输出新增开启结果。"""
        sources = (
            [self.store.resolve_source(str(company))[1]]
            if company and str(company).strip()
            else self.store.list_sources()
        )
        sources = [source for source in sources if source is not None]
        if not sources:
            yield event.plain_result("没有匹配到要刷新的公司。")
            return

        results = await asyncio.gather(
            *(self.adapter.fetch(source) for source in sources),
            return_exceptions=False,
        )
        outcomes = [self.store.record_refresh(result) for result in results]

        new_openings = [item for item in outcomes if item.is_new_opening]
        opened = [item for item in outcomes if item.opened]
        failed = [item for item in outcomes if item.error]

        lines = [f"本次检查 {len(outcomes)} 家公司。"]
        if new_openings:
            lines.append("今天检测到新开启：")
            lines.extend(
                f"- {item.company}: {item.evidence[:120]}" for item in new_openings
            )
        else:
            lines.append("今天没有检测到新的 27 届开启公司。")

        if opened:
            lines.append("当前命中 27 届关键词：")
            lines.extend(f"- {item.company}" for item in opened[:12])

        if failed:
            lines.append("抓取失败：")
            lines.extend(f"- {item.company}: {item.error}" for item in failed[:8])

        yield event.plain_result("\n".join(lines))

    @filter.command("campus_today")
    async def campus_today(self, event: AstrMessageEvent):
        """查看今天新开启的公司。"""
        rows = self.store.list_today_openings()
        if not rows:
            yield event.plain_result("今天还没有记录到新的 27 届校招开启公司。先执行 /campus_refresh。")
            return

        lines = ["今天新开启的公司："]
        for row in rows:
            lines.append(f"- {row['company']} ({row['checked_at']}): {row['evidence'][:120]}")
        yield event.plain_result("\n".join(lines))

    @filter.command("今天校招")
    async def campus_today_alias(self, event: AstrMessageEvent):
        """自然语言别名命令：今天哪些开启了校招。"""
        yield event.plain_result(self._format_today_openings())

    @filter.command("campus_watch_add")
    async def campus_watch_add(self, event: AstrMessageEvent, company: GreedyStr):
        """添加关注公司。"""
        try:
            saved = self.store.add_watch(str(company))
        except ValueError as exc:
            yield event.plain_result(f"{exc}。先用 /campus_source_list 看支持列表。")
            return
        yield event.plain_result(f"已关注：{saved}")

    @filter.command("campus_watch_remove")
    async def campus_watch_remove(self, event: AstrMessageEvent, company: GreedyStr):
        """取消关注公司。"""
        try:
            removed = self.store.remove_watch(str(company))
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        yield event.plain_result(f"已取消关注：{removed}")

    @filter.command("campus_watch_list")
    async def campus_watch_list(self, event: AstrMessageEvent):
        """查看关注列表及最近状态。"""
        watch_list = self.store.list_watch()
        if not watch_list:
            yield event.plain_result(
                "关注列表为空。先用 /campus_watch_add 腾讯 这类命令添加。"
            )
            return

        rows = self.store.list_current_status(watch_only=True)
        lines = ["当前关注公司："]
        for row in rows:
            status = "已命中" if row["last_opened"] == 1 else "未命中"
            checked_at = row["last_checked_at"] or "未检查"
            lines.append(f"- {row['company']}: {status} / 最近检查 {checked_at}")
        yield event.plain_result("\n".join(lines))

    @filter.command("campus_source_list")
    async def campus_source_list(self, event: AstrMessageEvent):
        """列出内置监控公司。"""
        rows = self.store.list_current_status(watch_only=False)
        lines = ["内置官方源："]
        for row in rows:
            lines.append(f"- {row['company']}: {row['url']}")
        yield event.plain_result("\n".join(lines))

    @filter.command("campus_status")
    async def campus_status(self, event: AstrMessageEvent):
        """查看当前状态摘要。"""
        rows = self.store.list_current_status(watch_only=False)
        opened = [row["company"] for row in rows if row["last_opened"] == 1]
        unchecked = [row["company"] for row in rows if not row["last_checked_at"]]
        lines = [
            f"总源数: {len(rows)}",
            f"当前命中 27 届关键词: {len(opened)}",
            f"尚未检查: {len(unchecked)}",
        ]
        if opened:
            lines.append("当前命中公司: " + "、".join(opened[:15]))
        yield event.plain_result("\n".join(lines))

    @filter.command("当前校招")
    async def campus_current_alias(self, event: AstrMessageEvent):
        """自然语言别名命令：目前哪些公司开了校招。"""
        yield event.plain_result(self._format_current_openings(limit=10))

    @filter.command("校招")
    async def campus_ask(self, event: AstrMessageEvent, query: GreedyStr):
        """自然语言查询校招状态。"""
        answer = await self._answer_query(str(query), event)
        yield event.plain_result(answer)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def campus_natural_language(self, event: AstrMessageEvent):
        """Handle campus-recruitment questions without a command when possible."""
        query = event.message_str.strip()
        if not self._should_handle_nl(query):
            return
        answer = await self._answer_query(query, event)
        yield event.plain_result(answer).stop_event()

    async def terminate(self) -> None:
        """Plugin shutdown hook."""
        return None

    def _data_dir(self) -> Path:
        return StarTools.get_data_dir("astrbot_plugin_campus_watch")

    def _should_handle_nl(self, query: str) -> bool:
        if not query or query.startswith("/"):
            return False
        keywords = ("校招", "校园招聘", "秋招", "春招", "实习")
        if any(keyword in query for keyword in keywords):
            return True

        companies = resolve_companies_in_text(query)
        company_question_tokens = ("开没开", "开了吗", "开启", "招吗", "在招", "开始了吗")
        return bool(companies) and any(token in query for token in company_question_tokens)

    async def _answer_query(self, query: str, event: AstrMessageEvent) -> str:
        intent_data = await self._classify_query(query, event)
        intent = intent_data.get("intent", "ignore")
        companies = intent_data.get("companies") or []
        limit = int(intent_data.get("limit") or 10)

        if intent == "today_openings":
            return self._format_today_openings()
        if intent == "current_openings":
            return self._format_current_openings(limit=limit)
        if intent == "company_status":
            return self._format_company_status(companies)
        return (
            "我目前支持三类校招问题：今天哪些新开了、目前哪些公司开了、某家公司开没开。"
            "也可以直接用 `/校招 百度开没开校招` 这种方式问。"
        )

    async def _classify_query(self, query: str, event: AstrMessageEvent) -> dict:
        local_companies = resolve_companies_in_text(query)
        local_intent = self._classify_query_local(query, bool(local_companies))
        llm_data = await self._classify_query_with_llm(query, event)
        if llm_data:
            if not llm_data.get("companies") and local_companies:
                llm_data["companies"] = local_companies
            if llm_data.get("intent") == "ignore" and local_intent != "ignore":
                llm_data["intent"] = local_intent
            return llm_data
        return {
            "intent": local_intent,
            "companies": local_companies,
            "limit": 10,
        }

    def _classify_query_local(self, query: str, has_company: bool) -> str:
        if "今天" in query and any(token in query for token in ("哪些", "哪几家", "什么公司")):
            return "today_openings"
        if has_company and any(token in query for token in ("开没开", "开了吗", "开启", "有无", "开始", "在招", "招吗")):
            return "company_status"
        if any(token in query for token in ("目前", "现在", "当前", "哪些")):
            return "current_openings"
        if has_company:
            return "company_status"
        return "ignore"

    async def _classify_query_with_llm(self, query: str, event: AstrMessageEvent) -> dict | None:
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
            "你是校园招聘问句分类器。"
            "请把用户问题分类为 today_openings、current_openings、company_status、ignore 四种之一。"
            "company_status 仅在用户明显在问某些具体公司是否开启校招时使用。"
            "只返回 JSON，不要输出解释。格式为："
            '{"intent":"current_openings","companies":["百度"],"limit":10}'
            f"\n已知标准公司列表：{', '.join(canonical_companies())}"
            f"\n用户问题：{query}"
        )
        try:
            response = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
                system_prompt=(
                    "你只做信息抽取与分类。"
                    "companies 必须尽量映射到给定标准公司名。"
                    "如果用户问的是今天新开启，用 today_openings。"
                    "如果用户问的是目前哪些公司开了，用 current_openings。"
                    "如果用户问的是某些具体公司，用 company_status。"
                    "只输出 JSON。"
                ),
            )
            return self._parse_llm_json(response.completion_text)
        except Exception:
            return None

    def _parse_llm_json(self, text: str) -> dict | None:
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
        if not isinstance(data, dict):
            return None
        return data

    def _format_today_openings(self) -> str:
        rows = self.store.list_today_openings()
        if not rows:
            return "今天还没有记录到新的 27 届校招开启公司。先执行 /campus_refresh。"
        lines = ["今天新开启的公司："]
        for row in rows[:10]:
            lines.append(f"- {row['company']} ({row['checked_at']})")
        return "\n".join(lines)

    def _format_current_openings(self, limit: int = 10) -> str:
        rows = self.store.list_current_status()
        opened = [row for row in rows if row["last_opened"] == 1]
        if not opened:
            return "当前还没有检测到已开启的公司，或者还没刷新。先执行 /campus_refresh。"
        lines = ["目前检测到已开启的公司："]
        for row in opened[: max(1, min(limit, 10))]:
            checked_at = row["last_checked_at"] or "未知时间"
            lines.append(f"- {row['company']} / 最近检查 {checked_at}")
        return "\n".join(lines)

    def _format_company_status(self, companies: list[str]) -> str:
        if not companies:
            return "我没识别出你问的是哪家公司。可以直接问：`/校招 百度开没开校招`。"
        rows = {row["company"]: row for row in self.store.list_current_status()}
        lines = []
        for company in companies[:10]:
            resolution = resolve_company(company)
            canonical = resolution.canonical or company
            row = rows.get(canonical)
            if not row:
                lines.append(f"- {canonical}: 暂无监控源")
                continue
            if not row["last_checked_at"]:
                lines.append(f"- {canonical}: 还没检查，先执行 /campus_refresh {canonical}")
                continue
            status = "已开启" if row["last_opened"] == 1 else "暂未检测到"
            detail = row["evidence"] or row["last_error"] or "无附加信息"
            lines.append(f"- {canonical}: {status} / {detail[:120]}")
        return "\n".join(lines)
