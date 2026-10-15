"""Local handover draft. Never sends or uploads it."""
from .report import main as report_main


def main(argv=None):
    return report_main(argv, handover=True)
