# MetricMemo

This tool can generate and send HTML email reports based on data queried from Prometheus and Loki. It supports customizable email templates and includes a development server for template testing.

## CLI Usage

This tool provides a command-line interface (CLI) with the following commands:

- `send-email`: Sends the email report using the specified template.
  - `--subject-template`: (Optional) Set a custom subject template for the email report. Default is `Weekly Infrastructure Report - {{ date }}`.
- `template-dev-server`: Starts a local HTTP server to serve the template output for development.
  - `--port`: (Optional) Port for the dev server (default: `8000`).

### Global Arguments

Some arguments are applicable to all commands:

- `--template-path`: Path to any Jinja2 HTML template file (absolute or relative to your current working directory). Default: `templates/weekly.html.jinja`.
- `-t, --time`: Time range for the report data (default: `7d`).

### Example Commands

Send an email report with a custom subject:

```bash
uvx metric-memo send-email --subject-template "Custom Report - {{ date }}"
```

Start the template development server on a specific port:

```bash
uvx metric-memo template-dev-server --port 8080
```

## Installation

To use this tool, you need to have Python 3.10 or higher installed on your system. If you have pip installed, you can install the tool directly with:

```bash
pip install metric-memo
```

This will install the `metric-memo` command globally, allowing you to run it from any terminal.

## Environment Variables

The tool requires the following environment variables to be set for email functionality. They can also be defined in a `.env` file:

| Environment Variable             | Description                                                                               |
| -------------------------------- | ----------------------------------------------------------------------------------------- |
| `METRIC_MEMO_RECIPIENTS`         | Recipient email addresses separated by commas                                             |
| `METRIC_MEMO_SMTP_HOST`          | SMTP server host                                                                          |
| `METRIC_MEMO_SMTP_PORT`          | SMTP server port (if left empty, defaults to 25 for non-TLS, 587 for TLS and 465 for SSL) |
| `METRIC_MEMO_SMTP__USER`         | SMTP username                                                                             |
| `METRIC_MEMO_SMTP__PASSWORD`     | SMTP password                                                                             |
| `METRIC_MEMO_SMTP__FROM_NAME`    | Name to display in the "From" field                                                       |
| `METRIC_MEMO_SMTP__USE_STARTTLS` | Use STARTTLS for SMTP connection (true/false)                                             |
| `METRIC_MEMO_SMTP__USE_SSL`      | Use SSL for SMTP connection (true/false)                                                  |
| `METRIC_MEMO_LOKI__URL`          | Loki server URL                                                                           |
| `METRIC_MEMO_LOKI__USE_AUTH`     | Use basic authentication for Loki (true/false)                                            |
| `METRIC_MEMO_LOKI__USER`         | Loki username                                                                             |
| `METRIC_MEMO_LOKI__PASSWORD`     | Loki password                                                                             |
| `METRIC_MEMO_PROM__URL`          | Prometheus server URL                                                                     |
| `METRIC_MEMO_PROM__USE_AUTH`     | Use basic authentication for Prometheus (true/false)                                      |
| `METRIC_MEMO_PROM__USER`         | Prometheus username                                                                       |
| `METRIC_MEMO_PROM__PASSWORD`     | Prometheus password                                                                       |

## Jinja2 Template

The email report is generated using a Jinja2 HTML template. You can use any template file on your system by passing its path to `--template-path`. The bundled file at `templates/weekly.html.jinja` is only a sample template.
The template has access to the following variables:

- `time_selection`: The time range selected for the report (e.g., `7d`). This can be used in queries to Prometheus and Loki.
- `now`: The current UTC date and time as a datetime object.
- `date`: The current date in `YYYY-MM-DD` format.
- `start_date`: The start date of the selected time range.
- `end_date`: The end date of the selected time range.

### Functions

The following functions are available within the Jinja2 template for querying data:

- `query_prom(query: str)`: Executes a Prometheus query and returns the result as a single number (scalar).
- `query_prom_raw(query: str)`: Executes a Prometheus query and returns the raw result as a list (including labels and values).
- `query_loki(query: str)`: Executes a Loki query and returns a list of dictionaries `{message, count}`.
- `query_loki_top(selector: str, label: str, limit: int = 10)`: Executes a Top-N query for a specific label in Loki and returns a list of dictionaries `{label_value, count}`.
- `query_loki_raw(logql: str, limit: int = 50)`: Fetches raw log lines from Loki over the selected time window and returns a list of dictionaries `{timestamp, message, labels}`.

### Filters

The following custom filters are available within the Jinja2 template:

- `fmt_bytes(value)`: Converts a byte value into a human-readable format (e.g KB, MB, GB).
- `fmt_pct(value)`: Formats a float value as a percentage with two decimal places.
- `fmt_timedelta(value)`: Formats a timedelta value into a human-readable string (e.g., "2d 3h").
- `from_epoch(value)`: Converts an epoch timestamp to a human-readable date string.
- `to_timedelta(value)`: Converts a number of seconds into a timedelta object.

## Automatic Reporting with cron jobs

I use this tool to generate a weekly and daily infrastructure report that includes key metrics from Prometheus and recent error logs from Loki. The report is sent every morning at 6 AM to me. I achieved this by setting up a cron job that runs the `send-email` command with the appropriate time selection:

First install the tool and set up the environment variables as described in the installation section. Then, I added the following lines to schedule the reports to my crontab using `crontab -e`:

```cron
0 6 * * 1 cd ~/reporting && metric-memo -t 7d send-email --subject-template "Weekly Infrastructure Report - {{ date }}" >> ~/reporting/report.weekly.log 2>&1
0 6 * * * cd ~/reporting && metric-memo -t 1d send-email --subject-template "Daily Infrastructure Report - {{ date }}" >> ~/reporting/report.daily.log 2>&1
```

### Troubleshooting

If the setup didn't work right away, make sure to check the following:

- You replaced `~/reporting` with the actual path to the directory where you cloned the repository and set up the tool.
- Check the log files (`~/reporting/report.weekly.log` and `~/reporting/report.daily.log`) for any error messages that can help identify what went wrong.

> [!NOTE]
> I have only tested this setup on Linux machine with Ubuntu 24.04.3 LTS. If you are using a different operating system, you may need to adjust the cron job setup accordingly (e.g., using Task Scheduler on Windows or launchd on macOS).

## Contributing

Contributions to this project are welcome! If you have any ideas for improvements, bug fixes, or new features, please feel free to submit a pull request.

### Setup development environment

This project uses [UV](https://github.com/astral-sh/uv) for dependency management. To install UV follow their instruction [here](https://github.com/astral-sh/uv#installation). Once UV is installed, you can clone the repository and install the project dependencies with and create a virtual environment by running:

```bash
git clone https://github.com/JannesStroehlein/MetricMemo.git
cd MetricMemo
uv sync
```

Once the dependencies are installed, you can run the CLI with:

```bash
uv run metric-memo [command] [options]
```
