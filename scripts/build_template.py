import logging
from pathlib import Path
from typing import Any, Dict


def build(
        logger: logging.Logger,
        course_key: str,
        path: Path,
        image: str,
        env: Dict[str, str],
        settings: Any,
        **kwargs,
        ) -> bool:
    """
    Build the course rooted at <path> synchronously. Use <logger> to log build
    output and return whether the build succeeded. <settings> is the value
    specified in django settings for BUILD_MODULE_SETTINGS.
    """