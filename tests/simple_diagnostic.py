#!/usr/bin/env python3
"""
Simple diagnostic test for YouTube Summarizer instance using HTTP requests
Tests the running application at http://192.168.50.56:8431/ for basic connectivity and issues
"""
import requests
import json
import time
from datetime import datetime
from urllib.parse import urljoin
import subprocess
import sys


class SimpleDiagnosticRunner:
    def __init__(self, base_url: str = "http://192.168.50.56:8431"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 10
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": base_url,
            "tests": {}
        }

    def run_all_tests(self):
        """Run all diagnostic tests"""
        print("🚀 Starting YouTube Summarizer Simple Diagnostic Test")
        print(f"Target: {self.base_url}")
        print("-" * 60)

        # Run tests
        self.test_basic_connectivity()
        self.test_http_response()
        self.test_static_resources()
        self.test_api_endpoints()
        self.test_sse_endpoint()
        self.test_curl_analysis()

        # Generate report
        self.generate_report()

    def test_basic_connectivity(self):
        """Test basic HTTP connectivity"""
        print("🔍 Testing basic connectivity...")

        try:
            response = self.session.get(self.base_url)

            self.results["tests"]["connectivity"] = {
                "status": "pass" if response.status_code == 200 else "fail",
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "response_time": response.elapsed.total_seconds(),
                "content_length": len(response.content)
            }

            if response.status_code == 200:
                print(f"✅ Connectivity: HTTP {response.status_code} ({response.elapsed.total_seconds():.2f}s)")
            else:
                print(f"❌ Connectivity: HTTP {response.status_code}")

        except requests.exceptions.RequestException as e:
            self.results["tests"]["connectivity"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Connectivity failed: {str(e)}")

    def test_http_response(self):
        """Test HTTP response content and headers"""
        print("🔍 Testing HTTP response content...")

        try:
            response = self.session.get(self.base_url)
            content = response.text

            # Check for key indicators
            indicators = {
                "html_structure": "<html" in content.lower() and "</html>" in content.lower(),
                "title_present": "<title>" in content.lower(),
                "form_present": "<form" in content.lower(),
                "input_present": "input" in content.lower(),
                "script_tags": "<script" in content.lower(),
                "css_links": 'rel="stylesheet"' in content.lower(),
                "youtube_mentions": "youtube" in content.lower()
            }

            # Check headers
            important_headers = {
                "content_type": response.headers.get("content-type", ""),
                "server": response.headers.get("server", ""),
                "cache_control": response.headers.get("cache-control", "")
            }

            self.results["tests"]["http_content"] = {
                "status": "pass" if indicators["html_structure"] else "fail",
                "indicators": indicators,
                "headers": important_headers,
                "content_preview": content[:500] + "..." if len(content) > 500 else content
            }

            if indicators["html_structure"]:
                print("✅ HTTP Content: Valid HTML structure detected")
            else:
                print("❌ HTTP Content: Invalid or missing HTML structure")

        except Exception as e:
            self.results["tests"]["http_content"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ HTTP content test failed: {str(e)}")

    def test_static_resources(self):
        """Test static resources (CSS, JS)"""
        print("🔍 Testing static resources...")

        static_resources = [
            "/static/css/async_ui.css",
            "/static/js/sse_client.js",
            "/static/js/job_tracker.js",
            "/static/js/ui_updater.js"
        ]

        resource_results = {}

        for resource in static_resources:
            try:
                url = urljoin(self.base_url, resource)
                response = self.session.get(url)

                resource_results[resource] = {
                    "status_code": response.status_code,
                    "accessible": response.status_code == 200,
                    "content_type": response.headers.get("content-type", ""),
                    "size": len(response.content)
                }

            except Exception as e:
                resource_results[resource] = {
                    "accessible": False,
                    "error": str(e)
                }

        accessible_count = sum(1 for r in resource_results.values() if r.get("accessible"))
        total_count = len(static_resources)

        self.results["tests"]["static_resources"] = {
            "status": "pass" if accessible_count >= total_count * 0.75 else "fail",
            "accessible_count": accessible_count,
            "total_count": total_count,
            "resources": resource_results
        }

        print(f"✅ Static Resources: {accessible_count}/{total_count} accessible")

    def test_api_endpoints(self):
        """Test API endpoints"""
        print("🔍 Testing API endpoints...")

        endpoints = [
            ("/", "GET", "main_page"),
            ("/health", "GET", "health_check"),
            ("/api/status", "GET", "api_status")
        ]

        endpoint_results = {}

        for path, method, name in endpoints:
            try:
                url = urljoin(self.base_url, path)

                if method == "GET":
                    response = self.session.get(url)
                elif method == "POST":
                    response = self.session.post(url)

                endpoint_results[name] = {
                    "url": url,
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "accessible": response.status_code in [200, 201, 204]
                }

            except Exception as e:
                endpoint_results[name] = {
                    "url": urljoin(self.base_url, path),
                    "accessible": False,
                    "error": str(e)
                }

        accessible_count = sum(1 for r in endpoint_results.values() if r.get("accessible"))

        self.results["tests"]["api_endpoints"] = {
            "status": "pass" if endpoint_results.get("main_page", {}).get("accessible") else "fail",
            "accessible_count": accessible_count,
            "endpoints": endpoint_results
        }

        print(f"✅ API Endpoints: Main page accessible={endpoint_results.get('main_page', {}).get('accessible')}")

    def test_sse_endpoint(self):
        """Test Server-Sent Events endpoint"""
        print("🔍 Testing SSE endpoint...")

        try:
            sse_url = urljoin(self.base_url, "/sse")

            # Test if SSE endpoint accepts connections
            response = self.session.get(sse_url, timeout=3, stream=True)

            # Check response headers for SSE
            content_type = response.headers.get("content-type", "")
            is_sse = "text/event-stream" in content_type

            self.results["tests"]["sse_endpoint"] = {
                "status": "pass" if response.status_code == 200 and is_sse else "fail",
                "status_code": response.status_code,
                "content_type": content_type,
                "sse_headers_present": is_sse,
                "accessible": response.status_code == 200
            }

            if response.status_code == 200 and is_sse:
                print("✅ SSE Endpoint: Accessible with correct headers")
            else:
                print(f"❌ SSE Endpoint: Status {response.status_code}, SSE headers: {is_sse}")

        except requests.exceptions.Timeout:
            self.results["tests"]["sse_endpoint"] = {
                "status": "warning",
                "error": "Connection timeout (expected for SSE)"
            }
            print("⚠️ SSE Endpoint: Timeout (normal for SSE connections)")

        except Exception as e:
            self.results["tests"]["sse_endpoint"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ SSE Endpoint failed: {str(e)}")

    def test_curl_analysis(self):
        """Use curl for detailed HTTP analysis"""
        print("🔍 Running curl analysis...")

        try:
            # Run curl with detailed output
            curl_cmd = [
                "curl", "-v", "-s", "-o", "/dev/null",
                "--connect-timeout", "10",
                "--max-time", "10",
                self.base_url
            ]

            result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=15)

            # Parse curl output
            curl_output = result.stderr  # curl writes verbose info to stderr

            # Extract useful information
            analysis = {
                "connection_successful": "Connected to" in curl_output,
                "http_response": "HTTP/" in curl_output,
                "ssl_issues": "SSL" in curl_output and ("error" in curl_output.lower() or "failed" in curl_output.lower()),
                "dns_resolution": "getaddrinfo" not in curl_output or "Could not resolve host" not in curl_output,
                "raw_output": curl_output
            }

            self.results["tests"]["curl_analysis"] = {
                "status": "pass" if analysis["connection_successful"] else "fail",
                "return_code": result.returncode,
                "analysis": analysis
            }

            if analysis["connection_successful"]:
                print("✅ Curl Analysis: Connection successful")
            else:
                print("❌ Curl Analysis: Connection failed")

        except subprocess.TimeoutExpired:
            self.results["tests"]["curl_analysis"] = {
                "status": "fail",
                "error": "Curl command timed out"
            }
            print("❌ Curl Analysis: Command timed out")

        except Exception as e:
            self.results["tests"]["curl_analysis"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Curl Analysis failed: {str(e)}")

    def generate_report(self):
        """Generate comprehensive diagnostic report"""
        print("\n" + "="*60)
        print("YOUTUBE SUMMARIZER SIMPLE DIAGNOSTIC REPORT")
        print("="*60)

        # Summary
        total_tests = len(self.results["tests"])
        passed_tests = len([t for t in self.results["tests"].values() if t.get("status") == "pass"])
        failed_tests = len([t for t in self.results["tests"].values() if t.get("status") == "fail"])
        warning_tests = len([t for t in self.results["tests"].values() if t.get("status") == "warning"])

        print(f"\nSUMMARY:")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Warnings: {warning_tests}")
        if total_tests > 0:
            print(f"Success Rate: {(passed_tests/total_tests*100):.1f}%")

        # Critical Issues Analysis
        print(f"\nCRITICAL ISSUES ANALYSIS:")

        connectivity = self.results["tests"].get("connectivity", {})
        if connectivity.get("status") == "fail":
            print("🚨 CRITICAL: Cannot connect to the server at all")
            if "error" in connectivity:
                print(f"   Error: {connectivity['error']}")
            print("   → Check if the server is running")
            print("   → Verify the correct IP address and port")
            print("   → Check firewall settings")

        http_content = self.results["tests"].get("http_content", {})
        if http_content.get("status") == "fail":
            print("🚨 CRITICAL: Server responds but doesn't serve valid HTML")
            indicators = http_content.get("indicators", {})
            if not indicators.get("html_structure"):
                print("   → Server may be serving error page or wrong content")
            if not indicators.get("form_present"):
                print("   → YouTube Summarizer UI form is missing")

        static_resources = self.results["tests"].get("static_resources", {})
        if static_resources.get("accessible_count", 0) == 0:
            print("⚠️ WARNING: No static resources (CSS/JS) are accessible")
            print("   → Frontend functionality may be broken")
            print("   → Check static file serving configuration")

        sse_endpoint = self.results["tests"].get("sse_endpoint", {})
        if sse_endpoint.get("status") == "fail":
            print("⚠️ WARNING: SSE endpoint not working")
            print("   → Real-time progress updates will not work")
            print("   → Users won't see job progress")

        # If everything looks good
        if connectivity.get("status") == "pass" and http_content.get("status") == "pass":
            print("✅ Basic functionality appears to be working")
            print("   → Server is responding correctly")
            print("   → HTML content is being served")

            # Additional recommendations
            if static_resources.get("accessible_count", 0) < static_resources.get("total_count", 1):
                print("   → Some static resources missing - check console for JS errors")

            if sse_endpoint.get("status") != "pass":
                print("   → SSE issues may affect real-time updates")

        # Detailed Results
        print(f"\nDETAILED RESULTS:")
        for test_name, result in self.results["tests"].items():
            status_emoji = "✅" if result["status"] == "pass" else "❌" if result["status"] == "fail" else "⚠️"
            print(f"\n{status_emoji} {test_name.upper().replace('_', ' ')}:")

            if result.get("error"):
                print(f"   Error: {result['error']}")

            if test_name == "connectivity" and "status_code" in result:
                print(f"   HTTP Status: {result['status_code']}")
                print(f"   Response Time: {result.get('response_time', 0):.2f}s")

            if test_name == "static_resources":
                accessible = result.get("accessible_count", 0)
                total = result.get("total_count", 0)
                print(f"   Resources: {accessible}/{total} accessible")

                for resource, data in result.get("resources", {}).items():
                    status = "✅" if data.get("accessible") else "❌"
                    print(f"   {status} {resource}")

            if test_name == "sse_endpoint" and "content_type" in result:
                print(f"   Content-Type: {result['content_type']}")
                print(f"   SSE Headers: {result.get('sse_headers_present', False)}")

        # Save detailed report
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"/Users/jaye/projects/youtube-summarizer/simple_diagnostic_report_{timestamp}.json"

        try:
            with open(report_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"\n📊 Detailed report saved to: {report_file}")
        except Exception as e:
            print(f"\n❌ Could not save report: {str(e)}")

        print("="*60)

        # Quick Action Items
        print("\nQUICK ACTION ITEMS:")
        if connectivity.get("status") == "fail":
            print("1. 🚨 Verify server is running: python app.py")
            print("2. 🚨 Check IP and port: netstat -an | grep 8431")
            print("3. 🚨 Test locally: curl http://localhost:8431/")
        elif http_content.get("status") == "fail":
            print("1. ⚠️ Check application logs for errors")
            print("2. ⚠️ Verify Flask app is serving correctly")
            print("3. ⚠️ Test with browser: open http://192.168.50.56:8431/")
        else:
            print("1. ✅ Basic connectivity is working")
            print("2. ✅ Try accessing via browser for full testing")
            if sse_endpoint.get("status") != "pass":
                print("3. ⚠️ Check SSE implementation for real-time updates")


def main():
    """Run the simple diagnostic test"""
    runner = SimpleDiagnosticRunner()
    runner.run_all_tests()


if __name__ == "__main__":
    main()
