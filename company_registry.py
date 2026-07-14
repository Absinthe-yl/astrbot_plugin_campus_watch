from __future__ import annotations

COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "腾讯": (
        "腾讯",
        "腾讯科技",
        "鹅厂",
        "tx",
        "tencent",
    ),
    "字节跳动": (
        "字节",
        "字节跳动",
        "抖音",
        "今日头条",
        "头条",
        "bytedance",
    ),
    "华为": ("华为", "华子", "huawei"),
    "阿里巴巴": (
        "阿里",
        "阿里巴巴",
        "淘宝",
        "天猫",
        "阿里云",
        "alibaba",
    ),
    "京东": ("京东", "jd", "jd.com"),
    "小米": ("小米", "mi", "xiaomi"),
    "网易": ("网易", "163", "netease"),
    "拼多多": ("拼多多", "pdd", "temu"),
    "百度": ("百度", "baidu"),
    "美团": ("美团", "meituan"),
}


def canonical_companies() -> list[str]:
    return list(COMPANY_ALIASES.keys())


def aliases_for_company(company: str) -> tuple[str, ...]:
    aliases = COMPANY_ALIASES.get(company, ())
    return (company, *aliases)
