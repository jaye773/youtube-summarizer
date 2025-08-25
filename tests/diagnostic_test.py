"""
Comprehensive diagnostic test for YouTube Summarizer instance
Tests the running application at http://192.168.50.56:8431/ for common issues
"""
import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext
import pytest


class DiagnosticTestRunner:
    def __init__(self, base_url: str = "http://192.168.50.56:8431"):
        self.base_url = base_url
        self.test_results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base_url,
            "tests": {}
        }
        self.console_logs = []
        self.network_logs = []
        self.errors = []

    async def run_comprehensive_diagnostics(self):
        """Run all diagnostic tests"""
        async with async_playwright() as p:
            # Use Chromium for better debugging capabilities
            browser = await p.chromium.launch(
                headless=False,  # Run in headed mode for visual debugging
                args=[
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--no-sandbox'
                ]
            )

            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )

            page = await context.new_page()

            # Set up logging
            await self._setup_logging(page)

            try:
                # Run diagnostic tests in sequence
                await self._test_basic_connectivity(page)
                await self._test_page_loading(page)
                await self._test_ui_elements(page)
                await self._test_console_errors(page)
                await self._test_network_requests(page)
                await self._test_authentication(page)
                await self._test_youtube_url_submission(page)
                await self._test_sse_connectivity(page)
                await self._test_javascript_functionality(page)
                await self._capture_screenshots(page)

            except Exception as e:
                self.errors.append(f"Critical test failure: {str(e)}")
                await self._capture_error_screenshot(page, "critical_failure")

            finally:
                await browser.close()

        # Generate comprehensive report
        await self._generate_diagnostic_report()

    async def _setup_logging(self, page: Page):
        """Set up comprehensive logging for diagnostics"""

        # Console log capture
        page.on("console", lambda msg: self.console_logs.append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location,
            "timestamp": datetime.now().isoformat()
        }))

        # Network request capture
        page.on("request", lambda req: self.network_logs.append({
            "type": "request",
            "url": req.url,
            "method": req.method,
            "headers": dict(req.headers),
            "timestamp": datetime.now().isoformat()
        }))

        page.on("response", lambda resp: self.network_logs.append({
            "type": "response",
            "url": resp.url,
            "status": resp.status,
            "headers": dict(resp.headers),
            "timestamp": datetime.now().isoformat()
        }))

        # Request failure capture
        page.on("requestfailed", lambda req: self.errors.append({
            "type": "network_failure",
            "url": req.url,
            "failure": req.failure,
            "timestamp": datetime.now().isoformat()
        }))

    async def _test_basic_connectivity(self, page: Page):
        """Test basic network connectivity to the instance"""
        test_name = "basic_connectivity"
        print(f"🔍 Testing basic connectivity to {self.base_url}")

        try:
            response = await page.goto(self.base_url, timeout=10000, wait_until="domcontentloaded")

            if response:
                status = response.status
                self.test_results["tests"][test_name] = {
                    "status": "pass" if status == 200 else "fail",
                    "http_status": status,
                    "url": response.url,
                    "headers": dict(response.headers)
                }
                print(f"✅ Basic connectivity: HTTP {status}")
            else:
                self.test_results["tests"][test_name] = {
                    "status": "fail",
                    "error": "No response received"
                }
                print("❌ Basic connectivity: No response")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Basic connectivity failed: {str(e)}")

    async def _test_page_loading(self, page: Page):
        """Test complete page loading with all resources"""
        test_name = "page_loading"
        print("🔍 Testing complete page loading")

        try:
            # Wait for page to fully load including network requests
            await page.wait_for_load_state("networkidle", timeout=15000)

            # Check if page title is present
            title = await page.title()

            # Check for critical elements that indicate successful load
            body_present = await page.locator("body").count() > 0

            self.test_results["tests"][test_name] = {
                "status": "pass" if body_present and title else "fail",
                "title": title,
                "body_present": body_present,
                "load_time": "completed"
            }
            print(f"✅ Page loading: Title='{title}', Body present={body_present}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Page loading failed: {str(e)}")

    async def _test_ui_elements(self, page: Page):
        """Test presence and functionality of critical UI elements"""
        test_name = "ui_elements"
        print("🔍 Testing UI elements presence and functionality")

        try:
            elements_to_check = {
                "url_input": "input[type='url'], input[name='url'], #url",
                "model_select": "select[name='model'], #model, .model-select",
                "submit_button": "button[type='submit'], input[type='submit'], .submit-btn",
                "progress_container": ".progress-container, #progress, .progress-bar",
                "status_indicator": ".status, #status, .connection-status"
            }

            element_results = {}

            for element_name, selector in elements_to_check.items():
                try:
                    element = page.locator(selector).first
                    is_visible = await element.is_visible() if await element.count() > 0 else False
                    is_enabled = await element.is_enabled() if await element.count() > 0 else False

                    element_results[element_name] = {
                        "present": await element.count() > 0,
                        "visible": is_visible,
                        "enabled": is_enabled,
                        "selector_used": selector
                    }

                except Exception as e:
                    element_results[element_name] = {
                        "present": False,
                        "error": str(e)
                    }

            # Test form interaction
            form_interactive = False
            try:
                url_input = page.locator("input[type='url'], input[name='url'], #url").first
                if await url_input.count() > 0:
                    await url_input.fill("https://www.youtube.com/watch?v=test")
                    form_interactive = True
            except:
                pass

            all_critical_present = all(
                result.get("present", False)
                for key, result in element_results.items()
                if key in ["url_input", "submit_button"]
            )

            self.test_results["tests"][test_name] = {
                "status": "pass" if all_critical_present else "fail",
                "elements": element_results,
                "form_interactive": form_interactive
            }

            print(f"✅ UI Elements: Critical elements present={all_critical_present}, Interactive={form_interactive}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ UI Elements test failed: {str(e)}")

    async def _test_console_errors(self, page: Page):
        """Analyze console errors and warnings"""
        test_name = "console_errors"
        print("🔍 Analyzing console errors and warnings")

        # Wait a bit to collect console messages
        await asyncio.sleep(2)

        errors = [log for log in self.console_logs if log["type"] == "error"]
        warnings = [log for log in self.console_logs if log["type"] == "warning"]

        critical_errors = []
        for error in errors:
            # Check for common critical errors
            error_text = error["text"].lower()
            if any(keyword in error_text for keyword in [
                "failed to load", "network error", "cors", "refused to connect",
                "script error", "uncaught", "syntax error"
            ]):
                critical_errors.append(error)

        self.test_results["tests"][test_name] = {
            "status": "fail" if critical_errors else "pass",
            "total_errors": len(errors),
            "total_warnings": len(warnings),
            "critical_errors": critical_errors,
            "all_console_logs": self.console_logs[-20:]  # Last 20 logs
        }

        print(f"✅ Console: {len(errors)} errors, {len(warnings)} warnings, {len(critical_errors)} critical")

    async def _test_network_requests(self, page: Page):
        """Test network requests for failures and issues"""
        test_name = "network_requests"
        print("🔍 Testing network requests and responses")

        failed_requests = [log for log in self.network_logs if log.get("type") == "response" and log.get("status", 200) >= 400]
        blocked_requests = [error for error in self.errors if error.get("type") == "network_failure"]

        # Check for CORS issues
        cors_issues = []
        for log in self.console_logs:
            if "cors" in log["text"].lower() or "cross-origin" in log["text"].lower():
                cors_issues.append(log)

        # Check for specific resource loading
        critical_resources = {
            "css": [log for log in self.network_logs if log.get("url", "").endswith(".css")],
            "js": [log for log in self.network_logs if log.get("url", "").endswith(".js")],
            "api": [log for log in self.network_logs if "/api/" in log.get("url", "") or "/sse" in log.get("url", "")]
        }

        self.test_results["tests"][test_name] = {
            "status": "fail" if failed_requests or blocked_requests or cors_issues else "pass",
            "failed_requests": failed_requests,
            "blocked_requests": blocked_requests,
            "cors_issues": cors_issues,
            "resource_loading": critical_resources,
            "total_requests": len([log for log in self.network_logs if log.get("type") == "request"])
        }

        print(f"✅ Network: {len(failed_requests)} failed, {len(blocked_requests)} blocked, {len(cors_issues)} CORS issues")

    async def _test_authentication(self, page: Page):
        """Test authentication if login is required"""
        test_name = "authentication"
        print("🔍 Testing authentication requirements")

        try:
            # Check if login form is present
            login_form = page.locator("form[action*='login'], .login-form, #login-form")
            login_required = await login_form.count() > 0

            # Check if redirected to login
            current_url = page.url
            is_login_page = "login" in current_url.lower()

            # Check for authentication-related elements
            auth_elements = {
                "username_field": await page.locator("input[name='username'], input[type='text'][name*='user']").count() > 0,
                "password_field": await page.locator("input[type='password']").count() > 0,
                "login_button": await page.locator("button[type='submit'], input[value*='Login']").count() > 0
            }

            self.test_results["tests"][test_name] = {
                "status": "info",  # This is informational, not pass/fail
                "login_required": login_required,
                "is_login_page": is_login_page,
                "current_url": current_url,
                "auth_elements": auth_elements
            }

            print(f"ℹ️ Authentication: Required={login_required}, Login page={is_login_page}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }

    async def _test_youtube_url_submission(self, page: Page):
        """Test YouTube URL submission functionality"""
        test_name = "youtube_submission"
        print("🔍 Testing YouTube URL submission")

        try:
            # Find URL input field
            url_input = page.locator("input[type='url'], input[name='url'], #url").first
            submit_button = page.locator("button[type='submit'], input[type='submit'], .submit-btn").first

            if await url_input.count() == 0 or await submit_button.count() == 0:
                self.test_results["tests"][test_name] = {
                    "status": "fail",
                    "error": "Required form elements not found",
                    "url_input_present": await url_input.count() > 0,
                    "submit_button_present": await submit_button.count() > 0
                }
                return

            # Test with a sample YouTube URL
            test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

            # Clear and fill the input
            await url_input.fill("")
            await url_input.fill(test_url)

            # Check if input accepts the value
            input_value = await url_input.input_value()

            # Capture network activity before submission
            initial_request_count = len(self.network_logs)

            # Try to submit (but don't actually process to avoid API usage)
            # We'll check if the form accepts submission
            is_form_submittable = await submit_button.is_enabled()

            self.test_results["tests"][test_name] = {
                "status": "pass" if input_value == test_url and is_form_submittable else "fail",
                "input_accepts_url": input_value == test_url,
                "form_submittable": is_form_submittable,
                "test_url": test_url,
                "actual_input_value": input_value
            }

            print(f"✅ URL Submission: Input works={input_value == test_url}, Submittable={is_form_submittable}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ URL Submission failed: {str(e)}")

    async def _test_sse_connectivity(self, page: Page):
        """Test Server-Sent Events connectivity"""
        test_name = "sse_connectivity"
        print("🔍 Testing SSE connectivity")

        try:
            # Inject JavaScript to test SSE connection
            sse_test_result = await page.evaluate("""
                new Promise((resolve) => {
                    try {
                        const eventSource = new EventSource('/sse');
                        let connected = false;
                        let error = null;

                        const timeout = setTimeout(() => {
                            if (!connected) {
                                eventSource.close();
                                resolve({
                                    connected: false,
                                    error: 'Connection timeout',
                                    readyState: eventSource.readyState
                                });
                            }
                        }, 5000);

                        eventSource.onopen = function(e) {
                            connected = true;
                            clearTimeout(timeout);
                            eventSource.close();
                            resolve({
                                connected: true,
                                readyState: eventSource.readyState,
                                url: eventSource.url
                            });
                        };

                        eventSource.onerror = function(e) {
                            error = e;
                            clearTimeout(timeout);
                            eventSource.close();
                            resolve({
                                connected: false,
                                error: 'SSE connection error',
                                readyState: eventSource.readyState,
                                url: eventSource.url
                            });
                        };

                    } catch (e) {
                        resolve({
                            connected: false,
                            error: e.message,
                            browserSupport: false
                        });
                    }
                })
            """)

            # Check if SSE endpoint exists in network logs
            sse_requests = [log for log in self.network_logs if "/sse" in log.get("url", "")]

            self.test_results["tests"][test_name] = {
                "status": "pass" if sse_test_result.get("connected") else "fail",
                "connection_result": sse_test_result,
                "sse_endpoint_accessible": len(sse_requests) > 0,
                "sse_requests": sse_requests
            }

            print(f"✅ SSE: Connected={sse_test_result.get('connected')}, Endpoint accessible={len(sse_requests) > 0}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ SSE test failed: {str(e)}")

    async def _test_javascript_functionality(self, page: Page):
        """Test JavaScript functionality and errors"""
        test_name = "javascript_functionality"
        print("🔍 Testing JavaScript functionality")

        try:
            # Test basic JavaScript execution
            js_basic = await page.evaluate("() => typeof window !== 'undefined' && typeof document !== 'undefined'")

            # Test jQuery if present
            jquery_present = await page.evaluate("() => typeof $ !== 'undefined' || typeof jQuery !== 'undefined'")

            # Test specific YouTube Summarizer JS functions if present
            custom_js_functions = await page.evaluate("""
                () => {
                    return {
                        sse_client: typeof SSEClient !== 'undefined',
                        job_tracker: typeof JobTracker !== 'undefined',
                        ui_updater: typeof UIUpdater !== 'undefined',
                        event_listeners: document.querySelectorAll('[onclick], [onsubmit]').length > 0
                    };
                }
            """)

            # Check for JavaScript errors in console logs
            js_errors = [log for log in self.console_logs if log["type"] == "error" and
                        any(keyword in log["text"].lower() for keyword in ["javascript", "script", "function", "undefined"])]

            self.test_results["tests"][test_name] = {
                "status": "pass" if js_basic and not js_errors else "fail",
                "basic_js_working": js_basic,
                "jquery_present": jquery_present,
                "custom_functions": custom_js_functions,
                "js_errors": js_errors
            }

            print(f"✅ JavaScript: Basic={js_basic}, Custom functions={custom_js_functions}, Errors={len(js_errors)}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ JavaScript test failed: {str(e)}")

    async def _capture_screenshots(self, page: Page):
        """Capture screenshots for visual debugging"""
        test_name = "screenshots"
        print("🔍 Capturing screenshots for visual debugging")

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Full page screenshot
            full_screenshot = f"/Users/jaye/projects/youtube-summarizer/diagnostic_full_{timestamp}.png"
            await page.screenshot(path=full_screenshot, full_page=True)

            # Viewport screenshot
            viewport_screenshot = f"/Users/jaye/projects/youtube-summarizer/diagnostic_viewport_{timestamp}.png"
            await page.screenshot(path=viewport_screenshot)

            self.test_results["tests"][test_name] = {
                "status": "pass",
                "full_screenshot": full_screenshot,
                "viewport_screenshot": viewport_screenshot
            }

            print(f"✅ Screenshots captured: {full_screenshot}, {viewport_screenshot}")

        except Exception as e:
            self.test_results["tests"][test_name] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Screenshot capture failed: {str(e)}")

    async def _capture_error_screenshot(self, page: Page, error_type: str):
        """Capture screenshot when critical error occurs"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            error_screenshot = f"/Users/jaye/projects/youtube-summarizer/diagnostic_error_{error_type}_{timestamp}.png"
            await page.screenshot(path=error_screenshot)
            print(f"🚨 Error screenshot captured: {error_screenshot}")
        except:
            pass

    async def _generate_diagnostic_report(self):
        """Generate comprehensive diagnostic report"""
        print("\n" + "="*80)
        print("YOUTUBE SUMMARIZER DIAGNOSTIC REPORT")
        print("="*80)

        # Summary
        total_tests = len(self.test_results["tests"])
        passed_tests = len([t for t in self.test_results["tests"].values() if t.get("status") == "pass"])
        failed_tests = len([t for t in self.test_results["tests"].values() if t.get("status") == "fail"])

        print(f"\nSUMMARY:")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")

        # Critical Issues
        print(f"\nCRITICAL ISSUES:")
        critical_issues = []

        for test_name, result in self.test_results["tests"].items():
            if result.get("status") == "fail":
                if "connectivity" in test_name:
                    critical_issues.append(f"🚨 {test_name.upper()}: Cannot connect to server")
                elif "page_loading" in test_name:
                    critical_issues.append(f"🚨 {test_name.upper()}: Page failed to load properly")
                elif "ui_elements" in test_name:
                    critical_issues.append(f"⚠️ {test_name.upper()}: Critical UI elements missing")
                elif "sse_connectivity" in test_name:
                    critical_issues.append(f"⚠️ {test_name.upper()}: Real-time updates not working")
                elif "javascript" in test_name:
                    critical_issues.append(f"⚠️ {test_name.upper()}: JavaScript functionality broken")

        if not critical_issues:
            print("✅ No critical issues detected")
        else:
            for issue in critical_issues:
                print(issue)

        # Detailed Results
        print(f"\nDETAILED TEST RESULTS:")
        for test_name, result in self.test_results["tests"].items():
            status_emoji = "✅" if result["status"] == "pass" else "❌" if result["status"] == "fail" else "ℹ️"
            print(f"\n{status_emoji} {test_name.upper()}:")

            if result.get("error"):
                print(f"   Error: {result['error']}")

            # Test-specific details
            if test_name == "basic_connectivity" and "http_status" in result:
                print(f"   HTTP Status: {result['http_status']}")

            if test_name == "ui_elements" and "elements" in result:
                for elem_name, elem_data in result["elements"].items():
                    if elem_data.get("present"):
                        print(f"   ✅ {elem_name}: present, visible={elem_data.get('visible')}")
                    else:
                        print(f"   ❌ {elem_name}: missing")

            if test_name == "console_errors":
                if result["critical_errors"]:
                    print(f"   Critical Errors: {len(result['critical_errors'])}")
                    for error in result["critical_errors"][:3]:  # Show first 3
                        print(f"     - {error['text'][:100]}...")

            if test_name == "network_requests":
                if result["failed_requests"]:
                    print(f"   Failed Requests: {len(result['failed_requests'])}")
                if result["cors_issues"]:
                    print(f"   CORS Issues: {len(result['cors_issues'])}")

            if test_name == "sse_connectivity" and "connection_result" in result:
                conn_result = result["connection_result"]
                print(f"   SSE Connection: {conn_result.get('connected')}")
                if conn_result.get("error"):
                    print(f"   SSE Error: {conn_result['error']}")

        # Save detailed report to file
        report_file = f"/Users/jaye/projects/youtube-summarizer/diagnostic_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(self.test_results, f, indent=2)

        print(f"\n📊 Detailed report saved to: {report_file}")
        print("="*80)


async def main():
    """Run the diagnostic test"""
    print("🚀 Starting YouTube Summarizer Diagnostic Test")
    print("Target: http://192.168.50.56:8431/")
    print("-" * 50)

    runner = DiagnosticTestRunner()
    await runner.run_comprehensive_diagnostics()


if __name__ == "__main__":
    asyncio.run(main())
