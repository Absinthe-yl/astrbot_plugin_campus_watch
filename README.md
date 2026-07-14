# astrbot_plugin_campus_watch

AstrBot plugin for tracking official campus recruitment pages and detecting new 2027-cohort openings.

## Features

- Monitor built-in official campus recruitment sources.
- Refresh source pages on demand.
- Record companies that appear to have newly opened 2027-cohort recruitment today.
- Maintain a personal watch list in AstrBot.
- Persist source status in local SQLite.

## Commands

- `/campus_source_list`
- `/campus_refresh`
- `/campus_refresh 腾讯`
- `/campus_today`
- `/campus_watch_add 腾讯`
- `/campus_watch_list`
- `/campus_watch_remove 腾讯`
- `/campus_status`

## Install

Place this plugin directory under:

```text
data/plugins/astrbot_plugin_campus_watch
```

Then reload plugins from AstrBot WebUI.

## Runtime Notes

- This first version uses official campus pages as the primary data source.
- It detects likely openings through keyword monitoring, not full job-detail crawling.
- SQLite data is stored under AstrBot `data/plugin_data/astrbot_plugin_campus_watch`.

## Server Deployment

This plugin is suitable for self-hosted AstrBot deployments on a server. After copying the plugin directory to the server, reload the plugin from AstrBot WebUI.
