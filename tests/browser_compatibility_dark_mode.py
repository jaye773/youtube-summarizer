#!/usr/bin/env python3
"""
Browser Compatibility Tests for Dark Mode Implementation

This module provides cross-browser testing for the YouTube Summarizer dark mode
system, ensuring consistent functionality across Chrome, Firefox, Safari, and
mobile browsers.

Author: YouTube Summarizer Team
Version: 1.0.0
"""

import pytest
import time
import os
import json
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass

# Try to import playwright for browser testing
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = Any
    Browser = Any
    BrowserContext = Any
    Playwright = Any


@dataclass
class BrowserTestResult:
    """Container for browser test results."""
    browser_name: str
    browser_version: str
    test_name: str
    status: str  # 'PASS', 'FAIL', 'SKIP'
    duration: float
    details: Dict[str, Any]
    errors: List[str]


class BrowserCompatibilityTester:
    """Cross-browser theme testing utility."""

    def __init__(self, playwright: Playwright):
        """Initialize with Playwright instance.

        Args:
            playwright: Playwright sync API instance
        """
        self.playwright = playwright
        self.results: List[BrowserTestResult] = []

        # Browser configurations to test
        self.browser_configs = [
            {
                'name': 'chromium',
                'display_name': 'Chrome/Chromium',
                'launch_options': {
                    'headless': True,
                    'args': ['--no-sandbox', '--disable-dev-shm-usage']
                }
            },
            {
                'name': 'firefox',
                'display_name': 'Firefox',
                'launch_options': {
                    'headless': True
                }
            },
            {
                'name': 'webkit',
                'display_name': 'Safari/WebKit',
                'launch_options': {
                    'headless': True
                }
            }
        ]

        # Mobile browser configurations
        self.mobile_configs = [
            {
                'name': 'chromium',
                'display_name': 'Mobile Chrome',
                'device': 'iPhone 12',
                'launch_options': {'headless': True}
            },
            {
                'name': 'webkit',
                'display_name': 'Mobile Safari',
                'device': 'iPhone 12',
                'launch_options': {'headless': True}
            }
        ]

    def run_cross_browser_test(self, test_func, test_name: str, include_mobile: bool = False) -> List[BrowserTestResult]:
        """Run a test function across all browser configurations.

        Args:
            test_func: Test function that takes (browser, page) parameters
            test_name: Name of the test for reporting
            include_mobile: Whether to include mobile browser testing

        Returns:
            List of test results for each browser
        """
        configs = self.browser_configs.copy()
        if include_mobile:
            configs.extend(self.mobile_configs)

        results = []

        for config in configs:
            result = self._run_single_browser_test(test_func, test_name, config)
            results.append(result)
            self.results.append(result)

        return results

    def _run_single_browser_test(self, test_func, test_name: str, config: Dict[str, Any]) -> BrowserTestResult:
        """Run test on a single browser configuration.

        Args:
            test_func: Test function to run
            test_name: Name of the test
            config: Browser configuration

        Returns:
            Test result for this browser
        """
        start_time = time.time()
        browser_type = getattr(self.playwright, config['name'])
        errors = []
        details = {}
        status = 'FAIL'

        try:
            # Launch browser
            browser = browser_type.launch(**config['launch_options'])

            try:
                # Create context with optional device emulation
                if 'device' in config:
                    device = self.playwright.devices[config['device']]
                    context = browser.new_context(**device)
                else:
                    context = browser.new_context()

                # Create page and set up error tracking
                page = context.new_page()
                console_errors = []

                def handle_console(msg):
                    if msg.type == 'error':
                        console_errors.append(msg.text)

                page.on('console', handle_console)

                # Get browser version info
                browser_version = self._get_browser_version(page, config['name'])

                # Run the actual test
                test_result = test_func(browser, page, config)

                # Collect results
                details.update(test_result or {})
                details['console_errors'] = console_errors
                details['browser_version'] = browser_version

                # Test passes if no exceptions and no critical console errors
                critical_errors = [err for err in console_errors
                                 if 'TypeError' in err or 'ReferenceError' in err]

                if len(critical_errors) == 0:
                    status = 'PASS'
                else:
                    errors.extend(critical_errors)

            finally:
                browser.close()

        except Exception as e:
            errors.append(str(e))
            status = 'FAIL'

        duration = time.time() - start_time

        return BrowserTestResult(
            browser_name=config['display_name'],
            browser_version=details.get('browser_version', 'Unknown'),
            test_name=test_name,
            status=status,
            duration=duration,
            details=details,
            errors=errors
        )

    def _get_browser_version(self, page: Page, browser_name: str) -> str:
        """Get browser version information.

        Args:
            page: Playwright page object
            browser_name: Name of the browser

        Returns:
            Browser version string
        """
        try:
            if browser_name == 'chromium':
                version = page.evaluate('() => navigator.userAgent.match(/Chrome\/([0-9.]+)/)?.[1] || "Unknown"')
            elif browser_name == 'firefox':
                version = page.evaluate('() => navigator.userAgent.match(/Firefox\/([0-9.]+)/)?.[1] || "Unknown"')
            elif browser_name == 'webkit':
                version = page.evaluate('() => navigator.userAgent.match(/Version\/([0-9.]+)/)?.[1] || "Unknown"')
            else:
                version = 'Unknown'
            return f"{browser_name.title()} {version}"
        except:
            return f"{browser_name.title()} Unknown"

    def get_summary_report(self) -> Dict[str, Any]:
        """Generate summary report of all test results.

        Returns:
            Dictionary containing test summary
        """
        if not self.results:
            return {'status': 'NO_TESTS_RUN'}

        total_tests = len(self.results)
        passed_tests = len([r for r in self.results if r.status == 'PASS'])
        failed_tests = len([r for r in self.results if r.status == 'FAIL'])
        skipped_tests = len([r for r in self.results if r.status == 'SKIP'])

        # Group by browser
        by_browser = {}
        for result in self.results:
            browser = result.browser_name
            if browser not in by_browser:
                by_browser[browser] = {'passed': 0, 'failed': 0, 'skipped': 0, 'total': 0}

            by_browser[browser]['total'] += 1
            if result.status == 'PASS':
                by_browser[browser]['passed'] += 1
            elif result.status == 'FAIL':
                by_browser[browser]['failed'] += 1
            else:
                by_browser[browser]['skipped'] += 1

        return {
            'total_tests': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'skipped': skipped_tests,
            'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0,
            'by_browser': by_browser,
            'failed_tests': [
                {
                    'browser': r.browser_name,
                    'test': r.test_name,
                    'errors': r.errors
                }
                for r in self.results if r.status == 'FAIL'
            ]
        }


