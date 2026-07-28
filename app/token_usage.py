import json
import threading
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_app_data_dir

_LOCK = threading.Lock()


def _usage_path() -> Path:
    return get_app_data_dir() / "token_usage.jsonl"


def record_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    source: str = "chat",
    model_config: str = "",
    cache_hit_tokens: int = 0,
    cache_miss_tokens: int = 0,
    estimated: bool = False,
) -> None:
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
        "cache_hit_tokens": int(cache_hit_tokens or 0),
        "cache_miss_tokens": int(cache_miss_tokens or 0),
        "estimated": bool(estimated),
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


_METRICS = (
    "input_tokens", "output_tokens", "total_tokens",
    "cache_hit_tokens", "cache_miss_tokens",
)


def _empty_metrics() -> dict[str, int]:
    return {key: 0 for key in _METRICS}


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _record_metrics(record: dict[str, Any]) -> dict[str, int]:
    values = _empty_metrics()
    values["input_tokens"] = _int_value(record.get("input_tokens"))
    values["output_tokens"] = _int_value(record.get("output_tokens"))
    values["total_tokens"] = _int_value(record.get("total_tokens"))
    if values["total_tokens"] <= 0:
        values["total_tokens"] = values["input_tokens"] + values["output_tokens"]
    values["cache_hit_tokens"] = _int_value(record.get("cache_hit_tokens"))
    values["cache_miss_tokens"] = _int_value(record.get("cache_miss_tokens"))
    return values


def _add_metrics(target: dict[str, int], values: dict[str, int]) -> None:
    for key in _METRICS:
        target[key] = int(target.get(key, 0)) + int(values.get(key, 0))


def _aggregate_range(start: date_type, end: date_type) -> dict[str, Any]:
    days: dict[str, dict[str, Any]] = {}
    current = start
    while current <= end:
        key = current.isoformat()
        days[key] = {
            "date": key,
            **_empty_metrics(),
            "models": {},
            "model_metrics": {},
            "estimated_records": 0,
        }
        current += timedelta(days=1)

    totals = _empty_metrics()
    models: dict[str, dict[str, int]] = {}
    estimated_records = 0
    for record in _iter_records():
        record_date = str(record.get("date") or record.get("timestamp", "")[:10])
        if record_date not in days:
            continue
        values = _record_metrics(record)
        if values["total_tokens"] <= 0:
            continue
        model = str(record.get("model") or "unknown")
        day = days[record_date]
        _add_metrics(day, values)
        _add_metrics(totals, values)
        day["models"][model] = int(day["models"].get(model, 0)) + values["total_tokens"]
        day_model = day["model_metrics"].setdefault(model, _empty_metrics())
        _add_metrics(day_model, values)
        model_totals = models.setdefault(model, _empty_metrics())
        _add_metrics(model_totals, values)
        if record.get("estimated") is True:
            day["estimated_records"] += 1
            estimated_records += 1

    peak_date = ""
    peak_total = 0
    for key, item in days.items():
        if item["total_tokens"] > peak_total:
            peak_date = key
            peak_total = item["total_tokens"]
    top_model = max(
        models, key=lambda name: models[name]["total_tokens"], default=""
    )
    period_days = len(days)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": days,
        "day_order": list(days),
        "models": models,
        "stats": {
            **totals,
            "average_per_day": round(totals["total_tokens"] / period_days) if period_days else 0,
            "top_model": top_model,
            "top_model_tokens": models.get(top_model, {}).get("total_tokens", 0),
            "peak_date": peak_date,
            "peak_date_tokens": peak_total,
            "estimated_records": estimated_records,
        },
    }


def aggregate_month(year: int, month: int) -> dict[str, Any]:
    """Return daily/model token aggregation for a calendar month."""
    import calendar

    year = int(year)
    month = int(month)
    _, days_in_month = calendar.monthrange(year, month)
    data = _aggregate_range(
        date_type(year, month, 1), date_type(year, month, days_in_month)
    )
    data.update({"year": year, "month": month, "days_in_month": days_in_month})
    return data


def aggregate_week(anchor_date: str = "") -> dict[str, Any]:
    """Return Monday-through-Sunday token aggregation around an ISO date."""
    try:
        anchor = date_type.fromisoformat(str(anchor_date or "")[:10])
    except ValueError:
        anchor = datetime.now().date()
    start = anchor - timedelta(days=anchor.weekday())
    end = start + timedelta(days=6)
    data = _aggregate_range(start, end)
    data["anchor_date"] = anchor.isoformat()
    return data
