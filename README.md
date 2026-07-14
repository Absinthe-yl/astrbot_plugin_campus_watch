# astrbot_plugin_campus_watch

AstrBot plugin for tracking official campus recruitment pages and detecting new 2027-cohort openings.

## Features

- Monitor built-in official campus recruitment sources.
- Refresh source pages on demand.
- Record companies that appear to have newly opened 2027-cohort recruitment today.
- Maintain a personal watch list in AstrBot.
- Persist source status in local SQLite.
- Support company alias resolution such as `腾讯科技 -> 腾讯`, `抖音 -> 字节跳动`.
- Support natural-language campus recruitment queries through AstrBot LLM.
- Support auto-discovery of official campus sources for companies not yet stored locally.
- Support WonderCV public campus feed as the primary aggregated source.

## Commands

- `/campus_source_list`
- `/campus_refresh`
- `/campus_refresh 腾讯`
- `/campus_today`
- `/campus_watch_add 腾讯`
- `/campus_watch_list`
- `/campus_watch_remove 腾讯`
- `/campus_status`
- `/campus_discover 快手`
- `/今天校招`
- `/当前校招`
- `/校招 今天哪些开启了校招`
- `/校招 目前哪些公司开了校招`
- `/校招 百度开没开校招`

The plugin can also answer direct natural-language questions in chat, for example:

- `今天哪些开启了校招`
- `目前哪些公司开了校招`
- `腾讯科技开没开校招`
- `抖音开了吗`

When a company is not yet in the local source database, the plugin will:

1. Search candidate pages from public search engines.
2. Validate whether the page looks like an official recruitment entry.
3. Save the verified source for reuse in later queries.

The plugin reads the public WonderCV campus feed as the primary aggregated source to:

1. Answer "currently which companies have openings" with aggregated results.
2. Provide auxiliary evidence for "has company X opened campus recruitment".
3. Show same-day aggregated feed items when local refresh data is empty.

## Install

Place this plugin directory under:

```text
data/plugins/astrbot_plugin_campus_watch
```

Then reload plugins from AstrBot WebUI.

## Runtime Notes

- This first version uses official campus pages as the primary data source.
- WonderCV is the primary aggregated source for natural-language campus queries.
- Official company pages are still used for per-company verification and fallback checks.
- It detects likely openings through keyword monitoring, not full job-detail crawling.
- Natural-language intent is classified with AstrBot's configured LLM when available, and falls back to local rules when unavailable.
- Auto-discovery is intentionally conservative. If a candidate page does not look like an official recruitment entry, it will not be saved.
- SQLite data is stored under AstrBot `data/plugin_data/astrbot_plugin_campus_watch`.

## Server Deployment

This plugin is suitable for self-hosted AstrBot deployments on a server. After copying the plugin directory to the server, reload the plugin from AstrBot WebUI.
