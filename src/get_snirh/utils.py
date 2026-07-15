"""Text and date helpers."""

import datetime as _dt
import html as _html
import re
import unicodedata

from .constants import MARKER_CHAR


def strip_accents(text: str) -> str:
    """Remove diacritics: NFD-decompose and drop combining marks."""
    decomposed = unicodedata.normalize("NFD", str(text))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(name: str) -> str:
    """Derive a network slug from a name.

    Rule: de-accent (NFD), lowercase, collapse runs of non-alphanumerics to
    ``_``, strip leading/trailing ``_``.

    >>> slugify("Hidrométrica Açores")
    'hidrometrica_acores'
    >>> slugify("* Piezometria")
    'piezometria'
    >>> slugify("Águas Balneares")
    'aguas_balneares'
    """
    text = strip_accents(name).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def unescape_html(text: str) -> str:
    """``html.unescape`` until stable (SNIRH sometimes double-escapes,
    e.g. ``&amp;#9632;``)."""
    for _ in range(4):
        unescaped = _html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return text


def clean_marker_label(text: str) -> str:
    """Unescape a SNIRH label and strip its ``■`` markers.

    SNIRH only ever prefixes the marker, but every occurrence is replaced —
    a label carrying one mid-string would be cleaned too.

    >>> clean_marker_label("&amp;#9632; Piezometria")
    'Piezometria'
    """
    return unescape_html(text).replace(MARKER_CHAR, " ").strip()


_DDMMYYYY = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def to_snirh_date(value, name: str = "date") -> str:
    """Coerce a date to the ``dd/mm/yyyy`` string SNIRH endpoints require.

    Accepts ISO ``'YYYY-MM-DD'`` strings and ``datetime.date`` /
    ``datetime.datetime`` objects. Rejects ``'dd/mm/yyyy'`` strings.
    """
    if type(value).__name__ == "NaTType":
        raise TypeError(
            f"{name} is NaT (pandas missing-value marker); pass an ISO "
            "'YYYY-MM-DD' string or a datetime.date/datetime object, not a "
            "missing/NaT value."
        )
    if isinstance(value, _dt.datetime):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, _dt.date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        text = value.strip()
        if _DDMMYYYY.match(text):
            raise ValueError(
                f"{name}={value!r} looks like 'dd/mm/yyyy', which is no longer "
                "accepted. Pass an ISO 'YYYY-MM-DD' string or a "
                "datetime.date/datetime object."
            )
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = _dt.datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"Could not parse {name}={value!r}. Use an ISO 'YYYY-MM-DD' "
                "string or a datetime.date/datetime object."
            ) from exc
        return parsed.strftime("%d/%m/%Y")
    raise TypeError(
        f"{name} must be an ISO 'YYYY-MM-DD' string or a "
        f"datetime.date/datetime object, got {type(value).__name__}"
    )
