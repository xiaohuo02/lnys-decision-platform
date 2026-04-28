# -*- coding: utf-8 -*-
"""
柠优生活科技有限公司 - 基础配置文件
所有数据处理脚本的共享常量和映射表
"""

import numpy as np

# ─────────────────────────────────────────────
# 1. 门店配置（8家线下门店）
# ─────────────────────────────────────────────
STORES = {
    "NDE-001": {"name": "宁德旗舰店",   "city": "宁德", "province": "福建", "tier": "三线"},
    "NDE-002": {"name": "宁德东侨店",   "city": "宁德", "province": "福建", "tier": "三线"},
    "FUZ-001": {"name": "福州仓山店",   "city": "福州", "province": "福建", "tier": "二线"},
    "FUZ-002": {"name": "福州台江店",   "city": "福州", "province": "福建", "tier": "二线"},
    "XMN-001": {"name": "厦门思明店",   "city": "厦门", "province": "福建", "tier": "二线"},
    "QZH-001": {"name": "泉州丰泽店",   "city": "泉州", "province": "福建", "tier": "二线"},
    "SHA-001": {"name": "上海静安店",   "city": "上海", "province": "上海", "tier": "一线"},
    "HZH-001": {"name": "杭州西湖店",   "city": "杭州", "province": "浙江", "tier": "一线"},
}
STORE_IDS = list(STORES.keys())

# Walmart Store(1~45) → 柠优门店（mod 8 映射）
WALMART_STORE_MAP = {i: STORE_IDS[i % 8] for i in range(1, 46)}

# 门店层级销售缩放因子（相对于 Walmart 原始数据）
TIER_SCALE = {"一线": 1.0, "二线": 0.65, "三线": 0.40}

# ─────────────────────────────────────────────
# 2. SKU 商品目录（26个SKU）
# ─────────────────────────────────────────────
SKUS = {
    # A类：宁德特产礼盒
    "A001": {"name": "坦洋工夫茶·特级礼盒",       "category": "宁德特产礼盒", "unit_price": 298, "season": "全年"},
    "A002": {"name": "天山绿茶·手工散茶",           "category": "宁德特产礼盒", "unit_price": 168, "season": "春夏"},
    "A003": {"name": "福鼎白茶·老白茶饼",           "category": "宁德特产礼盒", "unit_price": 388, "season": "全年"},
    "A004": {"name": "宁德大黄鱼·风干礼盒",         "category": "宁德特产礼盒", "unit_price": 268, "season": "节日旺季"},
    "A005": {"name": "宁德鲍鱼·即食礼盒",           "category": "宁德特产礼盒", "unit_price": 498, "season": "节日"},
    "A006": {"name": "古田银耳·养生礼盒",           "category": "宁德特产礼盒", "unit_price": 158, "season": "全年"},
    # B类：健康食品
    "B001": {"name": "有机燕麦片1kg",               "category": "健康食品",     "unit_price": 58,  "season": "全年"},
    "B002": {"name": "混合坚果·每日坚果30包",       "category": "健康食品",     "unit_price": 88,  "season": "全年"},
    "B003": {"name": "黑芝麻丸·传统手工",           "category": "健康食品",     "unit_price": 128, "season": "秋冬"},
    "B004": {"name": "枸杞红枣·养生组合",           "category": "健康食品",     "unit_price": 78,  "season": "全年"},
    "B005": {"name": "即食燕窝·NFC鲜炖6瓶",         "category": "健康食品",     "unit_price": 398, "season": "全年"},
    "B006": {"name": "益生菌粉·儿童版30包",         "category": "健康食品",     "unit_price": 138, "season": "全年"},
    # C类：茶饮系列
    "C001": {"name": "乌龙茶·安溪铁观音250g",       "category": "茶饮系列",     "unit_price": 198, "season": "全年"},
    "C002": {"name": "花草茶·洛神玫瑰组合",         "category": "茶饮系列",     "unit_price": 88,  "season": "春夏"},
    "C003": {"name": "冷泡茶包·冰摇系列20包",       "category": "茶饮系列",     "unit_price": 68,  "season": "夏季"},
    "C004": {"name": "普洱茶·7年陈357g饼",         "category": "茶饮系列",     "unit_price": 328, "season": "秋冬"},
    # D类：生活家居
    "D001": {"name": "香薰蜡烛·天然大豆蜡",         "category": "生活家居",     "unit_price": 98,  "season": "全年"},
    "D002": {"name": "精油扩香器·竹木款",           "category": "生活家居",     "unit_price": 258, "season": "全年"},
    "D003": {"name": "竹制厨房收纳套装",             "category": "生活家居",     "unit_price": 168, "season": "全年"},
    "D004": {"name": "陶瓷餐具套装",                 "category": "生活家居",     "unit_price": 298, "season": "全年"},
    "D005": {"name": "茶具套装·功夫茶盘",           "category": "生活家居",     "unit_price": 368, "season": "全年"},
    # E类：个护美妆
    "E001": {"name": "有机玫瑰水·补水喷雾100ml",   "category": "个护美妆",     "unit_price": 128, "season": "全年"},
    "E002": {"name": "山茶花发油·护发精华",         "category": "个护美妆",     "unit_price": 178, "season": "全年"},
    "E003": {"name": "绿茶洁面泡泡100ml",           "category": "个护美妆",     "unit_price": 88,  "season": "全年"},
    "E004": {"name": "防晒霜·SPF50户外款",         "category": "个护美妆",     "unit_price": 158, "season": "夏季"},
    "E005": {"name": "有机面膜·白茶系列5片",       "category": "个护美妆",     "unit_price": 108, "season": "全年"},
}
SKU_CODES = list(SKUS.keys())

