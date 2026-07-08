import json
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_app_data_dir

_LOCK = threading.Lock()


def _usage_path() -> Path:
    return get_app_data_dir() / "token_usage.jsonl"


def record_usage(model: str, input_tokens: int, output_tokens: int, *, source: str = "chat", model_config: str = "") -> None:
    """Append one AI model-call token usage record.

    JSONL is used so recording is append-only and cheap. Each line is independent,
    which avoids rewriting a growing statistics file during streaming callbacks.
    """
    input_tokens = int(input_tokens or 0)
    output_tokens = int(output_tokens or 0)
    total_tokens = input_tokens + output_tokens
    if total_tokens <= 0:
        return

    now = datetime.now()
    rec = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.date().isoformat(),
        "model": model or "unknown",
        "model_config": model_config or "",
        "source": source or "chat",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    path = _usage_path()
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _iter_records() -> list[dict[str, Any]]:
    path = _usage_path()
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with _LOCK:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if isinstance(rec, dict):
                records.append(rec)
        except Exception:
            continue
    return records


def aggregate_month(year: int, month: int) -> dict[str, Any]:
    """Return daily/model token aggregation for a calendar month."""
    import calendar

    year = int(year)
    month = int(month)
    _, days_in_month = calendar.monthrange(year, month)
    prefix = f"{year:04d}-{month:02d}-"

    day_totals: dict[str, dict[str, Any]] = {}
    month_models: defaultdict[str, int] = defaultdict(int)
    month_total = 0

    for day in range(1, days_in_month + 1):
        date = f"{year:04d}-{month:02d}-{day:02d}"
        day_totals[date] = {"date": date, "total_tokens": 0, "models": {}}

    for rec in _iter_records():
        date = str(rec.get("date") or rec.get("timestamp", "")[:10])
        if not date.startswith(prefix) or date not in day_totals:
            continue
        model = str(rec.get("model") or "unknown")
        total = int(rec.get("total_tokens") or 0)
        if total <= 0:
            continue
        day_totals[date]["total_tokens"] += total
        models = day_totals[date]["models"]
        models[model] = int(models.get(model, 0)) + total
        month_models[model] += total
        month_total += total

    peak_date = ""
    peak_total = 0
    for date, item in day_totals.items():
        if item["total_tokens"] > peak_total:
            peak_date = date
            peak_total = item["total_tokens"]

    top_model = ""
    if month_models:
        top_model = max(month_models.items(), key=lambda kv: kv[1])[0]

    return {
        "year": year,
        "month": month,
        "days_in_month": days_in_month,
        "days": day_totals,
        "stats": {
            "total_tokens": month_total,
            "average_per_day": round(month_total / days_in_month) if days_in_month else 0,
            "top_model": top_model,
            "top_model_tokens": int(month_models.get(top_model, 0)) if top_model else 0,
            "peak_date": peak_date,
            "peak_date_tokens": peak_total,
        },
    }
