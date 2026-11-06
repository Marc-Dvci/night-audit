"""The page shell: link card, favicon, policy and fonts, checked without a browser (ui-kit Req 9, 11.2).

The built page (``skeleton/web/dist``) is checked when it exists; the browser tests check the rendered page.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from nightaudit.api import CONTENT_SECURITY_POLICY

WEB = Path(__file__).resolve().parents[1] / "web"
DIST = WEB / "dist" / "index.html"


class _Head(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.links: list[dict[str, str | None]] = []
        self.scripts: list[dict[str, str | None]] = []
        self.inline_script = False
        self._in_script = False
        self.styles = 0
        self.style_attrs = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if "style" in a:
            self.style_attrs += 1
        if tag == "meta":
            name = a.get("name") or a.get("property") or a.get("http-equiv")
            if name:
                self.meta[name] = a.get("content") or ""
        elif tag == "link":
            self.links.append(a)
        elif tag == "script":
            self.scripts.append(a)
            self._in_script = "src" not in a
        elif tag == "style":
            self.styles += 1

    def handle_data(self, data: str) -> None:
        if self._in_script and data.strip():
            self.inline_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False


def parse(path: Path) -> _Head:
    head = _Head()
    head.feed(path.read_text(encoding="utf-8"))
    return head


def test_the_page_has_a_title_description_and_link_card() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    head = parse(WEB / "index.html")
    assert re.search(r"<title>Night Audit[^<]+</title>", page)
    assert head.meta["description"]
    for name in ("og:title", "og:description", "og:image", "og:image:alt", "twitter:card", "twitter:image"):
        assert head.meta.get(name), name
    assert (head.meta["og:image:width"], head.meta["og:image:height"]) == ("1200", "630")
    assert head.meta["twitter:card"] == "summary_large_image"


def test_the_favicon_is_an_svg_file() -> None:
    icon = next(link for link in parse(WEB / "index.html").links if link.get("rel") == "icon")
    assert icon["href"] == "./favicon.svg" and icon["type"] == "image/svg+xml"
    assert (WEB / "public" / "favicon.svg").read_text(encoding="utf-8").startswith("<svg")


def test_fonts_are_self_hosted_and_drawn_once() -> None:
    fonts = (WEB / "src" / "fonts.css").read_text(encoding="utf-8")
    assert fonts.count("@font-face") == 4
    assert fonts.count("font-display: block") == 4
    assert "http" not in fonts
    assert all((WEB / "src" / url).resolve().exists() for url in re.findall(r'url\("([^"]+)"\)', fonts))
    main = (WEB / "src" / "main.ts").read_text(encoding="utf-8")
    assert "document.fonts.load" in main and "@fontsource" not in main


@pytest.mark.skipif(not DIST.exists(), reason="build the front end first: npm run build in skeleton/web")
def test_the_built_page_carries_the_policy_and_no_inline_code() -> None:
    head = parse(DIST)
    assert head.meta["Content-Security-Policy"] == CONTENT_SECURITY_POLICY.replace("; frame-ancestors 'none'", "")
    assert not head.inline_script and head.styles == 0 and head.style_attrs == 0
    page = DIST.read_text(encoding="utf-8")
    assert page.index('<meta charset="utf-8"') < page.index("Content-Security-Policy")
    assert (DIST.parent / "assets" / "verify.js").exists()
    assert "http://" not in page and "https://" not in page


def test_no_source_module_writes_an_inline_style() -> None:
    for path in (WEB / "src").rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        assert 'style="' not in text and ".style." not in text, path.name
