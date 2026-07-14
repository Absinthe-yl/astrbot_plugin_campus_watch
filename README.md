# astrbot_plugin_campus_watch

基于 WonderCV API 的校园招聘自然语言查询插件。

## 用法

插件不再提供运维型命令列表，主要通过自然语言直接问：

- `字节开校招了吗`
- `腾讯秋招提前批开没开`
- `百度春招正式批开没开`
- `美团秋招补录开没开`
- `美团暑期实习开没开`
- `阿里寒假实习开没开`
- `哪些公司开校招了`
- `近7天哪些公司开春招了`

也保留一个兜底命令：

- `/校招 字节开校招了吗`

## 查询方式

1. AstrBot LLM 先把用户问题解析成结构化条件。
2. 插件将条件组装成 WonderCV API 请求参数。
3. 请求 WonderCV API。
4. 用对话形式返回结论。
5. 相同查询参数会优先命中本地缓存文件，不再重复请求。

支持的结构化维度：

- 公司关键词
- 校招 / 实习
- 春招 / 秋招 / 暑期实习 / 寒假实习
- 提前批 / 正式批 / 补录
- 最近 N 天

## 数据源

- WonderCV 首页：<https://www.wondercv.com/xiaozhao/>
- WonderCV API：<https://api.wondercv.com/cv/v3/campus_recruits_v2>

## 说明

- 精确问法会优先依赖 WonderCV API 的筛选结果。
- 模糊问法会返回更自然的汇总结论。
- 当前插件不再依赖旧的关注列表、手动刷新、源管理命令。
- 查询缓存保存在插件数据目录下的 `wondercv_query_cache.json`。
