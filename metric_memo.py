"""
MetricMemo: A Python application to generate and email infrastructure reports using
Prometheus and Loki data.
This application queries Prometheus for metrics and Loki for logs, 
renders an email report using Jinja2 templates, and sends it via SMTP. 

It also includes a development server to preview the email template in a browser.
"""
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import smtplib

import argparse
import re
from requests.auth import HTTPBasicAuth

from prometheus_api_client.prometheus_connect import PrometheusConnect

from jinja2 import Environment, FileSystemLoader
from loki_client import LokiClient
from settings import Settings
from template_dev_server import TemplateDevServer

# Services you want to track
TIME_SELECTION_REGEX = r"(?P<num>\d+)(?P<unit>\w)"

# --- HELPER FUNCTIONS ---

def get_start_date(end_date: datetime, number: int, unit: str):
    match unit:
        case "h":
            return end_date - timedelta(hours=number)
        case "d":
            return end_date - timedelta(days=number)
        case _:
            raise ValueError("Invalid time selection")


def get_date_range(selector: str):
    """
    Returns the start and end date for a LogQL/PromQL time selector like 7d or 24h
    """
    end_date = datetime.now()
    match = re.search(TIME_SELECTION_REGEX, selector)
    if not match:
        raise RuntimeError(f"Invalid time selection format: {selector}")

    number = match.group("num")
    unit = match.group("unit")

    return (get_start_date(end_date, int(number), unit), end_date)


def from_epoch(epoch_time):
    return datetime.fromtimestamp(epoch_time, timezone.utc)


def format_bytes(size):
    # Converts raw bytes to GB/TB
    power = 2**30
    n = size / power
    if n > 1024:
        return f"{n/1024:.2f} TB"
    return f"{n:.2f} GB"


def format_percent(val):
    return f"{val:.2f}%"


