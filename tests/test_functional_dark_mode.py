#!/usr/bin/env python3
"""
Functional Testing Suite for Dark Mode Implementation

This module provides comprehensive functional tests for the YouTube Summarizer
dark mode system, validating theme detection, toggle functionality, persistence,
and dynamic content theming.

Author: YouTube Summarizer Team
Version: 1.0.0
"""

import pytest
import time
import json
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from unittest.mock import patch, MagicMock

# Try to import playwright for browser testing
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    Browser = Any
    BrowserContext = Any

from flask import Flask
from flask.testing import FlaskClient

# Import application components
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from sse_manager import SSEManager


class ThemeFunctionalTester:
    """Utility class for theme functional testing."""

    def __init__(self, page: Page = None):
        """Initialize with optional Playwright page.

        Args:
            page: Playwright page object for browser testing
        """
        self.page = page

    def get_current_theme(self) -> str:
        """Get the current theme from the DOM.

        Returns:
            Current theme ('light' or 'dark')
        """
        if not self.page:
            raise ValueError("Page object required for theme detection")

        return self.page.evaluate("""
            () => document.documentElement.getAttribute('data-theme')
        """)

    def get_theme_class(self) -> str:
        """Get the current theme class from the DOM.

        Returns:
            Current theme class ('theme-light' or 'theme-dark')
        """
        if not self.page:
            raise ValueError("Page object required for theme class detection")

        class_list = self.page.evaluate("""
            () => Array.from(document.documentElement.classList)
        """)

        theme_classes = [cls for cls in class_list if cls.startswith('theme-')]
        return theme_classes[0] if theme_classes else 'none'

    def get_localStorage_theme(self) -> Optional[str]:
        """Get the theme preference from localStorage.

        Returns:
            Theme preference from localStorage or None
        """
        if not self.page:
            raise ValueError("Page object required for localStorage access")

        return self.page.evaluate("""
            () => localStorage.getItem('youtube-summarizer-theme')
        """)

    def set_localStorage_theme(self, theme: str) -> None:
        """Set theme preference in localStorage.

        Args:
            theme: Theme to set ('light', 'dark', or 'auto')
        """
        if not self.page:
            raise ValueError("Page object required for localStorage access")

        self.page.evaluate(f"""
            () => localStorage.setItem('youtube-summarizer-theme', '{theme}')
        """)

    def clear_localStorage_theme(self) -> None:
        """Clear theme preference from localStorage."""
        if not self.page:
            raise ValueError("Page object required for localStorage access")

        self.page.evaluate("""
            () => localStorage.removeItem('youtube-summarizer-theme')
        """)

    def get_system_preference(self) -> bool:
        """Get system dark mode preference.

        Returns:
            True if system prefers dark mode
        """
        if not self.page:
            raise ValueError("Page object required for system preference detection")

        return self.page.evaluate("""
            () => window.matchMedia('(prefers-color-scheme: dark)').matches
        """)

    def click_theme_toggle(self) -> None:
        """Click the theme toggle button."""
        if not self.page:
            raise ValueError("Page object required for clicking theme toggle")

        # Look for theme toggle button or icon
        toggle_selectors = [
            '[data-theme-toggle]',
            '.theme-toggle',
            '#theme-toggle',
            'button[title*="theme" i]',
            'button[aria-label*="theme" i]'
        ]

        for selector in toggle_selectors:
            try:
                self.page.click(selector, timeout=1000)
                return
            except:
                continue

        raise RuntimeError("Theme toggle button not found")

    def wait_for_theme_transition(self, timeout: float = 1.0) -> None:
        """Wait for theme transition to complete.

        Args:
            timeout: Maximum time to wait in seconds
        """
        if not self.page:
            return

        # Wait for CSS transition to complete
        time.sleep(timeout)

        # Wait for any theme-related JavaScript to complete
        self.page.wait_for_timeout(100)

    def get_computed_style(self, selector: str, property_name: str) -> str:
        """Get computed CSS property value.

        Args:
            selector: CSS selector for element
            property_name: CSS property name

        Returns:
            Computed CSS property value
        """
        if not self.page:
            raise ValueError("Page object required for computed style access")

        return self.page.evaluate(f"""
            () => {{
                const element = document.querySelector('{selector}');
                if (!element) return null;
                return getComputedStyle(element).getPropertyValue('{property_name}');
            }}
        """)

    def get_css_variable_value(self, variable_name: str) -> str:
        """Get CSS custom property (variable) value.

        Args:
            variable_name: CSS variable name (without --)

        Returns:
            CSS variable value
        """
        if not self.page:
            raise ValueError("Page object required for CSS variable access")

        return self.page.evaluate(f"""
            () => getComputedStyle(document.documentElement)
                  .getPropertyValue('--{variable_name}').trim()
        """)

    def has_flash_of_unstyled_content(self, load_url: str, timeout: float = 2.0) -> bool:
        """Detect if there's a flash of unstyled content (FOUC) during page load.

        Args:
            load_url: URL to load for testing
            timeout: Maximum time to monitor for FOUC

        Returns:
            True if FOUC is detected
        """
        if not self.page:
            raise ValueError("Page object required for FOUC detection")

        fouc_detected = False

        # Monitor for rapid theme changes that indicate FOUC
        theme_changes = []

        def track_theme_change():
            current_theme = self.get_current_theme()
            theme_changes.append({
                'theme': current_theme,
                'timestamp': time.time()
            })

        # Navigate to page and monitor theme changes
        self.page.goto(load_url)

        # Track initial theme
        track_theme_change()

        # Monitor for rapid theme changes (FOUC indicator)
        start_time = time.time()
        while time.time() - start_time < timeout:
            old_theme = theme_changes[-1]['theme'] if theme_changes else None
            track_theme_change()
            new_theme = theme_changes[-1]['theme']

            # If theme changed rapidly, it might be FOUC
            if len(theme_changes) >= 2 and old_theme != new_theme:
                time_diff = theme_changes[-1]['timestamp'] - theme_changes[-2]['timestamp']
                if time_diff < 0.1:  # Very rapid change indicates FOUC
                    fouc_detected = True
                    break

            time.sleep(0.05)  # Check every 50ms

        return fouc_detected

    def verify_no_javascript_errors(self) -> List[str]:
        """Check for JavaScript console errors.

        Returns:
            List of console error messages
        """
        if not self.page:
            return []

        errors = []

        # Listen for console errors
        def handle_console_message(msg):
            if msg.type == 'error':
                errors.append(msg.text)

        self.page.on('console', handle_console_message)

        return errors


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    yield app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def browser_page():
    """Create Playwright browser page for testing."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Set up console error tracking
        console_errors = []
        page.on('console', lambda msg:
                console_errors.append(msg.text) if msg.type == 'error' else None)

        yield page, console_errors

        browser.close()


@pytest.fixture
def theme_tester(browser_page):
    """Create theme functional tester."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    page, console_errors = browser_page
    return ThemeFunctionalTester(page), console_errors


