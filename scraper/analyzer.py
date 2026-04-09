"""Rule-based review analysis engine."""

import re
from collections import defaultdict
from datetime import datetime, timedelta

# ── Keyword sets by place type ─────────────────────────────────────────────
# Each set is merged with "general" at analysis time.
KEYWORD_SETS: dict[str, list[str]] = {
    # Applies to ALL place types
    "general": [
        "投訴", "要告", "告你", "告到", "法院", "退款", "賠償", "霸凌",
        "歧視", "騷擾", "恐嚇", "詐騙", "不合格",
        "態度差", "態度惡劣", "態度不好", "服務差", "服務惡劣",
        "白眼", "不理人", "不友善", "冷漠", "無視",
        "lawsuit", "refund", "discrimination", "fraud", "rude", "unfriendly",
    ],
    # 餐廳 / 飲食
    "restaurant": [
        "食物中毒", "不衛生", "老鼠", "蟑螂", "臭", "過期", "異物",
        "頭髮", "蟲", "發霉", "腐爛", "生食", "腹瀉", "拉肚子",
        "poisoning", "cockroach", "disgusting", "expired",
    ],
    # 醫院 / 診所
    "hospital": [
        "醫療疏失", "誤診", "開錯藥", "打錯針", "手術失敗", "感染",
        "護理疏忽", "醫療糾紛", "衛生局", "衛福部", "醫師公會",
        "死亡", "延誤治療", "病歷", "醫療事故", "副作用",
        "malpractice", "misdiagnosis", "negligence", "infection",
    ],
    # 百貨公司 / 零售商場
    "department_store": [
        "失竊", "扒手", "偷竊", "安全事故", "消防", "逃生", "跌倒",
        "受傷", "假貨", "仿冒", "品質瑕疵", "退換貨", "過期商品",
        "電梯故障", "停車場",
        "theft", "counterfeit", "injury", "fire safety",
    ],
}

# Supported place type labels (for UI)
PLACE_TYPE_LABELS: dict[str, str] = {
    "general":          "通用",
    "restaurant":       "餐廳／飲食",
    "hospital":         "醫院／診所",
    "department_store": "百貨／零售",
}


def get_keywords(place_type: str = "general") -> list[str]:
    """Return combined keyword list for a given place type (always includes general)."""
    base = KEYWORD_SETS["general"]
    extra = KEYWORD_SETS.get(place_type, [])
    return base + extra if place_type != "general" else base

_CHINESE_NUM = {
    "一": 1, "兩": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _parse_relative_date(date_str: str, scraped_at: str) -> str:
    """Convert a relative date string (e.g. '3 個月前') to 'YYYY-MM'."""
    try:
        base = datetime.fromisoformat(scraped_at)
    except Exception:
        base = datetime.now()

    if not date_str:
        return base.strftime("%Y-%m")

    for ch, num in _CHINESE_NUM.items():
        date_str = date_str.replace(ch, str(num))

    m = re.search(r"(\d+)", date_str)
    n = int(m.group(1)) if m else 1

    if "年" in date_str or "year" in date_str:
        delta = timedelta(days=365 * n)
    elif "月" in date_str or "month" in date_str:
        delta = timedelta(days=30 * n)
    elif "週" in date_str or "周" in date_str or "week" in date_str:
        delta = timedelta(weeks=n)
    elif "天" in date_str or "day" in date_str:
        delta = timedelta(days=n)
    else:
        delta = timedelta(days=0)

    return (base - delta).strftime("%Y-%m")


def suggest_response(review: dict, alert_reasons: list = None) -> str:
    """Generate a Chinese response suggestion based on rating and alert keywords."""
    rating = review.get("rating") or 0
    name = review.get("reviewer_name") or "您"
    alert_reasons = alert_reasons or []

    if alert_reasons:
        return (
            f"親愛的 {name}，非常感謝您的回饋。我們對您提到的問題（{'、'.join(alert_reasons[:2])}）感到非常抱歉，"
            "我們會立即進行內部調查並改善相關流程。如有需要，歡迎直接與我們聯繫，我們將竭誠為您解決問題。"
        )
    if rating <= 2:
        return (
            f"親愛的 {name}，非常感謝您給予我們寶貴的意見。"
            "我們對您這次的體驗感到非常抱歉，您的回饋對我們改善服務非常重要。"
            "我們承諾會認真檢討並改進，希望未來有機會能為您提供更好的服務。"
        )
    if rating == 3:
        return (
            f"親愛的 {name}，感謝您撥冗留下評論。"
            "我們很重視您的體驗，也希望能做得更好。"
            "如果您方便的話，歡迎告訴我們哪些地方可以改進，我們會持續努力提升服務品質。"
        )
    return ""  # 4–5 stars → no response needed


def analyze_review(review: dict, keywords: list[str] | None = None) -> dict:
    """Analyse a single review and return sentiment, alert, and response info."""
    if keywords is None:
        keywords = get_keywords("general")

    rating = review.get("rating") or 0
    text = (review.get("text") or "").lower()

    if rating >= 4:
        sentiment = "positive"
    elif rating == 3:
        sentiment = "neutral"
    else:
        sentiment = "negative"

    alert_reasons = [kw for kw in keywords if kw.lower() in text]
    is_alert = rating <= 2 or bool(alert_reasons)
    needs_response = rating <= 3 or bool(alert_reasons)

    return {
        "sentiment": sentiment,
        "is_alert": is_alert,
        "needs_response": needs_response,
        "alert_reasons": alert_reasons,
        "suggested_response": suggest_response(review, alert_reasons),
    }


def analyze_place(place_data: dict, place_type: str = "general") -> dict:
    """Run analysis on all reviews in a place record and return an enriched summary."""
    reviews = place_data.get("reviews", [])
    scraped_at = place_data.get("scraped_at", datetime.now().isoformat())
    keywords = get_keywords(place_type)

    analyzed = []
    monthly: dict = defaultdict(int)
    total_rating = 0
    rating_count = 0

    for r in reviews:
        result = analyze_review(r, keywords=keywords)
        month = _parse_relative_date(r.get("date") or "", scraped_at)
        monthly[month] += 1
        analyzed.append({**r, "analysis": result})
        if r.get("rating"):
            total_rating += r["rating"]
            rating_count += 1

    alert_count = sum(1 for r in analyzed if r["analysis"]["is_alert"])
    needs_response_count = sum(1 for r in analyzed if r["analysis"]["needs_response"])
    avg_rating = round(total_rating / rating_count, 1) if rating_count else 0

    sorted_months = sorted(monthly.keys())

    return {
        "place_name": place_data.get("place_name", ""),
        "place_url": place_data.get("place_url", ""),
        "scraped_at": scraped_at,
        "place_type": place_type,
        "place_type_label": PLACE_TYPE_LABELS.get(place_type, place_type),
        "total_reviews": len(reviews),
        "avg_rating": avg_rating,
        "alert_count": alert_count,
        "needs_response_count": needs_response_count,
        "time_distribution": {
            "labels": sorted_months,
            "data": [monthly[m] for m in sorted_months],
        },
        "reviews": analyzed,
    }