def format_timedelta(td: timedelta):
    days = td.days
    hours, remainder = divmod(td.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0:
        parts.append(f"{seconds}s")
    return " ".join(parts)


class MetricMemo:
    """
    The main class for the application. Initializes Prometheus and Loki clients,
    provides query methods, and handles email rendering/sending.
    """

    def __init__(self, settings: Settings, time_selection: str = "7d"):
        self.settings = settings
        self.time_selection = time_selection

        # Initialize Prometheus
        self.prom = PrometheusConnect(
            url=settings.prom.url,
            disable_ssl=False,
            auth=(
                HTTPBasicAuth(settings.prom.user, settings.prom.password)
                if settings.prom.use_auth
                else None
            ),
        )

        # Initialize Loki
        self.loki = LokiClient(
            url=settings.loki.url,
            user=settings.loki.user if settings.loki.use_auth else None,
            password=settings.loki.password if settings.loki.use_auth else None,
        )

        self.loader = FileSystemLoader("templates")
        self.jinja_environment = Environment(autoescape=True, loader=self.loader)
        self.setup_jinja_env()

    def query_prom(self, query: str) -> int | str:
        """Returns a single number (scalar) from Prometheus"""
        try:
            res = self.prom.custom_query(query)
            # return the value or 0 if empty
            return int(float(res[0]["value"][1])) if res else 0
        except Exception as e:
            return f"Error: {e}"

    def query_prom_raw(self, query: str) -> list:
        """Returns the raw result from Prometheus"""
        try:
            res = self.prom.custom_query(query)
            return res
        except Exception as e:
            print(f"Prometheus Error: {e}")
            return []

    def query_loki(self, query: str) -> list[dict]:
        """Returns a list of dicts {message, count} from Loki"""
        try:
            # Enforce a time lookback from selection
            full_query = f"topk(5, sum by (message) (count_over_time({{query}} [{{self.time_selection}}])))".format(
                query=query, self=self
            )
            # Wait, f-string with double braces for query/self.time_selection logic
            # Correct f-string:
            full_query = f"topk(5, sum by (message) (count_over_time({query} [{self.time_selection}])))"

            results = self.loki.query_raw(full_query)
            parsed = []
            for item in results:
                parsed.append(
                    {
                        "count": int(float(item["value"][1])),
                        "message": item["metric"].get(
                            "message", "No message label found"
                        ),
                    }
                )
            return parsed
        except Exception as e:
            print("Error querying loki", e)
            return []

    def query_loki_top(self, selector: str, label: str, limit: int = 10) -> list[dict]:
        """
        Generic Top-N query for any label (Country, ASN, UserAgent, etc.)
        """
        try:
            # Fetch from Loki
            results = self.loki.query_top(selector, label, limit, self.time_selection)

            # Sort by count desc
            return sorted(results, key=lambda x: x["count"], reverse=True)
        except Exception as e:
            print(f"Loki Error on {label}: {e}")
            return []

    def query_loki_raw(self, logql: str, limit: int = 50) -> list[dict]:
        """Fetch raw log lines from Loki over the selected time window."""
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
        except Exception as e:
            print(f"Loki Raw Query Error: {e}")
            return []

    def setup_jinja_env(self):
        start_date, end_date = get_date_range(self.time_selection)

        self.jinja_environment.globals["time_selection"] = self.time_selection
        self.jinja_environment.globals["start_date"] = start_date
        self.jinja_environment.globals["end_date"] = end_date
        self.jinja_environment.globals["date"] = datetime.now().strftime("%Y-%m-%d")
        self.jinja_environment.globals["now"] = datetime.now(timezone.utc)

        self.jinja_environment.globals["query_prom"] = self.query_prom
        self.jinja_environment.globals["query_prom_raw"] = self.query_prom_raw
        self.jinja_environment.globals["query_loki"] = self.query_loki
        self.jinja_environment.globals["query_loki_top"] = self.query_loki_top
        self.jinja_environment.globals["query_loki_raw"] = self.query_loki_raw

        self.jinja_environment.filters["to_timedelta"] = lambda x: timedelta(
            seconds=int(x)
        )
        self.jinja_environment.filters["from_epoch"] = from_epoch
        self.jinja_environment.filters["fmt_bytes"] = format_bytes
        self.jinja_environment.filters["fmt_pct"] = format_percent
        self.jinja_environment.filters["fmt_timedelta"] = format_timedelta

    def get_template(self, path: str):
        return self.jinja_environment.get_template(path)

    def render_html(self, path: str):
        template = self.get_template(path)
        return template.render()

    def render_email_subject(self, template_str: str):
        template = self.jinja_environment.from_string(template_str)
        return template.render(
            time_selection=self.time_selection, date=datetime.now().strftime("%Y-%m-%d")
        )

    def send_email(self, path: str, subject: str):
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"{self.settings.smtp.from_name} <{self.settings.smtp.user}>"

        # HTML Body
        html_body = self.render_html(path)
        msg.attach(MIMEText(html_body, "html"))

        # Determine port and usage of TLS/STARTTLS
        port = self.settings.smtp.port or (
            465
            if self.settings.smtp.use_ssl
            else 587 if self.settings.smtp.use_starttls else 25
        )

        if self.settings.smtp.use_ssl:
            server = smtplib.SMTP_SSL(self.settings.smtp.host, port)
        else:
            server = smtplib.SMTP(self.settings.smtp.host, port)

        with server:
            if self.settings.smtp.use_starttls:
                server.starttls()

            # Login if credentials provided
            if self.settings.smtp.user and self.settings.smtp.password:
                server.login(self.settings.smtp.user, self.settings.smtp.password)

            # Send email to each recipient individually
            for recipient in self.settings.recipients:
                msg["To"] = recipient
                server.send_message(msg)

def main():
    """
    The main entry point of the application. Parses command-line arguments, loads settings, 
    and either sends the email report or starts the template dev server
    based on the provided command.
    """
    parser = argparse.ArgumentParser(prog="metric-memo")
    parser.add_argument(
        "-t",
        "--time",
        default="7d",
        help="Set the time selection for the stats (24h, 7d)",
    )
    parser.add_argument(
        "--template-path",
        default="weekly.html.jinja",
        help="Set the template path to use for the report",
    )

    # Verb for dev server or send email
    commands = parser.add_subparsers(title="sub-commands", dest="command")

    mail_parser = commands.add_parser("send-email", help="Send the email report")
    mail_parser.add_argument(
        "--subject-template",
        default="Weekly Infrastructure Report - {{ date }}",
        help="Set a custom subject template for the email report",
    )

    dev_parser = commands.add_parser(
        "template-dev-server",
        help="Start a local HTTP server to serve the template output for development",
    )
    dev_parser.add_argument(
        "--port", type=int, default=8000, help="Port for the dev server (default: 8000)"
    )

    args = parser.parse_args()

    # Create Settings instance
    try:
        app_settings = Settings()
    except Exception as e:
        print(f"Framework Error: Failed to load settings. {e}")
        exit(1)

    memo = MetricMemo(app_settings, args.time)

    if not args.command:
        parser.print_help()
    else:
        if args.command == "send-email":
            subject = memo.render_email_subject(args.subject_template)
            try:
                memo.send_email(args.template_path, subject)
                print("Report sent!")
            except Exception as e:
                print(f"Error sending email: {e}")

        elif args.command == "template-dev-server":
            try:
                server = TemplateDevServer(memo, args.template_path, args.port)
                server.start()
            except KeyboardInterrupt:
                print("\nServer stopped.")

# --- MAIN ---
if __name__ == "__main__":
    main()
