#!/usr/bin/env python3
"""
Diagnostic for hanging YouTube Summarizer instance
Focuses on identifying why the server accepts connections but doesn't respond to HTTP requests
"""
import socket
import time
import threading
from datetime import datetime
import subprocess
import sys


class HangingDiagnostic:
    def __init__(self, host="192.168.50.56", port=8431):
        self.host = host
        self.port = port
        self.results = {}

    def run_all_diagnostics(self):
        """Run all diagnostic tests for hanging server"""
        print("🔍 YOUTUBE SUMMARIZER HANGING SERVER DIAGNOSTIC")
        print(f"Target: {self.host}:{self.port}")
        print("=" * 60)

        self.test_tcp_connection()
        self.test_http_request_timeout()
        self.test_partial_http_response()
        self.test_multiple_connections()
        self.test_server_process()

        self.generate_diagnosis()

    def test_tcp_connection(self):
        """Test basic TCP connection"""
        print("\n🔍 Testing TCP connection...")

        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)

            result = sock.connect_ex((self.host, self.port))
            connection_time = time.time() - start_time
            sock.close()

            if result == 0:
                self.results["tcp_connection"] = {
                    "status": "pass",
                    "connection_time": connection_time,
                    "port_open": True
                }
                print(f"✅ TCP Connection: Successful ({connection_time:.2f}s)")
            else:
                self.results["tcp_connection"] = {
                    "status": "fail",
                    "error": f"Connection failed with code {result}",
                    "port_open": False
                }
                print(f"❌ TCP Connection: Failed (code {result})")

        except Exception as e:
            self.results["tcp_connection"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ TCP Connection: Exception - {str(e)}")

    def test_http_request_timeout(self):
        """Test HTTP request with different timeout values"""
        print("\n🔍 Testing HTTP request timeouts...")

        timeouts = [1, 3, 5, 10]
        timeout_results = {}

        for timeout in timeouts:
            try:
                print(f"   Testing {timeout}s timeout...")
                start_time = time.time()

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect((self.host, self.port))

                # Send HTTP request
                http_request = (
                    f"GET / HTTP/1.1\r\n"
                    f"Host: {self.host}:{self.port}\r\n"
                    f"User-Agent: HangingDiagnostic/1.0\r\n"
                    f"Connection: close\r\n\r\n"
                ).encode()

                sock.send(http_request)

                # Try to receive response
                response = b""
                try:
                    while True:
                        data = sock.recv(1024)
                        if not data:
                            break
                        response += data
                        if len(response) > 10000:  # Prevent infinite read
                            break
                except socket.timeout:
                    pass

                elapsed_time = time.time() - start_time
                sock.close()

                timeout_results[timeout] = {
                    "elapsed_time": elapsed_time,
                    "response_received": len(response) > 0,
                    "response_length": len(response),
                    "response_preview": response[:200].decode('utf-8', errors='ignore') if response else ""
                }

                if len(response) > 0:
                    print(f"   ✅ {timeout}s: Got {len(response)} bytes ({elapsed_time:.2f}s)")
                else:
                    print(f"   ❌ {timeout}s: No response ({elapsed_time:.2f}s)")

            except socket.timeout:
                timeout_results[timeout] = {
                    "elapsed_time": timeout,
                    "timed_out": True,
                    "response_received": False
                }
                print(f"   ⏰ {timeout}s: Timed out")

            except Exception as e:
                timeout_results[timeout] = {
                    "error": str(e),
                    "response_received": False
                }
                print(f"   ❌ {timeout}s: Error - {str(e)}")

        # Determine if any timeout worked
        any_response = any(r.get("response_received") for r in timeout_results.values())

        self.results["http_timeouts"] = {
            "status": "pass" if any_response else "fail",
            "timeout_results": timeout_results,
            "any_response_received": any_response
        }

    def test_partial_http_response(self):
        """Test if server starts to respond but hangs mid-response"""
        print("\n🔍 Testing for partial HTTP responses...")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # Short timeout for this test
            sock.connect((self.host, self.port))

            # Send HTTP request
            http_request = (
                f"GET / HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"User-Agent: PartialResponseTest/1.0\r\n"
                f"Connection: close\r\n\r\n"
            ).encode()

            sock.send(http_request)

            # Read response in small chunks with timing
            response_parts = []
            chunk_times = []

            while True:
                try:
                    start_chunk = time.time()
                    data = sock.recv(100)  # Small chunks
                    chunk_time = time.time() - start_chunk

                    if not data:
                        break

                    response_parts.append(data)
                    chunk_times.append(chunk_time)

                    if len(response_parts) > 100:  # Prevent runaway
                        break

                except socket.timeout:
                    break

            sock.close()

            full_response = b"".join(response_parts)

            self.results["partial_response"] = {
                "status": "info",
                "chunks_received": len(response_parts),
                "total_bytes": len(full_response),
                "chunk_times": chunk_times,
                "response_preview": full_response[:500].decode('utf-8', errors='ignore'),
                "appears_incomplete": len(response_parts) > 0 and not full_response.endswith(b'</html>')
            }

            if len(response_parts) > 0:
                print(f"✅ Partial Response: {len(response_parts)} chunks, {len(full_response)} total bytes")
                if chunk_times:
                    avg_chunk_time = sum(chunk_times) / len(chunk_times)
                    print(f"   Average chunk time: {avg_chunk_time:.3f}s")
            else:
                print("❌ Partial Response: No data received")

        except Exception as e:
            self.results["partial_response"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Partial Response test failed: {str(e)}")

    def test_multiple_connections(self):
        """Test if server can handle multiple simultaneous connections"""
        print("\n🔍 Testing multiple simultaneous connections...")

        def test_connection(conn_id):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                start_time = time.time()

                sock.connect((self.host, self.port))
                connection_time = time.time() - start_time

                # Send simple HTTP request
                http_request = f"GET / HTTP/1.1\r\nHost: {self.host}\r\nConnection: close\r\n\r\n".encode()
                sock.send(http_request)

                # Try to get some response
                response = b""
                try:
                    response = sock.recv(1024)
                except socket.timeout:
                    pass

                total_time = time.time() - start_time
                sock.close()

                return {
                    "conn_id": conn_id,
                    "success": True,
                    "connection_time": connection_time,
                    "total_time": total_time,
                    "got_response": len(response) > 0,
                    "response_length": len(response)
                }

            except Exception as e:
                return {
                    "conn_id": conn_id,
                    "success": False,
                    "error": str(e)
                }

        # Test 3 simultaneous connections
        threads = []
        results = []

        for i in range(3):
            thread = threading.Thread(target=lambda i=i: results.append(test_connection(i)))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=10)

        successful_connections = sum(1 for r in results if r.get("success"))
        connections_with_response = sum(1 for r in results if r.get("got_response"))

        self.results["multiple_connections"] = {
            "status": "pass" if successful_connections > 0 else "fail",
            "total_attempts": 3,
            "successful_connections": successful_connections,
            "connections_with_response": connections_with_response,
            "connection_results": results
        }

        print(f"✅ Multiple Connections: {successful_connections}/3 connected, {connections_with_response}/3 got response")

    def test_server_process(self):
        """Check what's happening with the server process"""
        print("\n🔍 Checking server process status...")

        try:
            # Check what's listening on the port
            netstat_result = subprocess.run(
                ["netstat", "-an", "-p", "tcp"],
                capture_output=True, text=True, timeout=10
            )

            port_lines = [line for line in netstat_result.stdout.split('\n') if '8431' in line]

            # Check for Python processes
            ps_result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10
            )

            python_processes = [
                line for line in ps_result.stdout.split('\n')
                if 'python' in line.lower() and ('app.py' in line or '8431' in line or 'flask' in line.lower())
            ]

            self.results["server_process"] = {
                "status": "info",
                "port_listeners": port_lines,
                "python_processes": python_processes,
                "netstat_success": netstat_result.returncode == 0,
                "ps_success": ps_result.returncode == 0
            }

            if port_lines:
                print(f"✅ Port Listeners: {len(port_lines)} process(es) on port 8431")
                for line in port_lines:
                    print(f"   {line.strip()}")

            if python_processes:
                print(f"✅ Python Processes: {len(python_processes)} relevant process(es)")
                for proc in python_processes[:3]:  # Show first 3
                    print(f"   {proc.strip()}")

        except subprocess.TimeoutExpired:
            self.results["server_process"] = {
                "status": "fail",
                "error": "Process check commands timed out"
            }
            print("❌ Server Process: Commands timed out")

        except Exception as e:
            self.results["server_process"] = {
                "status": "fail",
                "error": str(e)
            }
            print(f"❌ Server Process check failed: {str(e)}")

    def generate_diagnosis(self):
        """Generate diagnosis based on test results"""
        print("\n" + "="*60)
        print("DIAGNOSIS AND RECOMMENDATIONS")
        print("="*60)

        tcp_ok = self.results.get("tcp_connection", {}).get("status") == "pass"
        http_timeout = self.results.get("http_timeouts", {})
        partial_response = self.results.get("partial_response", {})

        print(f"\n🔍 PROBLEM ANALYSIS:")

        if not tcp_ok:
            print("🚨 CRITICAL: Cannot establish TCP connection")
            print("   → Server is not running or port is blocked")
            print("   → ACTION: Check if server process is running")

        elif not http_timeout.get("any_response_received", False):
            print("🚨 CRITICAL: Server accepts connections but never responds to HTTP requests")
            print("   → Server is hanging/deadlocked on HTTP request processing")
            print("   → This suggests an application-level problem, not network issue")

            # Analyze specific hanging patterns
            timeout_results = http_timeout.get("timeout_results", {})
            if all(not r.get("response_received", False) for r in timeout_results.values()):
                print("   → Server consistently hangs on ALL HTTP requests")
                print("   → Likely causes:")
                print("     • Deadlock in Flask application code")
                print("     • Blocking I/O operation without timeout")
                print("     • Infinite loop in request handler")
                print("     • Database connection hanging")
                print("     • External API call without timeout")

            # Check partial response data
            if partial_response.get("chunks_received", 0) > 0:
                print("   → Server starts responding but hangs mid-stream")
                print("     • Template rendering issue")
                print("     • Streaming response problem")
                print("     • Memory/resource exhaustion")
            else:
                print("   → Server never starts sending HTTP response")
                print("     • Request routing/handler issue")
                print("     • Early blocking operation")

        else:
            print("✅ Server responds to HTTP requests (at least sometimes)")
            print("   → Check response quality and consistency")

        print(f"\n🔧 IMMEDIATE ACTIONS:")
        print("1. 🚨 Check server logs for errors/exceptions")
        print("2. 🚨 Restart the YouTube Summarizer process")
        print("3. 🔍 Test locally: python app.py (check for startup errors)")
        print("4. 🔍 Check resource usage: top -p <server_pid>")

        if not http_timeout.get("any_response_received", False):
            print("5. 🚨 URGENT: Server is completely unresponsive to HTTP")
            print("   → Kill and restart the server process immediately")
            print("   → Check for deadlocks or infinite loops in code")

        print(f"\n📋 TECHNICAL DETAILS:")
        for test_name, result in self.results.items():
            if isinstance(result, dict) and result.get("status"):
                status_emoji = "✅" if result["status"] == "pass" else "❌" if result["status"] == "fail" else "ℹ️"
                print(f"{status_emoji} {test_name.replace('_', ' ').title()}")

                if result.get("error"):
                    print(f"   Error: {result['error']}")

        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"/Users/jaye/projects/youtube-summarizer/hanging_diagnostic_{timestamp}.json"

        try:
            import json
            with open(report_file, 'w') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "host": self.host,
                    "port": self.port,
                    "results": self.results
                }, f, indent=2)
            print(f"\n📊 Detailed results saved to: {report_file}")
        except Exception as e:
            print(f"\n❌ Could not save results: {str(e)}")

        print("="*60)


def main():
    diagnostic = HangingDiagnostic()
    diagnostic.run_all_diagnostics()


if __name__ == "__main__":
    main()
