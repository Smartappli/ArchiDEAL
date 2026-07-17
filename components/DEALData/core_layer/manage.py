#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys

from django.core.management import execute_from_command_line


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    try:
        execute_from_command_line(sys.argv)
    except ImportError as exc:
        message = "Couldn't import Django. Are you sure it's installed and "
        message += "available on your PYTHONPATH environment variable? Did you "
        message += "forget to activate a virtual environment?"
        raise ImportError(message) from exc


if __name__ == "__main__":
    main()
