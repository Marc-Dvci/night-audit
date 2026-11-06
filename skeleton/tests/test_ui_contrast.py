"""Every text and background pair of the kit meets WCAG 2.2 AA, computed from the palette in style.css (Req 10.1).

axe-core checks the rendered page in the browser tests; this check needs no browser and fails as soon as a token
changes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = (Path(__file__).resolve().parents[1] / "web" / "src" / "style.css").read_text(encoding="utf-8")
ROOT_BLOCK = re.search(r":root\s*\{(.*?)\}", CSS, re.S)
assert ROOT_BLOCK is not None
TOKENS = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6}|rgba\([^)]*\))", ROOT_BLOCK.group(1)))

RGB = tuple[float, float, float]


def rgb(token: str, over: RGB | None = None) -> RGB:
    value = TOKENS[token]
    if value.startswith("#"):
        return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))
    r, g, b, a = (float(x) for x in value[5:-1].split(","))
    base = over if over is not None else rgb("ink")
    return (r * a + base[0] * (1 - a), g * a + base[1] * (1 - a), b * a + base[2] * (1 - a))


def tint(r: float, g: float, b: float, alpha: float, over: RGB) -> RGB:
    return (r * alpha + over[0] * (1 - alpha), g * alpha + over[1] * (1 - alpha), b * alpha + over[2] * (1 - alpha))


def luminance(color: RGB) -> float:
    def channel(c: float) -> float:
        s = c / 255
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg: RGB, bg: RGB) -> float:
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


TEXT = ["bone", "bone-dim", "phosphor", "amber", "moon", "blood"]
GROUNDS = ["ink", "ink-2", "ink-3"]


@pytest.mark.parametrize("ground", GROUNDS)
@pytest.mark.parametrize("text", TEXT)
def test_text_tokens_are_readable_on_every_band(text: str, ground: str) -> None:
    assert ratio(rgb(text), rgb(ground)) >= 4.5


def test_the_skip_link_is_readable() -> None:
    assert ratio(rgb("ink"), rgb("phosphor")) >= 4.5


@pytest.mark.parametrize("text", ["bone", "bone-dim", "amber"])
def test_venn_labels_are_readable_on_the_tinted_finding_regions(text: str) -> None:
    assert ratio(rgb(text), tint(255, 179, 71, 0.07, rgb("ink"))) >= 4.5


@pytest.mark.parametrize("text", ["bone", "amber"])
def test_labels_of_a_selected_finding_region_are_readable(text: str) -> None:
    assert ratio(rgb(text), tint(255, 179, 71, 0.34, rgb("ink"))) >= 4.5


@pytest.mark.parametrize("text", ["bone", "phosphor"])
def test_labels_of_a_selected_region_are_readable(text: str) -> None:
    assert ratio(rgb(text), tint(124, 255, 178, 0.26, rgb("ink"))) >= 4.5


def test_selected_region_labels_are_drawn_in_bone() -> None:
    assert re.search(r"\.venn-name\.sel, \.venn-count\.zero\.sel \{ fill: var\(--bone\); \}", CSS)


def test_the_palette_matches_the_steering_file() -> None:
    expected = {"ink": "#0b1020", "ink-2": "#141b33", "phosphor": "#7cffb2", "bone": "#edeae0", "amber": "#ffb347",
                "moon": "#c9d3ff", "blood": "#ff5a6e"}
    assert {k: TOKENS[k].lower() for k in expected} == expected


def test_blood_is_used_only_for_findings_older_than_three_nights() -> None:
    uses = [line.strip() for line in CSS.splitlines() if "var(--blood)" in line]
    assert uses and all(".old" in line for line in uses), uses


def test_no_rounded_corners_and_no_gradient_except_the_scan_line() -> None:
    assert "border-radius: 0" in CSS or "border-radius" not in CSS
    assert not re.search(r"border-radius:\s*[1-9]", CSS)
    gradients = [line for line in CSS.splitlines() if "gradient(" in line]
    assert len(gradients) == 1 and "transparent, var(--phosphor), transparent" in gradients[0]
