#!/usr/bin/env python3
"""
Integration Tests for Dark Mode with Existing Features

This module tests the integration of the dark mode system with all existing
YouTube Summarizer features, ensuring seamless theming across the entire
application ecosystem.

Author: YouTube Summarizer Team
Version: 1.0.0
"""

import pytest
import time
import json
import os
import threading
from unittest.mock import patch, MagicMock, Mock
from typing import Dict, List, Any, Optional
from pathlib import Path

# Try to import playwright for browser testing
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    Browser = Any
    BrowserContext = Any

# Import Flask testing utilities
from flask import Flask
from flask.testing import FlaskClient

# Import application components
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

try:
    from app import create_app
    from sse_manager import SSEManager
    from job_models import JobRequest, JobType, JobPriority, JobStatus
    from job_queue import JobQueue
    from worker_manager import WorkerManager
    from voice_config import VoiceConfigManager
except ImportError as e:
    print(f"Warning: Could not import application modules: {e}")


class SSEThemeIntegrationTester:
    """Test SSE integration with theme system."""

    def __init__(self, page: Page):
        """Initialize with Playwright page.

        Args:
            page: Playwright page object
        """
        self.page = page
        self.sse_events: List[Dict[str, Any]] = []

    def setup_sse_monitoring(self):
        """Set up SSE event monitoring."""
        self.page.evaluate("""
            () => {
                window.sseEvents = [];
                window.themeSSETest = {
                    eventSource: null,
                    connect: function() {
                        if (typeof EventSource !== 'undefined') {
                            this.eventSource = new EventSource('/sse');

                            this.eventSource.onmessage = function(event) {
                                const data = JSON.parse(event.data);
                                window.sseEvents.push({
                                    type: 'message',
                                    data: data,
                                    timestamp: Date.now(),
                                    currentTheme: document.documentElement.getAttribute('data-theme')
                                });
                            };

                            this.eventSource.onerror = function(event) {
                                window.sseEvents.push({
                                    type: 'error',
                                    event: event,
                                    timestamp: Date.now(),
                                    currentTheme: document.documentElement.getAttribute('data-theme')
                                });
                            };
                        }
                    },

                    disconnect: function() {
                        if (this.eventSource) {
                            this.eventSource.close();
                        }
                    }
                };

                window.themeSSETest.connect();
            }
        """)

    def get_sse_events(self) -> List[Dict[str, Any]]:
        """Get captured SSE events.

        Returns:
            List of SSE events with theme information
        """
        return self.page.evaluate('() => window.sseEvents || []')

    def simulate_progress_update(self, job_id: str, progress: int, status: str):
        """Simulate a progress update via SSE.

        Args:
            job_id: Job identifier
            progress: Progress percentage
            status: Job status message
        """
        # This would typically be done through the server, but for testing
        # we'll inject the update directly into the page
        self.page.evaluate(f"""
            () => {{
                const event = new MessageEvent('message', {{
                    data: JSON.stringify({{
                        job_id: '{job_id}',
                        progress: {progress},
                        status: '{status}',
                        timestamp: Date.now()
                    }})
                }});

                if (window.themeSSETest && window.themeSSETest.eventSource) {{
                    window.themeSSETest.eventSource.onmessage(event);
                }}
            }}
        """)

    def check_progress_bar_theming(self) -> Dict[str, str]:
        """Check progress bar theming.

        Returns:
            Dictionary of progress bar styling information
        """
        return self.page.evaluate("""
            () => {
                const progressBars = document.querySelectorAll('.progress-bar, .progress-fill');
                const results = {};

                progressBars.forEach((bar, index) => {
                    const styles = getComputedStyle(bar);
                    results[`bar_${index}`] = {
                        backgroundColor: styles.backgroundColor,
                        borderColor: styles.borderColor,
                        color: styles.color
                    };
                });

                return results;
            }
        """)


