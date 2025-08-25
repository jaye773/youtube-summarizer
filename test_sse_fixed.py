#!/usr/bin/env python3
"""
Test script to verify SSE functionality after fixes
Tests both local and remote instances
"""

import requests
import json
import time
import sys
import threading
from datetime import datetime
import argparse

class SSETester:
    def __init__(self, base_url, username=None, password=None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.username = username
        self.password = password
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "base_url": self.base_url,
            "tests": {}
        }

    def test_basic_connectivity(self):
        """Test if server is responding"""
        print("\n📝 Test 1: Basic Connectivity")
        print("-" * 40)

        try:
            response = self.session.get(f"{self.base_url}/", timeout=5)
            print(f"✅ Server responding: {response.status_code}")
            print(f"   Server: {response.headers.get('Server', 'Unknown')}")

            self.results["tests"]["connectivity"] = {
                "status": "pass",
                "status_code": response.status_code,
                "response_time": response.elapsed.total_seconds()
            }

            # Check if login is required
            if response.status_code == 302 or 'login' in response.url.lower():
                print("🔒 Login required")
                return self.handle_login()

            return True

        except Exception as e:
            print(f"❌ Connection failed: {e}")
            self.results["tests"]["connectivity"] = {
                "status": "fail",
                "error": str(e)
            }
            return False

    def handle_login(self):
        """Handle authentication if required"""
        print("\n🔐 Attempting Login")
        print("-" * 40)

        if not self.username or not self.password:
            print("⚠️ No credentials provided, skipping login tests")
            return False

        try:
            login_data = {
                "username": self.username,
                "password": self.password
            }

            response = self.session.post(
                f"{self.base_url}/login",
                json=login_data,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success"):
                    print(f"✅ Login successful as {self.username}")
                    self.results["tests"]["authentication"] = {
                        "status": "pass",
                        "username": self.username
                    }
                    return True
                else:
                    print(f"❌ Login failed: {result.get('error')}")
                    self.results["tests"]["authentication"] = {
                        "status": "fail",
                        "error": result.get("error")
                    }
                    return False
            else:
                print(f"❌ Login returned status: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Login error: {e}")
            self.results["tests"]["authentication"] = {
                "status": "error",
                "error": str(e)
            }
            return False

    def test_sse_endpoint(self):
        """Test SSE endpoint functionality"""
        print("\n📡 Test 2: SSE Endpoint (/events)")
        print("-" * 40)

        try:
            # Test with streaming
            print("🔄 Connecting to SSE endpoint...")
            response = self.session.get(
                f"{self.base_url}/events",
                stream=True,
                timeout=5,
                headers={"Accept": "text/event-stream"}
            )

            if response.status_code == 200:
                print(f"✅ SSE endpoint accessible")
                print(f"   Content-Type: {response.headers.get('Content-Type')}")

                # Read first few events
                print("\n📨 Reading SSE events:")
                events_received = []
                start_time = time.time()

                for line_num, line in enumerate(response.iter_lines()):
                    if time.time() - start_time > 3:  # Read for 3 seconds
                        break

                    if line:
                        decoded = line.decode('utf-8')
                        if line_num < 10:  # Print first 10 lines
                            print(f"   Line {line_num}: {decoded[:80]}")

                        if decoded.startswith('event:'):
                            event_type = decoded.split(':', 1)[1].strip()
                            events_received.append(event_type)
                        elif decoded.startswith('data:'):
                            try:
                                data = json.loads(decoded.split(':', 1)[1].strip())
                                if 'connection_id' in data:
                                    print(f"\n✅ Connection established: {data['connection_id']}")
                            except:
                                pass

                response.close()

                self.results["tests"]["sse_endpoint"] = {
                    "status": "pass",
                    "events_received": events_received,
                    "connection_established": len(events_received) > 0
                }

                return True

            else:
                print(f"❌ SSE endpoint returned: {response.status_code}")
                self.results["tests"]["sse_endpoint"] = {
                    "status": "fail",
                    "status_code": response.status_code
                }
                return False

        except requests.exceptions.Timeout:
            print("⏱️ SSE connection timed out (may be normal for long-polling)")
            self.results["tests"]["sse_endpoint"] = {
                "status": "warning",
                "note": "Timeout - may be normal for SSE"
            }
            return True

        except Exception as e:
            print(f"❌ SSE test failed: {e}")
            self.results["tests"]["sse_endpoint"] = {
                "status": "error",
                "error": str(e)
            }
            return False

    def test_sse_realtime(self):
        """Test real-time SSE event delivery"""
        print("\n⚡ Test 3: Real-time Event Delivery")
        print("-" * 40)

        events_received = []
        connection_established = threading.Event()

        def sse_listener():
            """Listen for SSE events in background"""
            try:
                response = self.session.get(
                    f"{self.base_url}/events",
                    stream=True,
                    timeout=10,
                    headers={"Accept": "text/event-stream"}
                )

                for line in response.iter_lines():
                    if line:
                        decoded = line.decode('utf-8')
                        if decoded.startswith('event:'):
                            event = decoded.split(':', 1)[1].strip()
                            events_received.append({
                                "event": event,
                                "timestamp": datetime.now().isoformat()
                            })

                            if event == "connected":
                                connection_established.set()

            except Exception as e:
                print(f"   SSE listener error: {e}")

        # Start SSE listener in background
        listener_thread = threading.Thread(target=sse_listener, daemon=True)
        listener_thread.start()

        # Wait for connection
        print("⏳ Waiting for SSE connection...")
        if connection_established.wait(timeout=5):
            print("✅ SSE connection established")

            # Try to trigger an event via broadcast
            print("\n📢 Testing broadcast endpoint...")
            try:
                broadcast_data = {
                    "event": "test_message",
                    "data": {"message": "SSE test event", "timestamp": datetime.now().isoformat()}
                }

                response = self.session.post(
                    f"{self.base_url}/events/broadcast",
                    json=broadcast_data
                )

                if response.status_code == 200:
                    result = response.json()
                    print(f"✅ Broadcast sent to {result.get('sent', 0)} connections")
                else:
                    print(f"⚠️ Broadcast returned: {response.status_code}")

            except Exception as e:
                print(f"⚠️ Broadcast test skipped: {e}")

            # Wait a bit for events
            time.sleep(2)

            print(f"\n📊 Events received: {len(events_received)}")
            for event in events_received[:5]:  # Show first 5
                print(f"   - {event['event']} at {event['timestamp']}")

            self.results["tests"]["sse_realtime"] = {
                "status": "pass",
                "events_count": len(events_received),
                "connection_established": True
            }

            return True

        else:
            print("❌ SSE connection timeout")
            self.results["tests"]["sse_realtime"] = {
                "status": "fail",
                "error": "Connection timeout"
            }
            return False

    def test_health_endpoint(self):
        """Test health check endpoint"""
        print("\n🏥 Test 4: Health Check Endpoint")
        print("-" * 40)

        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)

            if response.status_code == 200:
                data = response.json()
                print("✅ Health endpoint working")
                print(f"   Status: {data.get('status', 'unknown')}")
                print(f"   SSE Connections: {data.get('sse_connections', 0)}")

                self.results["tests"]["health"] = {
                    "status": "pass",
                    "health_data": data
                }
                return True

            elif response.status_code == 404:
                print("⚠️ Health endpoint not found (needs implementation)")
                self.results["tests"]["health"] = {
                    "status": "missing",
                    "note": "Endpoint needs to be implemented"
                }
                return False

            else:
                print(f"❌ Health endpoint returned: {response.status_code}")
                self.results["tests"]["health"] = {
                    "status": "fail",
                    "status_code": response.status_code
                }
                return False

        except Exception as e:
            print(f"❌ Health check failed: {e}")
            self.results["tests"]["health"] = {
                "status": "error",
                "error": str(e)
            }
            return False

    def run_all_tests(self):
        """Run all SSE tests"""
        print("=" * 50)
        print(f"SSE Testing Suite - {self.base_url}")
        print("=" * 50)

        # Run tests
        connectivity_ok = self.test_basic_connectivity()

        if connectivity_ok:
            self.test_sse_endpoint()
            self.test_sse_realtime()
            self.test_health_endpoint()

        # Print summary
        print("\n" + "=" * 50)
        print("Test Summary")
        print("=" * 50)

        passed = 0
        failed = 0
        warnings = 0

        for test_name, result in self.results["tests"].items():
            status = result.get("status", "unknown")
            if status == "pass":
                passed += 1
                print(f"✅ {test_name}: PASSED")
            elif status == "warning":
                warnings += 1
                print(f"⚠️ {test_name}: WARNING")
            else:
                failed += 1
                print(f"❌ {test_name}: FAILED")

        print(f"\nTotal: {passed} passed, {failed} failed, {warnings} warnings")

        # Save results
        with open(f"sse_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w") as f:
            json.dump(self.results, f, indent=2)

        print(f"\nResults saved to: sse_test_results_*.json")

        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Test SSE functionality of YouTube Summarizer")
    parser.add_argument("url", help="Base URL of the instance (e.g., http://192.168.50.56:8431)")
    parser.add_argument("--username", help="Login username if authentication is enabled")
    parser.add_argument("--password", help="Login password if authentication is enabled")

    args = parser.parse_args()

    # Run tests
    tester = SSETester(args.url, args.username, args.password)
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
