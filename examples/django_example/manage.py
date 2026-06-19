"""Run administrative commands for the Django example."""

import os

from django.core.management import execute_from_command_line


def main() -> None:
    """Execute Django's command-line utility."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_example.settings")
    execute_from_command_line()


if __name__ == "__main__":
    main()
