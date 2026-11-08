import glob
import os

import pytest


def _find_chromium():
    if os.environ.get("GPCHECK_CHROMIUM"):
        return os.environ["GPCHECK_CHROMIUM"]
    hits = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"))
    return hits[-1] if hits else None  # None -> Playwright's own downloaded browser


@pytest.fixture(scope="session")
def chromium():
    return _find_chromium()
