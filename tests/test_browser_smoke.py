"""Browser smoke tests: real pages served by the app, driven by Playwright.

These start the Flask app on a free local port, load the real templates and
static files in headless Chromium, and check behavior that unit tests cannot
see: the pages run without JavaScript errors, the model selector is built
from /api_status, and the saved theme is applied and can be changed.

Skipped unless Playwright and its Chromium are installed:
    pip install playwright && python -m playwright install chromium
Run with: make test-browser
"""

import threading
from unittest.mock import patch

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

THEME_KEY = "youtube-summarizer-theme"


@pytest.fixture(scope="module")
def live_server():
    """Serve the app on 127.0.0.1:<free port> in a background thread."""
    from werkzeug.serving import make_server

    import ai_models
    import app as app_module
    import auth

    flask_app = app_module.app
    patches = [
        # Login off regardless of the environment or what earlier tests left behind
        patch.object(app_module, "LOGIN_ENABLED", False),
        patch.dict(auth._config, {"LOGIN_ENABLED": False}),
        patch.dict(flask_app.config, {"TESTING": True}),
        # Only Gemini is "configured", so the selector should list just the Google models
        patch.object(app_module, "google_api_key", "test-key"),
        patch.object(app_module, "openai_api_key", None),
        patch.object(app_module, "summary_cache", {}),
    ]
    for p in patches:
        p.start()

    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"url": f"http://127.0.0.1:{server.server_port}", "ai_models": ai_models}
    finally:
        server.shutdown()
        for p in patches:
            p.stop()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as e:  # browser binaries not installed
            pytest.skip(f"Playwright Chromium unavailable: {e}")
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """A fresh browser context (empty localStorage) that records JS errors."""
    context = browser.new_context()
    page = context.new_page()
    page.js_errors = []
    page.on("pageerror", lambda exc: page.js_errors.append(str(exc)))
    page.on("console", lambda msg: page.js_errors.append(msg.text) if msg.type == "error" else None)
    yield page
    context.close()


def _wait_for_models(page):
    page.wait_for_function("document.querySelectorAll('#model-select option').length > 0")


def test_index_loads_without_js_errors(live_server, page):
    page.goto(live_server["url"] + "/")
    _wait_for_models(page)
    page.wait_for_load_state("networkidle")

    assert page.title().startswith("YouTube Summarizer")
    assert page.js_errors == []


def test_model_selector_built_from_api_status(live_server, page):
    ai_models = live_server["ai_models"]
    page.goto(live_server["url"] + "/")
    _wait_for_models(page)

    options = page.eval_on_selector_all("#model-select option", "els => els.map(e => [e.value, e.textContent])")
    google = [(k, c["display_name"]) for k, c in ai_models.AVAILABLE_MODELS.items() if c["provider"] == "google"]
    assert [tuple(o) for o in options] == google
    assert page.input_value("#model-select") == ai_models.DEFAULT_MODEL


def _background(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_saved_theme_is_applied(live_server, browser):
    colors = {}
    for theme in ("light", "dark"):
        context = browser.new_context()
        context.add_init_script(f"localStorage.setItem('{THEME_KEY}', '{theme}')")
        page = context.new_page()
        page.goto(live_server["url"] + "/")
        assert page.get_attribute("html", "data-theme") == theme
        colors[theme] = _background(page)
        context.close()

    assert colors["light"] != colors["dark"]


def test_settings_theme_choice_persists(live_server, page):
    page.goto(live_server["url"] + "/settings")
    page.wait_for_function("typeof window.setTheme === 'function'")

    page.click('.theme-option[data-theme="dark"]')

    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.evaluate(f"localStorage.getItem('{THEME_KEY}')") == "dark"

    page.goto(live_server["url"] + "/")
    assert page.get_attribute("html", "data-theme") == "dark"
    assert page.js_errors == []
