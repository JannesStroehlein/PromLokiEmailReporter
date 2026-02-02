from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
import smtplib

import argparse
import re
import os
from requests.auth import HTTPBasicAuth

from prometheus_api_client.prometheus_connect import PrometheusConnect
from prometheus_api_client.utils import parse_datetime

from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv

from LokiClient import LokiClient

load_dotenv()

# --- CONFIGURATION ---

PROM_URL = os.getenv("PROM_URL")
PROM_USE_AUTH = os.getenv("PROM_USE_AUTH") == "true"
PROM_USER = os.getenv("PROM_USER")
PROM_PASS = os.getenv("PROM_PASS")

LOKI_URL = os.getenv("LOKI_URL")
LOKI_USE_AUTH = os.getenv("LOKI_USE_AUTH") == "true"
LOKI_USER = os.getenv("LOKI_USER")
LOKI_PASS = os.getenv("LOKI_PASS")

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT")) if os.getenv("SMTP_PORT") else None
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS") == "true"
SMTP_USE_STARTTLS = os.getenv("SMTP_USE_STARTTLS") == "true"
EMAIL_TO = os.getenv("EMAIL_TO")

# Services you want to track
TRAEFIK_SERVICES = [
    "backend-contact@docker",
    "backend-projects@docker",
    "frontend@docker"
]

time_selection_regex = r"(?P<num>\d+)(?P<unit>\w)"

prom = PrometheusConnect(url=PROM_URL, disable_ssl=False, auth=HTTPBasicAuth(PROM_USER, PROM_PASS) if PROM_USE_AUTH else None)
loki = LokiClient(url=LOKI_URL, user=LOKI_USER if LOKI_USE_AUTH else None, password=LOKI_PASS if LOKI_USE_AUTH else None)

loader = FileSystemLoader("templates")
env = Environment(autoescape=True, loader=loader)

time_selection = "7d"


def query_prom(query):
    """Returns a single number (scalar) from Prometheus"""
    try:
        res = prom.custom_query(query)
        # return the value or 0 if empty
        return int(float(res[0]['value'][1])) if res else 0
    except Exception as e:
        return f"Error: {e}"

def query_prom_raw(query):
    """Returns the raw result from Prometheus"""
    try:
        res = prom.custom_query(query)
        return res
    except Exception as e:
        print(f"Prometheus Error: {e}")
        return []

def query_loki(query):
    """Returns a list of dicts {message, count} from Loki"""
    try:
        # Enforce a 7-day lookback for simplicity in the template
        # You could also pass the time range as an arg if you wanted
        full_query = f'topk(5, sum by (message) (count_over_time({
            query} [{time_selection}])))'

        results = loki.query_raw(full_query)
        parsed = []
        for item in results:
            parsed.append({
                "count": int(float(item['value'][1])),
                "message": item['metric'].get('message', 'No message label found')
            })
        return parsed
    except Exception as e:
        print("Error querying loki", e)
        return []


def query_loki_top(selector, label, limit=10):
    """
    Generic Top-N query for any label (Country, ASN, UserAgent, etc.)
    Query: topk(N, sum by (label) (count_over_time(selector [7d])))
    """
    try:
        # 2. Fetch from Loki
        results = loki.query_top(selector, label, limit, time_selection)

        # 4. Sort by count desc (just to be safe)
        return sorted(results, key=lambda x: x['count'], reverse=True)
    except Exception as e:
        print(f"Loki Error on {label}: {e}")
        return []

def query_loki_raw(logql, limit: int = 50):
    """Fetch raw log lines from Loki over the selected time window.

    For log streams (e.g. '{job="fail2ban"}'), Loki returns "streams" where each stream
    contains a list of (timestamp, line) pairs. This helper flattens those into a list of
    dicts: {timestamp, message, labels} sorted newest-first.
    """
    try:
        start_date, end_date = get_date_range(time_selection)
        results = loki.query_range(
            logql,
            start=start_date,
            end=end_date,
            limit=limit,
            direction="BACKWARD",
        )

        flattened = []
        for stream in results:
            labels = stream.get('stream', {})
            for ts_ns, line in stream.get('values', []):
                flattened.append({
                    'timestamp': int(ts_ns),
                    'message': line,
                    'labels': labels,
                })

        flattened.sort(key=lambda x: x['timestamp'], reverse=True)
        return flattened
    except Exception as e:
        print(f"Loki Raw Query Error: {e}")
        return []

