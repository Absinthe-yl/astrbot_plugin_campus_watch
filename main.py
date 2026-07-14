from __future__ import annotations

import asyncio
from pathlib import Path

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.star.filter.command import GreedyStr
from astrbot.core.star.star_tools import StarTools

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
            [self.store.get_source(str(company))]
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

    async def terminate(self) -> None:
        """Plugin shutdown hook."""
        return None

    def _data_dir(self) -> Path:
        return StarTools.get_data_dir("astrbot_plugin_campus_watch")