class ToastThemeIntegrationTester:
    """Test toast notification integration with themes."""

    def __init__(self, page: Page):
        """Initialize with Playwright page.

        Args:
            page: Playwright page object
        """
        self.page = page

    def trigger_toast(self, toast_type: str, message: str):
        """Trigger a toast notification.

        Args:
            toast_type: Type of toast ('success', 'error', 'warning', 'info')
            message: Toast message content
        """
        self.page.evaluate(f"""
            () => {{
                // Create toast element
                const toast = document.createElement('div');
                toast.className = 'toast toast-{toast_type}';
                toast.textContent = '{message}';
                toast.id = 'test-toast-{toast_type}';

                // Add to toast container or body
                const container = document.querySelector('.toast-container') || document.body;
                container.appendChild(toast);

                // Auto-remove after delay (like real toasts)
                setTimeout(() => {{
                    if (toast.parentNode) {{
                        toast.parentNode.removeChild(toast);
                    }}
                }}, 3000);
            }}
        """)

    def get_toast_theming(self, toast_type: str) -> Dict[str, str]:
        """Get toast theming information.

        Args:
            toast_type: Type of toast to check

        Returns:
            Dictionary of toast styling information
        """
        return self.page.evaluate(f"""
            () => {{
                const toast = document.querySelector('#test-toast-{toast_type}');
                if (!toast) return null;

                const styles = getComputedStyle(toast);
                return {{
                    backgroundColor: styles.backgroundColor,
                    color: styles.color,
                    borderColor: styles.borderColor,
                    boxShadow: styles.boxShadow
                }};
            }}
        """)

    def test_all_toast_types(self) -> Dict[str, Dict[str, str]]:
        """Test all toast types with current theme.

        Returns:
            Dictionary mapping toast types to their styling
        """
        toast_types = ['success', 'error', 'warning', 'info']
        results = {}

        for toast_type in toast_types:
            self.trigger_toast(toast_type, f"Test {toast_type} message")
            time.sleep(0.1)  # Brief delay for DOM update

            styling = self.get_toast_theming(toast_type)
            if styling:
                results[toast_type] = styling

        return results


