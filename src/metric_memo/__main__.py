"""
This is the main entry point for the Metric Memo application.
"""
from metric_memo.app import build_runtime
from metric_memo.commands.send_email import run_send_email
from metric_memo.commands.template_preview import run_template_preview
from metric_memo.config.settings import Settings
from metric_memo.cli import parse_args, print_help


def main() -> int:
    """
    Main entry point for the Metric Memo application.
    Parses command-line arguments and executes the appropriate commands.
    """

    args = parse_args()

    try:
        app_settings = Settings()
    # pylint: disable=broad-except
    except Exception as e:
        print(f"Framework Error: Failed to load settings. {e}")
        return 1

    runtime = build_runtime(app_settings, args.time)

    if not args.command:
        print_help()
        return 0

    if args.command == "send-email":
        try:
            run_send_email(runtime, args.template_path, args.subject_template)
            print("Report sent!")
        # pylint: disable=broad-except
        except Exception as e:
            print(f"Error sending email: {e}")
            return 1
        return 0

    if args.command == "template-dev-server":
        try:
            run_template_preview(runtime, args.template_path, args.port)
        except KeyboardInterrupt:
            print("\nServer stopped.")
            return 130
        # pylint: disable=broad-except
        except Exception as e:
            print(f"Error running template dev server: {e}")
            return 1
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