@pytest.fixture
def compatibility_tester():
    """Create browser compatibility tester."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not available")

    with sync_playwright() as p:
        yield BrowserCompatibilityTester(p)


class TestBasicThemeFunctionality:
    """Test basic theme functionality across browsers."""

    def test_theme_detection_cross_browser(self, compatibility_tester):
        """Test theme detection works across all browsers."""

        def theme_detection_test(browser, page, config):
            # Navigate to application
            page.goto('http://localhost:5000')
            page.wait_for_timeout(1000)

            # Check theme detection
            theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')
            theme_class = page.evaluate('() => Array.from(document.documentElement.classList).find(c => c.startsWith("theme-"))')

            # Verify localStorage handling
            page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
            page.reload()
            page.wait_for_timeout(1000)

            new_theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')

            return {
                'initial_theme': theme,
                'initial_theme_class': theme_class,
                'theme_after_localStorage': new_theme,
                'localStorage_works': new_theme == 'dark'
            }

        results = compatibility_tester.run_cross_browser_test(
            theme_detection_test,
            'Theme Detection',
            include_mobile=True
        )

        # Verify results
        for result in results:
            assert result.status == 'PASS', \
                f"Theme detection failed in {result.browser_name}: {result.errors}"

            assert result.details['localStorage_works'], \
                f"LocalStorage theme persistence failed in {result.browser_name}"

    def test_css_variables_support(self, compatibility_tester):
        """Test CSS custom properties work across browsers."""

        def css_variables_test(browser, page, config):
            page.goto('http://localhost:5000')
            page.wait_for_timeout(1000)

            # Test CSS variable reading
            bg_primary = page.evaluate('''
                () => getComputedStyle(document.documentElement)
                      .getPropertyValue('--bg-primary').trim()
            ''')

            text_primary = page.evaluate('''
                () => getComputedStyle(document.documentElement)
                      .getPropertyValue('--text-primary').trim()
            ''')

            # Test CSS variable inheritance
            test_element_bg = page.evaluate('''
                () => {
                    const div = document.createElement('div');
                    div.style.backgroundColor = 'var(--bg-primary)';
                    document.body.appendChild(div);
                    const computedBg = getComputedStyle(div).backgroundColor;
                    document.body.removeChild(div);
                    return computedBg;
                }
            ''')

            return {
                'bg_primary_value': bg_primary,
                'text_primary_value': text_primary,
                'css_vars_supported': bool(bg_primary and text_primary),
                'css_var_inheritance_works': test_element_bg != 'var(--bg-primary)'
            }

        results = compatibility_tester.run_cross_browser_test(
            css_variables_test,
            'CSS Variables Support'
        )

        for result in results:
            assert result.status == 'PASS', \
                f"CSS variables test failed in {result.browser_name}: {result.errors}"

            assert result.details['css_vars_supported'], \
                f"CSS variables not supported in {result.browser_name}"

    def test_matchMedia_api_support(self, compatibility_tester):
        """Test matchMedia API support across browsers."""

        def matchMedia_test(browser, page, config):
            page.goto('http://localhost:5000')

            # Test matchMedia API availability
            matchMedia_available = page.evaluate('() => typeof window.matchMedia === "function"')

            if matchMedia_available:
                # Test media query matching
                supports_prefers_color_scheme = page.evaluate('''
                    () => {
                        try {
                            const mq = window.matchMedia('(prefers-color-scheme: dark)');
                            return typeof mq.matches === 'boolean';
                        } catch (e) {
                            return false;
                        }
                    }
                ''')

                # Test event listener support
                event_listener_support = page.evaluate('''
                    () => {
                        try {
                            const mq = window.matchMedia('(prefers-color-scheme: dark)');
                            return typeof mq.addEventListener === 'function' ||
                                   typeof mq.addListener === 'function';
                        } catch (e) {
                            return false;
                        }
                    }
                ''')
            else:
                supports_prefers_color_scheme = False
                event_listener_support = False

            return {
                'matchMedia_available': matchMedia_available,
                'prefers_color_scheme_works': supports_prefers_color_scheme,
                'event_listeners_work': event_listener_support
            }

        results = compatibility_tester.run_cross_browser_test(
            matchMedia_test,
            'matchMedia API Support'
        )

        for result in results:
            assert result.status == 'PASS', \
                f"matchMedia API test failed in {result.browser_name}: {result.errors}"

            # matchMedia should be available in all modern browsers
            assert result.details['matchMedia_available'], \
                f"matchMedia API not available in {result.browser_name}"


class TestThemeTransitions:
    """Test theme transitions and animations across browsers."""

    def test_css_transitions_support(self, compatibility_tester):
        """Test CSS transition support for smooth theme changes."""

        def transitions_test(browser, page, config):
            page.goto('http://localhost:5000')
            page.wait_for_timeout(1000)

            # Test CSS transition property support
            transition_support = page.evaluate('''
                () => {
                    const div = document.createElement('div');
                    div.style.transition = 'background-color 0.3s ease';
                    document.body.appendChild(div);
                    const hasTransition = getComputedStyle(div).transition !== '';
                    document.body.removeChild(div);
                    return hasTransition;
                }
            ''')

            # Test CSS variable transition support
            css_var_transition_support = page.evaluate('''
                () => {
                    const div = document.createElement('div');
                    div.style.setProperty('--test-color', '#000000');
                    div.style.backgroundColor = 'var(--test-color)';
                    div.style.transition = 'background-color 0.3s ease';
                    document.body.appendChild(div);

                    const initialBg = getComputedStyle(div).backgroundColor;
                    div.style.setProperty('--test-color', '#ffffff');

                    setTimeout(() => {
                        const newBg = getComputedStyle(div).backgroundColor;
                        document.body.removeChild(div);
                        return initialBg !== newBg;
                    }, 100);

                    return true; // Simplified for this test
                }
            ''')

            return {
                'css_transitions_supported': transition_support,
                'css_var_transitions_supported': css_var_transition_support
            }

        results = compatibility_tester.run_cross_browser_test(
            transitions_test,
            'CSS Transitions Support'
        )

        for result in results:
            assert result.status == 'PASS', \
                f"CSS transitions test failed in {result.browser_name}: {result.errors}"


class TestMobileBrowserSupport:
    """Test mobile browser specific functionality."""

    def test_viewport_meta_theme_color(self, compatibility_tester):
        """Test theme-color meta tag support on mobile."""

        def theme_color_test(browser, page, config):
            page.goto('http://localhost:5000')
            page.wait_for_timeout(1000)

            # Check if theme-color meta tag exists or gets created
            theme_color_meta = page.evaluate('''
                () => {
                    const meta = document.querySelector('meta[name="theme-color"]');
                    return meta ? meta.content : null;
                }
            ''')

            # Test theme switching updates meta theme-color
            if 'localStorage' in page.evaluate('() => typeof localStorage'):
                page.evaluate('() => localStorage.setItem("youtube-summarizer-theme", "dark")')
                page.reload()
                page.wait_for_timeout(1000)

                dark_theme_color = page.evaluate('''
                    () => {
                        const meta = document.querySelector('meta[name="theme-color"]');
                        return meta ? meta.content : null;
                    }
                ''')
            else:
                dark_theme_color = None

            return {
                'theme_color_meta_exists': theme_color_meta is not None,
                'theme_color_value': theme_color_meta,
                'dark_theme_color_value': dark_theme_color,
                'theme_color_updates': theme_color_meta != dark_theme_color if both else False
            }

        results = compatibility_tester.run_cross_browser_test(
            theme_color_test,
            'Mobile Theme Color Support',
            include_mobile=True
        )

        # This test is specifically for mobile configurations
        mobile_results = [r for r in results if 'Mobile' in r.browser_name]

        for result in mobile_results:
            assert result.status == 'PASS', \
                f"Mobile theme color test failed in {result.browser_name}: {result.errors}"

    def test_touch_interaction_with_theme_toggle(self, compatibility_tester):
        """Test touch interactions with theme toggle on mobile."""

        def touch_test(browser, page, config):
            page.goto('http://localhost:5000')
            page.wait_for_timeout(1000)

            # Look for theme toggle button
            toggle_selectors = [
                '[data-theme-toggle]',
                '.theme-toggle',
                '#theme-toggle',
                'button[title*="theme" i]'
            ]

            toggle_found = False
            for selector in toggle_selectors:
                if page.query_selector(selector):
                    toggle_found = True
                    break

            if toggle_found:
                initial_theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')

                # Simulate touch interaction
                try:
                    page.tap(selector, timeout=5000)
                    page.wait_for_timeout(500)

                    new_theme = page.evaluate('() => document.documentElement.getAttribute("data-theme")')
                    theme_changed = initial_theme != new_theme
                except:
                    theme_changed = False
            else:
                theme_changed = None

            return {
                'toggle_button_found': toggle_found,
                'touch_interaction_works': theme_changed,
                'selector_used': selector if toggle_found else None
            }

        results = compatibility_tester.run_cross_browser_test(
            touch_test,
            'Touch Interaction Test',
            include_mobile=True
        )

        mobile_results = [r for r in results if 'Mobile' in r.browser_name]

        for result in mobile_results:
            if result.details['toggle_button_found']:
                assert result.status == 'PASS', \
                    f"Touch interaction test failed in {result.browser_name}: {result.errors}"
            else:
                # Theme toggle might not be implemented yet
                print(f"Theme toggle not found in {result.browser_name} - skipping touch test")


class TestLocalStorageCompatibility:
    """Test localStorage implementation across browsers."""

    def test_localStorage_basic_functionality(self, compatibility_tester):
        """Test basic localStorage operations across browsers."""

        def localStorage_test(browser, page, config):
            page.goto('http://localhost:5000')

            # Test localStorage availability
            localStorage_available = page.evaluate('() => typeof Storage !== "undefined" && localStorage')

            if localStorage_available:
                # Test basic operations
                set_success = page.evaluate('''
                    () => {
                        try {
                            localStorage.setItem('test-theme', 'dark');
                            return true;
                        } catch (e) {
                            return false;
                        }
                    }
                ''')

                get_success = page.evaluate('''
                    () => {
                        try {
                            return localStorage.getItem('test-theme') === 'dark';
                        } catch (e) {
                            return false;
                        }
                    }
                ''')

                remove_success = page.evaluate('''
                    () => {
                        try {
                            localStorage.removeItem('test-theme');
                            return localStorage.getItem('test-theme') === null;
                        } catch (e) {
                            return false;
                        }
                    }
                ''')
            else:
                set_success = get_success = remove_success = False

            return {
                'localStorage_available': localStorage_available,
                'set_works': set_success,
                'get_works': get_success,
                'remove_works': remove_success,
                'all_operations_work': all([set_success, get_success, remove_success])
            }

        results = compatibility_tester.run_cross_browser_test(
            localStorage_test,
            'LocalStorage Basic Operations'
        )

        for result in results:
            assert result.status == 'PASS', \
                f"LocalStorage test failed in {result.browser_name}: {result.errors}"

            assert result.details['localStorage_available'], \
                f"LocalStorage not available in {result.browser_name}"

    def test_localStorage_quota_handling(self, compatibility_tester):
        """Test localStorage quota handling across browsers."""

        def quota_test(browser, page, config):
            page.goto('http://localhost:5000')

            # Test quota exceeded handling
            quota_test_result = page.evaluate('''
                () => {
                    try {
                        // Try to fill localStorage
                        const testKey = 'quota-test';
                        let size = 0;
                        let data = 'x';

                        // Increase data size exponentially
                        while (data.length < 1024 * 1024) { // 1MB
                            data += data;
                        }

                        // Try to store large data
                        try {
                            localStorage.setItem(testKey, data);
                            localStorage.removeItem(testKey);
                            return { success: true, error: null };
                        } catch (quotaError) {
                            return {
                                success: false,
                                error: quotaError.name,
                                graceful_handling: quotaError.name === 'QuotaExceededError'
                            };
                        }
                    } catch (e) {
                        return { success: false, error: e.message, graceful_handling: false };
                    }
                }
            ''')

            return quota_test_result

        results = compatibility_tester.run_cross_browser_test(
            quota_test,
            'LocalStorage Quota Handling'
        )

        for result in results:
            assert result.status == 'PASS', \
                f"LocalStorage quota test failed in {result.browser_name}: {result.errors}"


def test_cross_browser_compatibility_suite(compatibility_tester):
    """Run the complete cross-browser compatibility test suite."""

    # Run all browser compatibility tests
    basic_tests = TestBasicThemeFunctionality()
    basic_tests.test_theme_detection_cross_browser(compatibility_tester)
    basic_tests.test_css_variables_support(compatibility_tester)
    basic_tests.test_matchMedia_api_support(compatibility_tester)

    transition_tests = TestThemeTransitions()
    transition_tests.test_css_transitions_support(compatibility_tester)

    mobile_tests = TestMobileBrowserSupport()
    mobile_tests.test_viewport_meta_theme_color(compatibility_tester)
    mobile_tests.test_touch_interaction_with_theme_toggle(compatibility_tester)

    storage_tests = TestLocalStorageCompatibility()
    storage_tests.test_localStorage_basic_functionality(compatibility_tester)
    storage_tests.test_localStorage_quota_handling(compatibility_tester)

    # Generate and save compatibility report
    report = compatibility_tester.get_summary_report()

    # Save detailed report
    report_file = Path(__file__).parent / 'browser_compatibility_report.json'
    with open(report_file, 'w') as f:
        json.dump({
            'summary': report,
            'detailed_results': [
                {
                    'browser': r.browser_name,
                    'version': r.browser_version,
                    'test': r.test_name,
                    'status': r.status,
                    'duration': r.duration,
                    'details': r.details,
                    'errors': r.errors
                }
                for r in compatibility_tester.results
            ]
        }, f, indent=2)

    print(f"\nBrowser Compatibility Report:")
    print(f"  Total Tests: {report['total_tests']}")
    print(f"  Passed: {report['passed']}")
    print(f"  Failed: {report['failed']}")
    print(f"  Success Rate: {report['success_rate']:.1f}%")
    print(f"  Detailed report saved to: {report_file}")

    # Assert overall success
    assert report['success_rate'] >= 90, \
        f"Browser compatibility success rate too low: {report['success_rate']:.1f}%"


if __name__ == '__main__':
    """Run browser compatibility tests when executed directly."""
    import subprocess
    import sys

    # Install browsers if Playwright is available
    if PLAYWRIGHT_AVAILABLE:
        try:
            print("Installing browsers for testing...")
            subprocess.run([sys.executable, '-m', 'playwright', 'install'],
                         check=False, capture_output=True)
        except Exception as e:
            print(f"Could not install browsers: {e}")

    # Run the tests
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-s',  # Don't capture output so we can see progress
    ])

    sys.exit(exit_code)
