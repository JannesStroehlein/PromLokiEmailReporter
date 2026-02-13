"""
Abstraction layer for querying Loki logs. Provides methods for raw queries, 
range queries, and top-N queries by label.
"""
from datetime import datetime
import requests
from requests.auth import HTTPBasicAuth

class LokiClient:
    """
    Loki Client for querying Loki logs
    
    :var logql: Loki query language string
    :vartype logql: str
    :var Query: topk(N, sum by (label) (count_over_time(selector [time_selection])))
    :vartype Query: str
    """
    def __init__(self, url: str, user: str = None, password: str = None):
        self.url = url
        self.auth = HTTPBasicAuth(user, password) if user and password else None

    @staticmethod
    def _to_ns(ts):
        if ts is None:
            return None
        if isinstance(ts, (int, float)):
            # Assume seconds since epoch
            return int(ts * 1_000_000_000)
        if isinstance(ts, datetime):
            return int(ts.timestamp() * 1_000_000_000)
        raise TypeError(f"Unsupported timestamp type: {type(ts)!r}")

    def query_raw(self, logql: str, time=None, limit: int | None = None,
                  direction: str | None = None):
        """
        Instant query against Loki.

        logql: Loki query language string

        Returns the raw JSON result from Loki
        """
        try:
            params = {'query': logql}
            if time is not None:
                params['time'] = self._to_ns(time)
            if limit is not None:
                params['limit'] = int(limit)
            if direction is not None:
                params['direction'] = direction

            r = requests.get(
                f"{self.url}/loki/api/v1/query",
                params=params,
                auth=self.auth,
                timeout=15,
            )

            # Loki (or a proxy like Grafana) will often return HTML on auth/404.
            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

            payload = r.json()
            return payload.get('data', {}).get('result', [])
        except Exception as e:
            print(f"Loki Error: {e}")
            return []

    def query_range(
        self,
        logql: str,
        start,
        end,
        limit: int = 100,
        direction: str = "BACKWARD",
    ):
        """
        Range query against Loki. Use this for fetching raw log lines over a time window.

        Returns the raw JSON result list from Loki (data.result).
        """
        try:
            params = {
                'query': logql,
                'start': self._to_ns(start),
                'end': self._to_ns(end),
                'limit': int(limit),
                'direction': direction,
            }

            r = requests.get(
                f"{self.url}/loki/api/v1/query_range",
                params=params,
                auth=self.auth,
                timeout=30,
            )

            if not r.ok:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")

            payload = r.json()
            return payload.get('data', {}).get('result', [])
        except Exception as e:
            print(f"Loki Range Error: {e}")
            return []

    def query_top(self, selector: str, label: str, limit: int = 10, time_selection: str = "7d"):
        """
        Generic Top-N query for any label (Country, ASN, UserAgent, etc.)
        Query: topk(N, sum by (label) (count_over_time(selector [time_selection])))

        Returns a list of dicts with 'label' and 'count'
        """
        logql = f'topk({limit}, sum by ({
            label}) (count_over_time({selector} [{time_selection}])))'

        try:
            results = self.query_raw(logql)
            parsed = []
            for item in results:
                parsed.append({
                    "name": item['metric'].get(label, 'Unknown'),
                    "count": int(float(item['value'][1]))
                })
            return parsed
        except Exception as e:
            print(f"Loki Top-N Error: {e}")
            return []
