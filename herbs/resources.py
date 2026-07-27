from pathlib import Path
import re


PACKAGE_DIRECTORY = Path(__file__).resolve().parent
QSS_URL_PATTERN = re.compile(
    r"url\(\s*(?P<quote>['\"]?)(?P<path>.*?)(?P=quote)\s*\)",
    re.IGNORECASE,
)


def resource_path(relative_path):
    """Return an absolute path to a resource shipped with DriftlessMap."""
    path = Path(relative_path)
    if path.is_absolute():
        return str(path)
    return str(PACKAGE_DIRECTORY / path)


def resolve_qss_resource_urls(stylesheet):
    """Resolve package-relative Qt stylesheet URLs independently of the CWD."""

    def replace_url(match):
        target = match.group("path").strip()
        if not target or target.startswith(
            (":", "data:", "file:", "http:", "https:", "qrc:")
        ):
            return match.group(0)
        path = Path(target)
        if not path.is_absolute():
            path = PACKAGE_DIRECTORY / path
        return 'url("{}")'.format(path.resolve().as_posix())

    return QSS_URL_PATTERN.sub(replace_url, stylesheet)
