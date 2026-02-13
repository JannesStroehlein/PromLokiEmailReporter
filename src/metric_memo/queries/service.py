"""
This module defines the QueryService class, which provides methods 
to query Prometheus and Loki for metrics and logs.
"""
from prometheus_api_client.prometheus_connect import PrometheusConnect

from metric_memo.clients.loki_client import LokiClient
from metric_memo.templating.filters import get_date_range

class QueryService:
    def __init__(self, prom: PrometheusConnect, loki: LokiClient, time_selection: str):
        self.prom = prom
        self.loki = loki
        self.time_selection = time_selection

    def query_prom(self, query: str) -> int | str:
        try:
            res = self.prom.custom_query(query)
            return int(float(res[0]["value"][1])) if res else 0
        # pylint: disable=broad-except
        except Exception as e:
            return f"Error: {e}"

    def query_prom_raw(self, query: str) -> list:
        try:
            return self.prom.custom_query(query)
        # pylint: disable=broad-except
        except Exception as e:
            print(f"Prometheus Error: {e}")
            return []

    def query_loki(self, query: str) -> list[dict]:
        try:
            full_query = f"topk(5, sum by (message) (count_over_time({query} [{self.time_selection}])))"
            results = self.loki.query_raw(full_query)
            return [
                {
                    "count": int(float(item["value"][1])),
                    "message": item["metric"].get("message", "No message label found"),
                }
                for item in results
            ]
        # pylint: disable=broad-except
        except Exception as e:
            print("Error querying loki", e)
            return []

    def query_loki_top(self, selector: str, label: str, limit: int = 10) -> list[dict]:
        try:
            results = self.loki.query_top(selector, label, limit, self.time_selection)
            return sorted(results, key=lambda x: x["count"], reverse=True)
        # pylint: disable=broad-except
        except Exception as e:
            print(f"Loki Error on {label}: {e}")
            return []

    def query_loki_raw(self, logql: str, limit: int = 50) -> list[dict]:
        try:
            start_date, end_date = get_date_range(self.time_selection)
            results = self.loki.query_range(
                logql,
                start=start_date,
                end=end_date,
                limit=limit,
                direction="BACKWARD",
            )

            flattened = []
            for stream in results:
                labels = stream.get("stream", {})
                for ts_ns, line in stream.get("values", []):
                    flattened.append(
                        {
                            "timestamp": int(ts_ns),
                            "message": line,
                            "labels": labels,
                        }
                    )

            flattened.sort(key=lambda x: x["timestamp"], reverse=True)
            return flattened
        # pylint: disable=broad-except
        except Exception as e:
            print(f"Loki Raw Query Error: {e}")
            return []
