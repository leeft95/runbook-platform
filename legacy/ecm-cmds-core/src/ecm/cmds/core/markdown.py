from dataclasses import dataclass

import bleach
import markdown2
from bleach.css_sanitizer import CSSSanitizer

CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color",
        "background-color",
        "font-weight",
        "font-style",
        "text-decoration",
        "text-align",
        "white-space",
        "border",
        "border-top",
        "border-right",
        "border-bottom",
        "border-left",
        "border-color",
        "border-style",
        "border-width",
        "padding",
        "padding-top",
        "padding-right",
        "padding-bottom",
        "padding-left",
        "margin",
        "margin-top",
        "margin-right",
        "margin-bottom",
        "margin-left",
        "width",
        "max-width",
    ],
)

DEFAULT_MD_EXTRAS = [
    "fenced-code-blocks",
    "tables",
    "strike",
    "task_list",
    "cuddled-lists",
]

_ALLOWED_TAGS = [
    "p",
    "br",
    "hr",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "del",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "a",
    "img",
    "span",
    "div",
]
_ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "code": ["class"],
    "span": ["class"],
    "div": ["class", "style"],
    "th": ["colspan", "rowspan", "style"],
    "td": ["colspan", "rowspan", "style"],
    "table": ["style"],
}
_ALLOWED_PROTOCOLS = ["http", "https", "mailto", "file", "data"]


def markdown_to_html(
    text: str,
    *,
    extras: list[str] | None = None,
    safe: bool = True,
) -> str:
    extras = DEFAULT_MD_EXTRAS if extras is None else extras

    md_html = markdown2.markdown(
        text,
        extras=extras,
        safe_mode="escape" if safe else None,
    )

    if safe:
        md_html = bleach.clean(
            str(md_html),
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRS,
            protocols=_ALLOWED_PROTOCOLS,
            strip=True,
            css_sanitizer=CSS_SANITIZER,
        )
    return str(md_html)


@dataclass(frozen=True)
class Markdown:
    text: str
    safe: bool = True
    extras: list[str] | None = None
    wrap: bool = True
    css_class: str = "markdown"

    def to_html(self) -> str:
        body = markdown_to_html(self.text, extras=self.extras, safe=self.safe)
        return f"<div class='{self.css_class}'>{body}</div>" if self.wrap else body


def MD(text: str, **kwargs) -> Markdown:
    return Markdown(text=text, **kwargs)