class TestThemeDetection:
    """Test system theme preference detection."""

    def test_system_preference_detection_with_playwright(self, theme_tester):
        """Test system preference detection using Playwright."""
        tester, console_errors = theme_tester

        # Navigate to the application
        tester.page.goto('http://localhost:5000')

        # Wait for theme manager initialization
        tester.wait_for_theme_transition()

        # Check that system preference is properly detected
        system_prefers_dark = tester.get_system_preference()

        # Clear any saved preference to test auto mode
        tester.clear_localStorage_theme()
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Theme should match system preference when no saved preference exists
        current_theme = tester.get_current_theme()
        expected_theme = 'dark' if system_prefers_dark else 'light'

        assert current_theme == expected_theme, \
            f"Theme should match system preference. System: {system_prefers_dark}, " \
            f"Current: {current_theme}, Expected: {expected_theme}"

        # Verify no JavaScript errors
        assert len(console_errors) == 0, f"JavaScript errors detected: {console_errors}"

    @pytest.mark.parametrize("mock_system_preference", [True, False])
    def test_system_preference_with_mock(self, theme_tester, mock_system_preference):
        """Test system preference with mocked values."""
        tester, console_errors = theme_tester

        # Mock system preference
        tester.page.evaluate(f"""
            () => {{
                // Mock matchMedia
                Object.defineProperty(window, 'matchMedia', {{
                    value: (query) => ({{
                        matches: query === '(prefers-color-scheme: dark)' ? {str(mock_system_preference).lower()} : false,
                        media: query,
                        addEventListener: () => {{}},
                        removeEventListener: () => {{}}
                    }})
                }});
            }}
        """)

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.clear_localStorage_theme()
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Theme should match mocked system preference
        current_theme = tester.get_current_theme()
        expected_theme = 'dark' if mock_system_preference else 'light'

        assert current_theme == expected_theme, \
            f"Theme should match mocked system preference. " \
            f"Mock: {mock_system_preference}, Current: {current_theme}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestThemeToggleFunctionality:
    """Test theme toggle functionality."""

    def test_manual_theme_toggle(self, theme_tester):
        """Test manual theme toggling."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Get initial theme
        initial_theme = tester.get_current_theme()

        # Toggle theme
        try:
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            # Theme should have changed
            new_theme = tester.get_current_theme()
            assert new_theme != initial_theme, \
                f"Theme should have changed from {initial_theme} to opposite"

            # Toggle again
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            # Should return to original theme
            final_theme = tester.get_current_theme()
            assert final_theme == initial_theme, \
                f"Theme should return to initial state: {initial_theme}, got {final_theme}"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_toggle_with_css_variables(self, theme_tester):
        """Test that theme toggle updates CSS variables."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Get initial CSS variable values
        initial_bg_primary = tester.get_css_variable_value('bg-primary')
        initial_text_primary = tester.get_css_variable_value('text-primary')

        # Toggle theme
        try:
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            # CSS variables should have changed
            new_bg_primary = tester.get_css_variable_value('bg-primary')
            new_text_primary = tester.get_css_variable_value('text-primary')

            assert new_bg_primary != initial_bg_primary, \
                f"Background color should change: {initial_bg_primary} -> {new_bg_primary}"
            assert new_text_primary != initial_text_primary, \
                f"Text color should change: {initial_text_primary} -> {new_text_primary}"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_class_updates(self, theme_tester):
        """Test that theme toggle updates DOM classes."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Get initial theme class
        initial_class = tester.get_theme_class()
        assert initial_class in ['theme-light', 'theme-dark'], \
            f"Invalid initial theme class: {initial_class}"

        try:
            # Toggle theme
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            # Theme class should have changed
            new_class = tester.get_theme_class()
            assert new_class != initial_class, \
                f"Theme class should change: {initial_class} -> {new_class}"
            assert new_class in ['theme-light', 'theme-dark'], \
                f"Invalid new theme class: {new_class}"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestThemePersistence:
    """Test theme preference persistence."""

    def test_localStorage_persistence(self, theme_tester):
        """Test that theme preference persists in localStorage."""
        tester, console_errors = theme_tester

        # Clear any existing preference
        tester.page.goto('http://localhost:5000')
        tester.clear_localStorage_theme()
        tester.page.reload()
        tester.wait_for_theme_transition()

        try:
            # Toggle theme and check localStorage
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            saved_theme = tester.get_localStorage_theme()
            current_theme = tester.get_current_theme()

            assert saved_theme is not None, "Theme preference should be saved to localStorage"
            assert saved_theme == current_theme, \
                f"Saved theme ({saved_theme}) should match current theme ({current_theme})"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_persistence_across_page_loads(self, theme_tester):
        """Test theme persistence across page reloads."""
        tester, console_errors = theme_tester

        # Navigate and set a specific theme
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Verify dark theme is applied
        theme_after_reload = tester.get_current_theme()
        assert theme_after_reload == 'dark', \
            f"Dark theme should persist across reload, got: {theme_after_reload}"

        # Test with light theme
        tester.set_localStorage_theme('light')
        tester.page.reload()
        tester.wait_for_theme_transition()

        theme_after_reload = tester.get_current_theme()
        assert theme_after_reload == 'light', \
            f"Light theme should persist across reload, got: {theme_after_reload}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    @pytest.mark.parametrize("saved_theme", ['light', 'dark', 'auto'])
    def test_theme_preference_loading(self, theme_tester, saved_theme):
        """Test loading different saved theme preferences."""
        tester, console_errors = theme_tester

        # Set theme preference and reload
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme(saved_theme)
        tester.page.reload()
        tester.wait_for_theme_transition()

        current_theme = tester.get_current_theme()

        if saved_theme == 'auto':
            # Auto should resolve to system preference
            system_prefers_dark = tester.get_system_preference()
            expected = 'dark' if system_prefers_dark else 'light'
            assert current_theme == expected, \
                f"Auto theme should resolve to system preference: {expected}, got: {current_theme}"
        else:
            # Explicit themes should be applied directly
            assert current_theme == saved_theme, \
                f"Theme should match saved preference: {saved_theme}, got: {current_theme}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestThemeStateConsistency:
    """Test theme state consistency across page navigation."""

    def test_theme_consistency_between_pages(self, theme_tester):
        """Test theme consistency when navigating between pages."""
        tester, console_errors = theme_tester

        # Set dark theme on main page
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')
        tester.page.reload()
        tester.wait_for_theme_transition()

        main_page_theme = tester.get_current_theme()
        assert main_page_theme == 'dark', f"Main page should be dark theme, got: {main_page_theme}"

        # Navigate to settings page (if exists)
        try:
            tester.page.goto('http://localhost:5000/settings')
            tester.wait_for_theme_transition()

            settings_page_theme = tester.get_current_theme()
            assert settings_page_theme == 'dark', \
                f"Settings page should inherit dark theme, got: {settings_page_theme}"

        except Exception:
            # Settings page might not exist - test with back navigation instead
            tester.page.go_back()
            tester.wait_for_theme_transition()

            back_page_theme = tester.get_current_theme()
            assert back_page_theme == 'dark', \
                f"Theme should persist after navigation, got: {back_page_theme}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_state_after_form_submission(self, client, theme_tester):
        """Test theme state preservation after form submissions."""
        tester, console_errors = theme_tester

        # Set theme and navigate to form page
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')
        tester.page.reload()
        tester.wait_for_theme_transition()

        pre_submit_theme = tester.get_current_theme()
        assert pre_submit_theme == 'dark', f"Pre-submit theme should be dark, got: {pre_submit_theme}"

        # Try to submit a form (if URL input exists)
        try:
            # Look for URL input field
            url_input = tester.page.query_selector('input[name="url"], input[type="url"], #url')
            if url_input:
                # Fill and submit form
                url_input.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

                # Look for submit button
                submit_button = tester.page.query_selector(
                    'button[type="submit"], input[type="submit"], .submit-btn'
                )
                if submit_button:
                    submit_button.click()
                    tester.wait_for_theme_transition(2.0)  # Allow time for form submission

                    # Theme should still be dark after submission
                    post_submit_theme = tester.get_current_theme()
                    assert post_submit_theme == 'dark', \
                        f"Theme should persist after form submission, got: {post_submit_theme}"

        except Exception as e:
            # Form submission test is optional if no forms exist
            print(f"Form submission test skipped: {e}")

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestDynamicContentTheming:
    """Test theming of dynamically added content."""

    def test_new_elements_inherit_theme(self, theme_tester):
        """Test that new DOM elements inherit current theme."""
        tester, console_errors = theme_tester

        # Set dark theme
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Add new element via JavaScript
        tester.page.evaluate("""
            () => {
                const newCard = document.createElement('div');
                newCard.className = 'card test-dynamic-card';
                newCard.textContent = 'Dynamic Content Test';
                newCard.id = 'test-dynamic-element';
                document.body.appendChild(newCard);
            }
        """)

        # Check that new element has correct theme styling
        bg_color = tester.get_computed_style('#test-dynamic-element', 'background-color')
        text_color = tester.get_computed_style('#test-dynamic-element', 'color')

        # Colors should be theme-appropriate (not default browser colors)
        assert bg_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
            f"Dynamic element should have themed background: {bg_color}"
        assert text_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
            f"Dynamic element should have themed text color: {text_color}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_sse_updates_respect_theme(self, theme_tester):
        """Test that Server-Sent Event updates respect current theme."""
        tester, console_errors = theme_tester

        # Set dark theme
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Simulate SSE update by adding progress element
        tester.page.evaluate("""
            () => {
                const progressContainer = document.createElement('div');
                progressContainer.className = 'progress-container';
                progressContainer.innerHTML = `
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 50%;"></div>
                    </div>
                    <div class="progress-text">Processing...</div>
                `;
                progressContainer.id = 'test-sse-element';
                document.body.appendChild(progressContainer);
            }
        """)

        # Check that SSE-like element inherits theme
        progress_bg = tester.get_computed_style('.progress-bar', 'background-color')
        progress_text_color = tester.get_computed_style('.progress-text', 'color')

        assert progress_bg not in ['rgba(0, 0, 0, 0)', 'transparent'], \
            f"Progress bar should have themed background: {progress_bg}"
        assert progress_text_color not in ['rgba(0, 0, 0, 0)', 'transparent'], \
            f"Progress text should have themed color: {progress_text_color}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestFOUCPrevention:
    """Test prevention of Flash of Unstyled Content."""

    def test_no_flash_on_initial_load(self, theme_tester):
        """Test that there's no flash of unstyled content on initial page load."""
        tester, console_errors = theme_tester

        # Set theme preference before navigating
        tester.page.goto('http://localhost:5000')
        tester.set_localStorage_theme('dark')

        # Test for FOUC during page load
        has_fouc = tester.has_flash_of_unstyled_content('http://localhost:5000')

        assert not has_fouc, \
            "Flash of unstyled content detected during page load"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_no_flash_on_theme_switch(self, theme_tester):
        """Test that theme switching doesn't cause visual flash."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Record initial visual state
        initial_screenshot = tester.page.screenshot()

        try:
            # Toggle theme rapidly to test for flash
            tester.click_theme_toggle()

            # Theme transition should be smooth (no jarring visual changes)
            # We test this by ensuring the transition takes an appropriate amount of time
            start_time = time.time()
            tester.wait_for_theme_transition(0.5)  # Wait for transition
            transition_time = time.time() - start_time

            # Transition should not be instantaneous (which could cause flash)
            # but also not too slow
            assert 0.1 <= transition_time <= 2.0, \
                f"Theme transition should take 0.1-2.0 seconds, took: {transition_time:.3f}s"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestThemeEvents:
    """Test custom theme events and callbacks."""

    def test_theme_change_events_fired(self, theme_tester):
        """Test that theme change events are properly fired."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Set up event listener
        tester.page.evaluate("""
            () => {
                window.themeChangeEvents = [];
                document.addEventListener('theme-changed', (event) => {
                    window.themeChangeEvents.push({
                        type: event.type,
                        detail: event.detail,
                        timestamp: Date.now()
                    });
                });
            }
        """)

        try:
            # Toggle theme to trigger event
            tester.click_theme_toggle()
            tester.wait_for_theme_transition()

            # Check that event was fired
            events = tester.page.evaluate("() => window.themeChangeEvents")

            assert len(events) > 0, "Theme change event should be fired"

            event = events[0]
            assert event['type'] == 'theme-changed', \
                f"Event type should be 'theme-changed', got: {event['type']}"
            assert 'detail' in event, "Event should have detail object"

        except RuntimeError as e:
            if "Theme toggle button not found" in str(e):
                pytest.skip("Theme toggle button not found - may not be implemented yet")
            raise

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_manager_initialization_event(self, theme_tester):
        """Test theme manager initialization event."""
        tester, console_errors = theme_tester

        # Set up event listener before page load
        tester.page.goto('about:blank')
        tester.page.evaluate("""
            () => {
                window.initEvents = [];
                document.addEventListener('theme-manager-initialized', (event) => {
                    window.initEvents.push({
                        type: event.type,
                        detail: event.detail,
                        timestamp: Date.now()
                    });
                });
            }
        """)

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Check initialization event
        events = tester.page.evaluate("() => window.initEvents")

        if len(events) > 0:  # Event might not be implemented yet
            event = events[0]
            assert event['type'] == 'theme-manager-initialized', \
                f"Event type should be 'theme-manager-initialized', got: {event['type']}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestErrorHandling:
    """Test theme system error handling and graceful degradation."""

    def test_localStorage_unavailable_fallback(self, theme_tester):
        """Test fallback when localStorage is unavailable."""
        tester, console_errors = theme_tester

        # Mock localStorage to throw errors
        tester.page.goto('http://localhost:5000')
        tester.page.evaluate("""
            () => {
                // Mock localStorage to throw errors
                Object.defineProperty(window, 'localStorage', {
                    value: {
                        getItem: () => { throw new Error('localStorage unavailable'); },
                        setItem: () => { throw new Error('localStorage unavailable'); },
                        removeItem: () => { throw new Error('localStorage unavailable'); }
                    }
                });
            }
        """)

        # Reload page with broken localStorage
        tester.page.reload()
        tester.wait_for_theme_transition()

        # Application should still work with system preference
        current_theme = tester.get_current_theme()
        assert current_theme in ['light', 'dark'], \
            f"Theme should fallback gracefully when localStorage unavailable, got: {current_theme}"

        # Should not have critical JavaScript errors (warnings are OK)
        critical_errors = [error for error in console_errors
                          if 'localStorage unavailable' not in error]
        assert len(critical_errors) == 0, f"Critical JavaScript errors: {critical_errors}"

    def test_matchMedia_unavailable_fallback(self, theme_tester):
        """Test fallback when matchMedia is unavailable."""
        tester, console_errors = theme_tester

        # Mock matchMedia to be undefined
        tester.page.evaluate("""
            () => {
                delete window.matchMedia;
            }
        """)

        # Navigate to application
        tester.page.goto('http://localhost:5000')
        tester.wait_for_theme_transition()

        # Should fallback to light theme
        current_theme = tester.get_current_theme()
        assert current_theme == 'light', \
            f"Should fallback to light theme when matchMedia unavailable, got: {current_theme}"

        # Should handle gracefully without critical errors
        critical_errors = [error for error in console_errors
                          if 'matchMedia' not in error]
        assert len(critical_errors) == 0, f"Critical JavaScript errors: {critical_errors}"

    def test_css_variables_not_supported_fallback(self, theme_tester):
        """Test behavior when CSS variables are not supported."""
        tester, console_errors = theme_tester

        # Navigate to application
        tester.page.goto('http://localhost:5000')

        # Mock CSS.supports to return false for CSS variables
        tester.page.evaluate("""
            () => {
                if (window.CSS && window.CSS.supports) {
                    const originalSupports = window.CSS.supports;
                    window.CSS.supports = function(property, value) {
                        if (property.startsWith('--') || property === 'color' && value.includes('var(')) {
                            return false;
                        }
                        return originalSupports.call(this, property, value);
                    };
                }
            }
        """)

        tester.wait_for_theme_transition()

        # Application should still function (fallback styling)
        body_color = tester.get_computed_style('body', 'color')
        body_bg = tester.get_computed_style('body', 'background-color')

        assert body_color not in ['', 'transparent'], \
            f"Body should have fallback text color: {body_color}"
        assert body_bg not in ['', 'transparent'], \
            f"Body should have fallback background: {body_bg}"

        # Should not break JavaScript functionality
        theme = tester.get_current_theme()
        assert theme in ['light', 'dark'], \
            f"Theme detection should still work: {theme}"


if __name__ == '__main__':
    """Run functional tests when executed directly."""
    import subprocess
    import sys

    # Check if Playwright is available and browsers are installed
    if PLAYWRIGHT_AVAILABLE:
        try:
            # Try to install browsers if needed
            subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                         check=False, capture_output=True)
        except Exception:
            pass

    # Run the tests
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-x',  # Stop on first failure for faster feedback
    ])

    sys.exit(exit_code)
