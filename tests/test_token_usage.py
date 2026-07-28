import unittest
from unittest.mock import patch

from app.token_usage import aggregate_month, aggregate_week


class TokenUsageAggregationTests(unittest.TestCase):
    RECORDS = [
        {
            "date": "2026-07-06", "model": "model-a",
            "input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
            "cache_hit_tokens": 60, "cache_miss_tokens": 40,
        },
        {
            "date": "2026-07-07", "model": "model-b",
            "input_tokens": 200, "output_tokens": 30, "total_tokens": 230,
            "cache_hit_tokens": 0, "cache_miss_tokens": 200,
        },
        {
            "date": "2026-07-12", "model": "model-a",
            "input_tokens": 50, "output_tokens": 10, "total_tokens": 60,
        },
        {
            "date": "2026-08-01", "model": "model-c",
            "input_tokens": 999, "output_tokens": 999, "total_tokens": 1998,
        },
    ]

    @patch("app.token_usage._iter_records", return_value=RECORDS)
    def test_month_keeps_input_output_cache_and_model_breakdown(self, _records):
        data = aggregate_month(2026, 7)

        self.assertEqual(data["stats"]["total_tokens"], 410)
        self.assertEqual(data["stats"]["input_tokens"], 350)
        self.assertEqual(data["stats"]["output_tokens"], 60)
        self.assertEqual(data["stats"]["cache_hit_tokens"], 60)
        self.assertEqual(data["models"]["model-a"]["output_tokens"], 30)
        self.assertEqual(data["models"]["model-b"]["total_tokens"], 230)
        self.assertEqual(data["days"]["2026-07-07"]["output_tokens"], 30)

    @patch("app.token_usage._iter_records", return_value=RECORDS)
    def test_week_is_monday_through_sunday_with_daily_buckets(self, _records):
        data = aggregate_week("2026-07-08")

        self.assertEqual(data["start_date"], "2026-07-06")
        self.assertEqual(data["end_date"], "2026-07-12")
        self.assertEqual(len(data["days"]), 7)
        self.assertEqual(data["stats"]["total_tokens"], 410)
        self.assertEqual(data["stats"]["output_tokens"], 60)
        self.assertEqual(data["models"]["model-a"]["total_tokens"], 180)


if __name__ == "__main__":
    unittest.main()
