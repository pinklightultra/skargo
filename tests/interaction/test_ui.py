"""Playwright: every desk control paints an outcome, including the failure branches."""

import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from examples.demo.desk.controls import control_ids
from examples.demo.desk.server import serve_background

REPO = Path(__file__).resolve().parents[2]
LAME = REPO / "tests" / "fixtures" / "lameenc"
SHOTS = Path("/opt/cursor/artifacts/screenshots")


def _value_for(ident):
    if ident.startswith("fader:"):
        return "0.2"
    if ident == "kbps":
        return "128"
    if ident == "pod-override":
        return "4"
    if ident == "backlog":
        return ""
    return None


def _drive(page, ident):
    page.evaluate("() => { document.querySelector('#outcome').dataset.ready = '0'; }")
    el = page.locator('button[data-id="%s"], input[data-id="%s"]' % (ident, ident))
    tag = el.evaluate("node => node.tagName")
    if tag == "INPUT":
        el.evaluate(
            """(node, value) => {
                if (value !== null) node.value = value;
                node.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            _value_for(ident),
        )
    else:
        el.click()
    page.wait_for_function(
        """(id) => {
            const node = document.querySelector('#outcome');
            return node.dataset.ready === '1' && node.dataset.ran === id;
        }""",
        arg=ident,
    )
    tone = page.locator("#outcome").get_attribute("data-tone")
    summary = page.locator("#outcome-summary").inner_text().strip()
    assert tone in ("ok", "warn", "fail"), ident
    assert summary, ident
    return tone, summary


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        launched = playwright.chromium.launch(
            headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            yield launched
        finally:
            launched.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    tab = context.new_page()
    tab.set_default_timeout(180000)
    errors = []
    tab.on("pageerror", lambda err: errors.append(str(err)))
    tab.errors = errors
    try:
        yield tab
    finally:
        context.close()


def _open(page, root):
    httpd = serve_background(root)
    host, port = httpd.server_address[:2]
    page.goto("http://%s:%s/" % (host, port), wait_until="domcontentloaded")
    page.wait_for_selector('[data-id="stage:init"]')
    return httpd


def test_every_control_paints_an_outcome(page, finished, tmp_path):
    root = tmp_path / "show"
    shutil.copytree(finished, root)
    httpd = _open(page, root)
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "desk-loaded.png"), full_page=True)
        tone, summary = _drive(page, "stage:check")
        assert tone == "ok" and "0 failures" in page.locator("#outcome-detail").inner_text()
        page.screenshot(path=str(SHOTS / "desk-outcome.png"), full_page=True)
        seen = []
        for ident in control_ids():
            _drive(page, ident)
            seen.append(ident)
        assert tuple(seen) == control_ids()
        tone, summary = _drive(page, "cast:edge")
        assert tone == "ok" and "edge" in summary
        tone, summary = _drive(page, "stage:voices")
        assert tone == "fail" and "edge" in (summary + page.locator("#outcome-detail").inner_text()).lower()
        assert page.errors == []
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_empty_folder_clicks(page, tmp_path):
    httpd = _open(page, tmp_path / "empty")
    try:
        expect = {
            "stage:script": ("fail", "scene numbers"),
            "stage:check": ("fail", "FileNotFoundError"),
            "stage:voices": ("fail", "FileNotFoundError"),
            "stage:music": ("fail", "FileNotFoundError"),
            "stage:mix": ("fail", "FileNotFoundError"),
            "stage:levels": ("fail", "FileNotFoundError"),
            "stage:mp3": ("warn", "0 files"),
            "stage:sfx": ("fail", "FileNotFoundError"),
            "stage:timeline": ("warn", "0 utterances"),
            "stage:init": ("ok", "copied 2 parts"),
        }
        for ident, (tone, snippet) in expect.items():
            got, summary = _drive(page, ident)
            detail = page.locator("#outcome-detail").inner_text()
            assert got == tone, (ident, got, summary)
            assert snippet in summary or snippet in detail, (ident, summary, detail[-400:])
        assert page.errors == []
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mobile_init_is_clickable(page, tmp_path):
    page.set_viewport_size({"width": 390, "height": 844})
    httpd = _open(page, tmp_path / "phone")
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / "desk-mobile.png"), full_page=True)
        tone, summary = _drive(page, "stage:init")
        assert tone == "ok" and "copied 2 parts" in summary
        box = page.locator('button[data-id="stage:init"]').bounding_box()
        assert box["width"] >= 40 and box["height"] >= 40
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_mp3_button_writes_with_the_fixture_encoder(page, finished, tmp_path):
    root = tmp_path / "show"
    shutil.copytree(finished, root)
    sys.path.insert(0, str(LAME))
    sys.modules.pop("lameenc", None)
    httpd = _open(page, root)
    try:
        tone, summary = _drive(page, "kbps")
        assert tone == "ok" and "128" in summary
        tone, summary = _drive(page, "stage:mp3")
        assert tone == "ok", summary + page.locator("#outcome-detail").inner_text()[-500:]
        encoded = root / "audio" / "episodes" / "LOW_TIDE_EP1_scratch.mp3"
        assert encoded.read_bytes().startswith(b"LAME" + (128).to_bytes(2, "little"))
    finally:
        sys.path.remove(str(LAME))
        sys.modules.pop("lameenc", None)
        httpd.shutdown()
        httpd.server_close()