# 按价格区间映射 SKU（UCI 原价格 £ → 柠优 SKU）
PRICE_TIER_SKUS = {
    "low":       ["B001", "B002", "C003"],            # £0.1~£1.5  → ¥48~¥88
    "mid_low":   ["B002", "C002", "E003", "E005"],    # £1.5~£5    → ¥88~¥128
    "mid":       ["A002", "A006", "C001", "D001", "E001", "E002"],  # £5~£15 → ¥168~¥258
    "mid_high":  ["A001", "A004", "D002", "D003", "D004"],          # £15~£30 → ¥268~¥368
    "high":      ["A003", "A005", "B005", "D005", "C004"],          # £30+    → ¥388~¥498
}

# UCI 商品描述关键词 → SKU 映射
DESCRIPTION_KEYWORD_MAP = {
    "tea":          "A001", "teabag":       "A001", "infuser":     "C001",
    "candle":       "D001", "wax":          "D001", "aroma":       "D002",
    "ceramic":      "D004", "mug":          "D004", "bowl":        "D004",
    "bamboo":       "D003", "kitchen":      "D003", "storage":     "D003",
    "rose":         "E001", "serum":        "E002", "cream":       "E001",
    "face":         "E003", "mask":         "E005", "sunscreen":   "E004",
    "nut":          "B002", "almond":       "B002", "walnut":      "B002",
    "oat":          "B001", "grain":        "B001",
    "gift":         "A001", "box":          "A001", "set":         "D005",
    "teapot":       "D005", "tray":         "D005",
}

# ─────────────────────────────────────────────
# 3. 线上订单城市分布（加权抽样）
# ─────────────────────────────────────────────
ONLINE_CITY_POOL = {
    "北京": 0.08, "上海": 0.10, "广州": 0.09, "深圳": 0.08,
    "杭州": 0.06, "成都": 0.06, "武汉": 0.05, "南京": 0.05,
    "西安": 0.04, "重庆": 0.04,
    "厦门": 0.04, "宁波": 0.03, "合肥": 0.03, "福州": 0.04,
    "长沙": 0.03, "济南": 0.03,
    "宁德": 0.05, "其他城市": 0.10,
}
ONLINE_CITIES  = list(ONLINE_CITY_POOL.keys())
ONLINE_WEIGHTS = list(ONLINE_CITY_POOL.values())

