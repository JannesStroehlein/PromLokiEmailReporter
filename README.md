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

- `--template-path`: Path to the Jinja2 HTML template file relative to `./templates` (default: `weekly.html.jinja`).
- `-t, --time-selection`: Time range for the report data (default: `7d`).

### Example Commands

Send an email report with a custom subject:

```bash
uv run main.py send-email --subject-template "Custom Report - {{ date }}"
```

Start the template development server on a specific port:

```bash
uv run main.py template-dev-server --port 8080
```

## Installation

To setup the project, first clone the repository and navigate to the project directory.

```bash
git clone https://github.com/JannesStroehlein/MetricMemo.git
cd MetricMemo
```

This project uses [UV](https://github.com/astral-sh/uv) for dependency management. To install UV follow their instruction [here](https://github.com/astral-sh/uv#installation). Once UV is installed, you can install the project dependencies with and create a virtual environment by running:

```bash
uv sync
```

Once the dependencies are installed, you can run the CLI with:

```bash
uv run main.py [command] [options]
```

## Environment Variables

The tool requires the following environment variables to be set for email functionality. They can also be defined in a `.env` file:

| Environment Variable | Description                                          |
| -------------------- | ---------------------------------------------------- |
| `EMAIL_TO`           | Recipient email address                              |
| `SMTP_HOST`          | SMTP server host                                     |
| `SMTP_PORT`          | SMTP server port                                     |
| `SMTP_USER`          | SMTP username                                        |
| `SMTP_PASSWORD`      | SMTP password                                        |
| `SMTP_FROM_NAME`     | Name to display in the "From" field                  |
| `SMTP_USE_TLS`       | Use TLS for SMTP connection (true/false)             |
| `SMTP_USE_SSL`       | Use SSL for SMTP connection (true/false)             |
| `LOKI_URL`           | Loki server URL                                      |
| `LOKI_USE_AUTH`      | Use basic authentication for Loki (true/false)       |
| `LOKI_USER`          | Loki username                                        |
| `LOKI_PASS`          | Loki password                                        |
| `PROM_URL`           | Prometheus server URL                                |
| `PROM_USE_AUTH`      | Use basic authentication for Prometheus (true/false) |
| `PROM_USER`          | Prometheus username                                  |
| `PROM_PASS`          | Prometheus password                                  |

## Jinja2 Template

The email report is generated using a Jinja2 HTML template. You can customize the template to fit your reporting needs. The default template file is `weekly.html.jinja`.
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
0 6 * * 1 cd ~/reporting && .venv/bin/python main.py -t 7d send-email --subject-template "Weekly Infrastructure Report - {{ date }}" >> ~/reporting/report.weekly.log 2>&1
0 6 * * * cd ~/reporting && .venv/bin/python main.py -t 1d send-email --subject-template "Daily Infrastructure Report - {{ date }}" >> ~/reporting/report.daily.log 2>&1
```

### Troubleshooting

If the setup didn't work right away, make sure to check the following:

- You replaced `~/reporting` with the actual path to the directory where you cloned the repository and set up the tool.
- The virtual environment is correctly activated in the cron job command (e.g., `.venv/bin/python`).
  - If this is not working, you might didn't run the `uv sync` command to create the virtual environment and install dependencies. More information on how to do this can be found in the [Installation](#installation) section.
- Check the log files (`~/reporting/report.weekly.log` and `~/reporting/report.daily.log`) for any error messages that can help identify what went wrong.

> [!NOTE]
> I have only tested this setup on Linux machine with Ubuntu 24.04.3 LTS. If you are using a different operating system, you may need to adjust the cron job setup accordingly (e.g., using Task Scheduler on Windows or launchd on macOS).