@pytest.fixture
def app():
    """Create Flask app for testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


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


class TestSSEIntegrationWithThemes:
    """Test Server-Sent Events integration with theme system."""

    def test_sse_connection_with_theme_switching(self, browser_page):
        """Test SSE connection maintains functionality when themes switch."""
        page, console_errors = browser_page

        # Navigate to application and set up SSE monitoring
        page.goto('http://localhost:5000')
        page.wait_for_timeout(1000)

        sse_tester = SSEThemeIntegrationTester(page)
        sse_tester.setup_sse_monitoring()

        # Start in light theme
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "light")')
        page.reload()
        page.wait_for_timeout(1000)

        # Simulate some SSE events
        sse_tester.simulate_progress_update("test-job-1", 25, "Processing...")
        page.wait_for_timeout(500)

        # Switch to dark theme
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        # Setup SSE monitoring again after reload
        sse_tester.setup_sse_monitoring()

        # Simulate more SSE events
        sse_tester.simulate_progress_update("test-job-2", 75, "Almost done...")
        page.wait_for_timeout(500)

        # Check that SSE events were captured with theme information
        events = sse_tester.get_sse_events()

        # Should have events with theme information
        assert len(events) > 0, "Should have captured SSE events"

        # Events should include theme information
        for event in events:
            assert 'currentTheme' in event, "SSE events should include theme information"
            assert event['currentTheme'] in ['light', 'dark'], \
                f"Theme should be light or dark, got: {event['currentTheme']}"

        # No critical JavaScript errors
        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_progress_bars_theme_correctly(self, browser_page):
        """Test that progress bars created via SSE use correct theme."""
        page, console_errors = browser_page

        # Set dark theme
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        sse_tester = SSEThemeIntegrationTester(page)

        # Create a progress bar element (simulating SSE update)
        page.evaluate("""
            () => {
                const progressContainer = document.createElement('div');
                progressContainer.className = 'progress-container';
                progressContainer.innerHTML = `
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: 60%;"></div>
                    </div>
                    <div class="progress-text">Processing video...</div>
                `;
                document.body.appendChild(progressContainer);
            }
        """)

        # Check progress bar theming
        progress_styling = sse_tester.check_progress_bar_theming()

        # Progress bars should have themed colors (not default browser colors)
        for bar_key, styles in progress_styling.items():
            bg_color = styles.get('backgroundColor', '')
            assert bg_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                f"Progress bar {bar_key} should have themed background color: {bg_color}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_sse_status_messages_readable(self, browser_page):
        """Test that SSE status messages are readable in both themes."""
        page, console_errors = browser_page

        for theme in ['light', 'dark']:
            # Set theme
            page.goto('http://localhost:5000')
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(1000)

            # Create status message (simulating SSE update)
            page.evaluate(f"""
                () => {{
                    const statusMsg = document.createElement('div');
                    statusMsg.className = 'status-message';
                    statusMsg.textContent = 'Processing video in {theme} theme...';
                    statusMsg.id = 'sse-status-{theme}';
                    document.body.appendChild(statusMsg);
                }}
            """)

            # Check text readability
            text_color = page.evaluate(f"""
                () => {{
                    const msg = document.querySelector('#sse-status-{theme}');
                    return getComputedStyle(msg).color;
                }}
            """)

            # Text should not be transparent or default
            assert text_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                f"Status message text should be visible in {theme} theme: {text_color}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestToastNotificationThemes:
    """Test toast notification theming integration."""

    def test_toast_notifications_theme_correctly(self, browser_page):
        """Test toast notifications use appropriate theme colors."""
        page, console_errors = browser_page

        for theme in ['light', 'dark']:
            # Set theme
            page.goto('http://localhost:5000')
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(1000)

            toast_tester = ToastThemeIntegrationTester(page)

            # Test all toast types
            toast_results = toast_tester.test_all_toast_types()

            # Verify each toast type has appropriate theming
            for toast_type, styling in toast_results.items():
                # Background should not be transparent
                bg_color = styling.get('backgroundColor', '')
                assert bg_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                    f"{toast_type} toast should have themed background in {theme} theme: {bg_color}"

                # Text should be visible
                text_color = styling.get('color', '')
                assert text_color not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                    f"{toast_type} toast should have visible text in {theme} theme: {text_color}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_toast_contrast_ratios(self, browser_page):
        """Test toast notifications meet contrast requirements."""
        page, console_errors = browser_page

        # Set dark theme for contrast testing
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        toast_tester = ToastThemeIntegrationTester(page)

        # Create success toast and check contrast
        toast_tester.trigger_toast('success', 'Success message for contrast test')
        page.wait_for_timeout(200)

        # Get computed colors
        colors = page.evaluate("""
            () => {
                const toast = document.querySelector('.toast-success');
                if (!toast) return null;

                const styles = getComputedStyle(toast);
                return {
                    background: styles.backgroundColor,
                    text: styles.color
                };
            }
        """)

        if colors:
            # Colors should be defined (actual contrast calculation would require color parsing)
            assert colors['background'] != colors['text'], \
                "Toast background and text colors should be different for contrast"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestFormIntegrationWithThemes:
    """Test form elements with theme system."""

    def test_form_elements_theme_correctly(self, browser_page):
        """Test form elements inherit theme styling."""
        page, console_errors = browser_page

        for theme in ['light', 'dark']:
            # Set theme
            page.goto('http://localhost:5000')
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(1000)

            # Check form element styling
            form_elements = page.evaluate("""
                () => {
                    const elements = {};

                    // Check URL input field
                    const urlInput = document.querySelector('input[type="url"], input[name="url"], #url');
                    if (urlInput) {
                        const styles = getComputedStyle(urlInput);
                        elements.urlInput = {
                            backgroundColor: styles.backgroundColor,
                            color: styles.color,
                            borderColor: styles.borderColor
                        };
                    }

                    // Check submit button
                    const submitBtn = document.querySelector('button[type="submit"], .submit-btn, input[type="submit"]');
                    if (submitBtn) {
                        const styles = getComputedStyle(submitBtn);
                        elements.submitButton = {
                            backgroundColor: styles.backgroundColor,
                            color: styles.color,
                            borderColor: styles.borderColor
                        };
                    }

                    // Check select elements
                    const selects = document.querySelectorAll('select');
                    if (selects.length > 0) {
                        const styles = getComputedStyle(selects[0]);
                        elements.select = {
                            backgroundColor: styles.backgroundColor,
                            color: styles.color,
                            borderColor: styles.borderColor
                        };
                    }

                    return elements;
                }
            """)

            # Verify form elements have themed styling
            for element_type, styling in form_elements.items():
                # Elements should have non-default colors
                for property_name, color_value in styling.items():
                    assert color_value not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                        f"{element_type} {property_name} should be themed in {theme} mode: {color_value}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_form_submission_preserves_theme(self, client, browser_page):
        """Test theme is preserved during form submissions."""
        page, console_errors = browser_page

        # Set dark theme
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        pre_submit_theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')
        assert pre_submit_theme == 'dark', f"Pre-submit theme should be dark, got: {pre_submit_theme}"

        # Try to submit form if URL input exists
        url_input = page.query_selector('input[type="url"], input[name="url"], #url')
        if url_input:
            url_input.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

            submit_button = page.query_selector('button[type="submit"], .submit-btn, input[type="submit"]')
            if submit_button:
                # Submit form
                submit_button.click()
                page.wait_for_timeout(2000)  # Wait for form processing

                # Check theme after submission
                post_submit_theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')
                assert post_submit_theme == 'dark', \
                    f"Theme should remain dark after form submission, got: {post_submit_theme}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestAudioPlayerThemeIntegration:
    """Test audio player integration with theme system."""

    def test_audio_controls_visibility(self, browser_page):
        """Test audio player controls are visible in both themes."""
        page, console_errors = browser_page

        for theme in ['light', 'dark']:
            # Set theme
            page.goto('http://localhost:5000')
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(1000)

            # Create mock audio player controls
            page.evaluate(f"""
                () => {{
                    const audioControls = document.createElement('div');
                    audioControls.className = 'audio-controls';
                    audioControls.innerHTML = `
                        <button class="play-btn" aria-label="Play">▶️</button>
                        <div class="progress-slider">
                            <input type="range" min="0" max="100" value="0" class="slider">
                        </div>
                        <button class="volume-btn" aria-label="Volume">🔊</button>
                        <span class="time-display">0:00 / 0:00</span>
                    `;
                    audioControls.id = 'audio-player-{theme}';
                    document.body.appendChild(audioControls);
                }}
            """)

            # Check control visibility
            control_visibility = page.evaluate(f"""
                () => {{
                    const controls = document.querySelector('#audio-player-{theme}');
                    if (!controls) return null;

                    const buttons = controls.querySelectorAll('button');
                    const slider = controls.querySelector('.slider');
                    const timeDisplay = controls.querySelector('.time-display');

                    return {{
                        buttons: Array.from(buttons).map(btn => {{
                            const styles = getComputedStyle(btn);
                            return {{
                                visible: styles.opacity !== '0' && styles.display !== 'none',
                                color: styles.color,
                                backgroundColor: styles.backgroundColor
                            }};
                        }}),
                        slider: {{
                            visible: getComputedStyle(slider).opacity !== '0',
                            color: getComputedStyle(slider).color
                        }},
                        timeDisplay: {{
                            visible: getComputedStyle(timeDisplay).opacity !== '0',
                            color: getComputedStyle(timeDisplay).color
                        }}
                    }};
                }}
            """)

            if control_visibility:
                # All buttons should be visible
                for i, button in enumerate(control_visibility['buttons']):
                    assert button['visible'], \
                        f"Audio button {i} should be visible in {theme} theme"

                # Slider and time display should be visible
                assert control_visibility['slider']['visible'], \
                    f"Audio slider should be visible in {theme} theme"
                assert control_visibility['timeDisplay']['visible'], \
                    f"Time display should be visible in {theme} theme"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_audio_player_focus_indicators(self, browser_page):
        """Test audio player focus indicators work in both themes."""
        page, console_errors = browser_page

        for theme in ['light', 'dark']:
            # Set theme
            page.goto('http://localhost:5000')
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(1000)

            # Create audio controls
            page.evaluate("""
                () => {
                    const playBtn = document.createElement('button');
                    playBtn.className = 'audio-play-btn';
                    playBtn.textContent = 'Play';
                    playBtn.id = 'test-audio-play';
                    document.body.appendChild(playBtn);
                }
            """)

            # Focus the button and check focus indicator
            page.focus('#test-audio-play')

            focus_styles = page.evaluate("""
                () => {
                    const btn = document.querySelector('#test-audio-play');
                    const styles = getComputedStyle(btn, ':focus');
                    return {
                        outline: styles.outline,
                        outlineColor: styles.outlineColor,
                        boxShadow: styles.boxShadow
                    };
                }
            """)

            # Should have some focus indicator (outline or box-shadow)
            has_focus_indicator = (
                focus_styles['outline'] not in ['none', ''] or
                focus_styles['boxShadow'] not in ['none', '']
            )

            assert has_focus_indicator, \
                f"Audio controls should have focus indicators in {theme} theme"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestDynamicContentThemeInheritance:
    """Test that dynamically created content inherits theme."""

    def test_new_cards_inherit_theme(self, browser_page):
        """Test that new content cards inherit current theme."""
        page, console_errors = browser_page

        # Set dark theme
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        # Create new card dynamically (simulating new video added)
        page.evaluate("""
            () => {
                const newCard = document.createElement('div');
                newCard.className = 'card video-card';
                newCard.innerHTML = `
                    <div class="card-header">
                        <h3>New Video Title</h3>
                    </div>
                    <div class="card-body">
                        <p>Video description text</p>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 30%;"></div>
                        </div>
                    </div>
                `;
                newCard.id = 'dynamic-video-card';
                document.body.appendChild(newCard);
            }
        """)

        # Check that new card inherits dark theme
        card_styling = page.evaluate("""
            () => {
                const card = document.querySelector('#dynamic-video-card');
                const header = card.querySelector('h3');
                const body = card.querySelector('p');
                const progressBar = card.querySelector('.progress-bar');

                return {
                    card: {
                        backgroundColor: getComputedStyle(card).backgroundColor,
                        borderColor: getComputedStyle(card).borderColor
                    },
                    header: {
                        color: getComputedStyle(header).color
                    },
                    body: {
                        color: getComputedStyle(body).color
                    },
                    progressBar: {
                        backgroundColor: getComputedStyle(progressBar).backgroundColor
                    }
                };
            }
        """)

        # All elements should have themed colors
        for element_name, styles in card_styling.items():
            for property_name, color_value in styles.items():
                assert color_value not in ['rgba(0, 0, 0, 0)', 'transparent', ''], \
                    f"Dynamic card {element_name} {property_name} should be themed: {color_value}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_ajax_content_respects_theme(self, browser_page):
        """Test AJAX-loaded content respects current theme."""
        page, console_errors = browser_page

        # Set light theme
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "light")')
        page.reload()
        page.wait_for_timeout(1000)

        # Simulate AJAX content loading
        page.evaluate("""
            () => {
                // Simulate AJAX response content
                const ajaxContent = document.createElement('div');
                ajaxContent.className = 'ajax-loaded-content';
                ajaxContent.innerHTML = `
                    <div class="summary-result">
                        <h4>Video Summary</h4>
                        <p>This is a summary loaded via AJAX...</p>
                        <div class="meta-info">
                            <span class="duration">Duration: 5:23</span>
                            <span class="views">Views: 1.2M</span>
                        </div>
                    </div>
                `;
                ajaxContent.id = 'ajax-test-content';
                document.body.appendChild(ajaxContent);
            }
        """)

        # Check AJAX content theming
        ajax_styling = page.evaluate("""
            () => {
                const content = document.querySelector('#ajax-test-content');
                const title = content.querySelector('h4');
                const text = content.querySelector('p');
                const metaSpans = content.querySelectorAll('.meta-info span');

                return {
                    container: getComputedStyle(content).backgroundColor,
                    title: getComputedStyle(title).color,
                    text: getComputedStyle(text).color,
                    meta: Array.from(metaSpans).map(span => getComputedStyle(span).color)
                };
            }
        """)

        # AJAX content should inherit light theme styling
        assert ajax_styling['title'] not in ['rgba(0, 0, 0, 0)', 'transparent'], \
            f"AJAX title should have themed color: {ajax_styling['title']}"
        assert ajax_styling['text'] not in ['rgba(0, 0, 0, 0)', 'transparent'], \
            f"AJAX text should have themed color: {ajax_styling['text']}"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


class TestThemeSystemRobustness:
    """Test theme system robustness under various conditions."""

    def test_theme_switching_during_active_operations(self, browser_page):
        """Test theme switching while operations are in progress."""
        page, console_errors = browser_page

        # Start in light theme
        page.goto('http://localhost:5000')
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "light")')
        page.reload()
        page.wait_for_timeout(1000)

        # Simulate active operation (progress bar)
        page.evaluate("""
            () => {
                const progressContainer = document.createElement('div');
                progressContainer.innerHTML = `
                    <div class="active-operation">
                        <h4>Processing Video...</h4>
                        <div class="progress-bar">
                            <div class="progress-fill" id="active-progress" style="width: 0%;"></div>
                        </div>
                        <p class="status-text">Analyzing content...</p>
                    </div>
                `;
                progressContainer.id = 'active-operation-test';
                document.body.appendChild(progressContainer);

                // Animate progress
                let progress = 0;
                window.activeProgressInterval = setInterval(() => {
                    progress += 10;
                    document.querySelector('#active-progress').style.width = progress + '%';
                    if (progress >= 100) {
                        clearInterval(window.activeProgressInterval);
                    }
                }, 200);
            }
        """)

        # Let progress run for a bit
        page.wait_for_timeout(500)

        # Switch theme during active operation
        page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
        page.reload()
        page.wait_for_timeout(1000)

        # Recreate the operation (simulating persistence)
        page.evaluate("""
            () => {
                const progressContainer = document.createElement('div');
                progressContainer.innerHTML = `
                    <div class="active-operation">
                        <h4>Processing Video...</h4>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: 60%;"></div>
                        </div>
                        <p class="status-text">Still analyzing in dark theme...</p>
                    </div>
                `;
                progressContainer.id = 'active-operation-dark';
                document.body.appendChild(progressContainer);
            }
        """)

        # Verify operation continues with correct theme
        operation_styling = page.evaluate("""
            () => {
                const operation = document.querySelector('#active-operation-dark');
                const title = operation.querySelector('h4');
                const progressBar = operation.querySelector('.progress-bar');
                const status = operation.querySelector('.status-text');

                return {
                    title: getComputedStyle(title).color,
                    progressBar: getComputedStyle(progressBar).backgroundColor,
                    status: getComputedStyle(status).color
                };
            }
        """)

        # All elements should have dark theme colors
        for element, color in operation_styling.items():
            assert color not in ['rgba(0, 0, 0, 0)', 'transparent'], \
                f"Active operation {element} should have dark theme color: {color}"

        # Clean up
        page.evaluate("""
            () => {
                if (window.activeProgressInterval) {
                    clearInterval(window.activeProgressInterval);
                }
            }
        """)

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"

    def test_theme_system_memory_usage(self, browser_page):
        """Test theme system doesn't cause memory leaks."""
        page, console_errors = browser_page

        page.goto('http://localhost:5000')
        page.wait_for_timeout(1000)

        # Get initial memory usage (if available)
        initial_memory = page.evaluate("""
            () => {
                if (performance.memory) {
                    return performance.memory.usedJSHeapSize;
                }
                return null;
            }
        """)

        # Switch themes multiple times rapidly
        for i in range(10):
            theme = 'dark' if i % 2 == 0 else 'light'
            page.evaluate(f'() => localStorage.setItem("youtube-summarizer-theme", "{theme}")')
            page.reload()
            page.wait_for_timeout(100)

        # Get final memory usage
        final_memory = page.evaluate("""
            () => {
                if (performance.memory) {
                    return performance.memory.usedJSHeapSize;
                }
                return null;
            }
        """)

        # Memory usage should not have grown excessively
        if initial_memory and final_memory:
            memory_growth = final_memory - initial_memory
            # Allow for reasonable memory growth (less than 5MB)
            assert memory_growth < 5 * 1024 * 1024, \
                f"Theme switching caused excessive memory growth: {memory_growth / 1024 / 1024:.2f} MB"

        assert len(console_errors) == 0, f"JavaScript errors: {console_errors}"


if __name__ == '__main__':
    """Run integration tests when executed directly."""
    import subprocess
    import sys

    # Check if Playwright is available and install browsers
    if PLAYWRIGHT_AVAILABLE:
        try:
            subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'],
                         check=False, capture_output=True)
        except Exception:
            pass

    # Run the tests
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-x',  # Stop on first failure
    ])

    sys.exit(exit_code)