# --- JINJA FORMATTERS ---

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
    return ' '.join(parts)

def get_template(path: str):
    return env.get_template(path)

def render_html(path: str):
    template = get_template(path)

    start_date, end_date = get_date_range(time_selection)

    return template.render(
        time_selection=time_selection,
        start_date=start_date,
        end_date=end_date,
        services=TRAEFIK_SERVICES,
        date=datetime.now().strftime("%Y-%m-%d")
    )


def send_email(path: str, subject: str):
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg['To'] = EMAIL_TO

    # HTML Body

    html_body = render_html(path)
    msg.attach(MIMEText(html_body, 'html'))

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def get_start_date(end_date: datetime, number: int, unit: str):
    match unit:
        case 'h':
            return end_date - timedelta(hours=number)
        case 'd':
            return end_date - timedelta(days=number)
        case _:
            raise ValueError("Invalid time selection")


def get_date_range(selector: str):
    """
    Returns the start and end date for a LogQL/PromQL time selector like 7d or 24h
    """
    end_date = datetime.now()
    match = re.search(time_selection_regex, selector)
    if not match:
        raise RuntimeError()

    number = match.group("num")
    unit = match.group("unit")

    return (
        get_start_date(end_date, int(number), unit),
        end_date
    )

def render_email_subject(template_str: str):
    template = env.from_string(template_str)
    return template.render(
        time_selection=time_selection,
        date=datetime.now().strftime("%Y-%m-%d")
    )

def template_dev_server(path: str, port: int):
    """
    Starts a HTTP server that serves the template output. The template is re-rendered when the page is refreshed.
    
    :param path: Description
    :type path: str
    """

    from http.server import HTTPServer, BaseHTTPRequestHandler

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = render_html(path)
            self.wfile.write(html.encode('utf-8'))

    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print("Starting template dev server at http://localhost:8000")
    httpd.serve_forever()

def setup_jinja_env():
    env.globals['now'] = datetime.now(timezone.utc)
    env.globals['query_prom'] = query_prom
    env.globals['query_prom_raw'] = query_prom_raw
    env.globals['query_loki'] = query_loki
    env.globals['query_loki_top'] = query_loki_top
    env.globals['query_loki_raw'] = query_loki_raw
    
    env.filters['to_timedelta'] = lambda x: timedelta(seconds=int(x))
    env.filters['format_timedelta'] = format_timedelta
    env.filters['from_epoch'] = from_epoch
    env.filters['fmt_bytes'] = format_bytes
    env.filters['fmt_pct'] = format_percent

# --- MAIN ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='J3SReports')
    parser.add_argument('-t', '--time',
                        default='7d',
                        help='Set the time selection for the stats (24h, 7d)')
    parser.add_argument('--template-path',
                        default='weekly.html.jinja',
                        help='Set the template path to use for the report')
    
    # Verb for dev server or send email
    commands = parser.add_subparsers(title='sub-commands')

    mail_parser = commands.add_parser('send-email', help='Send the email report')
    mail_parser.add_argument('--subject-template',
                            default='Weekly Infrastructure Report - {{ date }}',
                            help='Set a custom subject template for the email report')
    
    dev_parser = commands.add_parser('template-dev-server', help='Start a local HTTP server to serve the template output for development')
    dev_parser.add_argument('--port', type=int, default=8000, help='Port for the dev server (default: 8000)')

    args = parser.parse_args()

    time_selection = args.time if args.time else time_selection

    setup_jinja_env()

    if not commands.choices:
        parser.print_help()
    else:
        if 'send-email' in commands.choices and isinstance(args, argparse.Namespace) and hasattr(args, 'subject_template'):
            send_email(args.template_path, render_email_subject(args.subject_template))
            print("Report sent!")
        else:
            template_dev_server(args.template_path, args.port)