# 城市 → 省份映射
CITY_PROVINCE_MAP = {
    "北京": "北京", "上海": "上海", "广州": "广东", "深圳": "广东",
    "杭州": "浙江", "成都": "四川", "武汉": "湖北", "南京": "江苏",
    "西安": "陕西", "重庆": "重庆", "厦门": "福建", "宁波": "浙江",
    "合肥": "安徽", "福州": "福建", "长沙": "湖南", "济南": "山东",
    "宁德": "福建", "其他城市": "其他",
}

# ─────────────────────────────────────────────
# 4. 支付方式分布
# ─────────────────────────────────────────────
PAYMENT_METHODS  = ["支付宝", "微信支付", "信用卡", "现金"]
PAYMENT_WEIGHTS  = [0.50,    0.35,      0.10,    0.05]

# ─────────────────────────────────────────────
# 5. 会员等级分布
# ─────────────────────────────────────────────
MEMBER_LEVELS   = ["普通", "银卡", "金卡", "钻石"]
MEMBER_WEIGHTS  = [0.50,  0.30,  0.15,  0.05]

# ─────────────────────────────────────────────
# 6. 中国节假日（含前后促销窗口）
# ─────────────────────────────────────────────
# 格式：(月, 日起, 日止, 节日名)  — 适用于所有年份
HOLIDAY_WINDOWS = [
    (1,  20, 31, "春节"),
    (2,   1, 10, "春节假期"),
    (5,   1,  5, "劳动节"),
    (6,  16, 21, "618大促"),
    (9,  15, 22, "中秋"),
    (10,  1,  7, "国庆"),
    (11,  1, 12, "双11大促"),
    (12, 25, 31, "年末促销"),
]

def is_holiday(month: int, day: int) -> int:
    """判断某月某日是否处于促销窗口，返回 0/1"""
    for m, d_start, d_end, _ in HOLIDAY_WINDOWS:
        if month == m and d_start <= day <= d_end:
            return 1
    return 0

# ─────────────────────────────────────────────
# 7. 日期偏移（UCI 2009-2011 → 2022-2024）
# ─────────────────────────────────────────────
DATE_SHIFT_YEARS = 13   # 加 13 年

# ─────────────────────────────────────────────
# 8. 辅助函数
# ─────────────────────────────────────────────
def map_description_to_sku(description: str, unit_price_gbp: float = 0.0) -> str:
    """
    将 UCI 商品描述映射到柠优 SKU 编码。
    优先关键词匹配；无法匹配则按英镑价格区间降级映射。
    """
    desc_lower = str(description).lower()
    for keyword, sku in DESCRIPTION_KEYWORD_MAP.items():
        if keyword in desc_lower:
            return sku
    # 按价格区间降级
    if unit_price_gbp < 1.5:
        tier = "low"
    elif unit_price_gbp < 5:
        tier = "mid_low"
    elif unit_price_gbp < 15:
        tier = "mid"
    elif unit_price_gbp < 30:
        tier = "mid_high"
    else:
        tier = "high"
    candidates = PRICE_TIER_SKUS[tier]
    return candidates[hash(description) % len(candidates)]


def get_sku_price(sku_code: str) -> float:
    """获取 SKU 的人民币单价，默认返回 88"""
    return SKUS.get(sku_code, {}).get("unit_price", 88)


if __name__ == "__main__":
    print(f"门店数量: {len(STORES)}")
    print(f"SKU数量:  {len(SKUS)}")
    print(f"城市池:   {len(ONLINE_CITIES)} 个城市")
    print("company_config.py 加载正常 ✓")
