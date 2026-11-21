"""Запуск ThermoDrop: ``python main.py [файл]``."""

import sys

from thermodrop.app import run

if __name__ == "__main__":
    sys.exit(run(sys.argv))
