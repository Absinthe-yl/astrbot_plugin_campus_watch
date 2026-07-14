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

## Commands

- `/campus_source_list`
- `/campus_refresh`
- `/campus_refresh 腾讯`
- `/campus_today`
- `/campus_watch_add 腾讯`
- `/campus_watch_list`
- `/campus_watch_remove 腾讯`
- `/campus_status`
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

## Install

Place this plugin directory under:

```text
data/plugins/astrbot_plugin_campus_watch
```

Then reload plugins from AstrBot WebUI.

## Runtime Notes

- This first version uses official campus pages as the primary data source.
- It detects likely openings through keyword monitoring, not full job-detail crawling.
- Natural-language intent is classified with AstrBot's configured LLM when available, and falls back to local rules when unavailable.
- SQLite data is stored under AstrBot `data/plugin_data/astrbot_plugin_campus_watch`.

## Server Deployment

This plugin is suitable for self-hosted AstrBot deployments on a server. After copying the plugin directory to the server, reload the plugin from AstrBot WebUI.
