"""Aerolith: tactile UI rendered in Bryce 2, packaged as static files.

The CSS, the optional JS and the sprites live in ``aerolith/static/aerolith/``:

    from aerolith import static_dir
    static_dir() / "aerolith.css"

Django: add ``"aerolith"`` to INSTALLED_APPS, then ``{% static 'aerolith/aerolith.css' %}``.
Flask:  ``app.add_url_rule`` / a Blueprint with ``static_folder=static_dir()``.
FastAPI / Starlette: ``app.mount("/aerolith", StaticFiles(directory=static_dir()))``.
"""
from pathlib import Path

__version__ = "1.2.0"
__all__ = ["static_dir", "css_path", "js_path", "__version__"]


def static_dir() -> Path:
    """Directory holding aerolith.css, aerolith.js and sprites/."""
    return Path(__file__).resolve().parent / "static" / "aerolith"


def css_path() -> Path:
    return static_dir() / "aerolith.css"


def js_path() -> Path:
    return static_dir() / "aerolith.js"
