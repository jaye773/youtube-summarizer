"""
auth.py - Authentication helpers for the YouTube Summarizer application.

Contains login attempt tracking (load/save/clean/check/record/reset) and the
require_auth route decorator.  app.py calls configure() during startup and
whenever settings are updated so this module always uses the current config.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import jsonify, redirect, request, session, url_for

# ---------------------------------------------------------------------------
# Module-level config — kept in a mutable dict so that configure() updates are
# visible to every function without needing `global` declarations inside them.
# ---------------------------------------------------------------------------
_config = {
    "LOGIN_ATTEMPTS_FILE": "login_attempts.json",
    "MAX_LOGIN_ATTEMPTS": 5,
    "LOCKOUT_DURATION": 15,  # minutes
    "LOGIN_ENABLED": False,
}


def configure(
    login_attempts_file: str,
    max_login_attempts: int,
    lockout_duration: int,
    login_enabled: bool,
) -> None:
    """
    Update auth module config from app.py.

    Call this once during application startup and again any time the runtime
    settings are changed (e.g. from the /settings endpoint).
    """
    _config["LOGIN_ATTEMPTS_FILE"] = login_attempts_file
    _config["MAX_LOGIN_ATTEMPTS"] = max_login_attempts
    _config["LOCKOUT_DURATION"] = lockout_duration
    _config["LOGIN_ENABLED"] = login_enabled


# ---------------------------------------------------------------------------
# Login attempt persistence helpers
# ---------------------------------------------------------------------------


def load_login_attempts() -> dict:
    """Load login attempt tracking data from disk."""
    login_attempts_file = _config["LOGIN_ATTEMPTS_FILE"]
    if os.path.exists(login_attempts_file):
        with open(login_attempts_file, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_login_attempts(attempts_data: dict) -> None:
    """Save login attempt tracking data to disk."""
    login_attempts_file = _config["LOGIN_ATTEMPTS_FILE"]
    with open(login_attempts_file, "w") as f:
        json.dump(attempts_data, f, indent=4)


def clean_expired_attempts(attempts_data: dict) -> dict:
    """Remove expired lockout entries from attempts data."""
    current_time = datetime.now(timezone.utc)
    cleaned_data = {}

    for ip, data in attempts_data.items():
        if "locked_until" in data:
            locked_until = datetime.fromisoformat(data["locked_until"])
            if current_time < locked_until:
                # Still locked — keep the entry
                cleaned_data[ip] = data
            # If the lockout has expired, drop the entry entirely
        else:
            # Not locked; keep the attempt count
            cleaned_data[ip] = data

    return cleaned_data


# ---------------------------------------------------------------------------
# IP lockout helpers
# ---------------------------------------------------------------------------


def is_ip_locked_out(ip_address: str) -> tuple:
    """
    Check whether an IP address is currently locked out.

    Returns:
        (is_locked: bool, remaining_minutes: int | None)
    """
    if not _config["LOGIN_ENABLED"] or os.environ.get("TESTING"):
        return False, None

    attempts_data = load_login_attempts()
    attempts_data = clean_expired_attempts(attempts_data)

    if ip_address in attempts_data and "locked_until" in attempts_data[ip_address]:
        locked_until = datetime.fromisoformat(attempts_data[ip_address]["locked_until"])
        current_time = datetime.now(timezone.utc)

        if current_time < locked_until:
            remaining_minutes = int((locked_until - current_time).total_seconds() / 60)
            return True, remaining_minutes

    return False, None


def record_failed_attempt(ip_address: str) -> bool:
    """
    Record a failed login attempt and apply a lockout if the threshold is reached.

    Returns:
        True if the IP was just locked out, False otherwise.
    """
    if not _config["LOGIN_ENABLED"] or os.environ.get("TESTING"):
        return False

    max_attempts = _config["MAX_LOGIN_ATTEMPTS"]
    lockout_duration = _config["LOCKOUT_DURATION"]

    attempts_data = load_login_attempts()
    attempts_data = clean_expired_attempts(attempts_data)

    if ip_address not in attempts_data:
        attempts_data[ip_address] = {
            "count": 0,
            "first_attempt": datetime.now(timezone.utc).isoformat(),
        }

    attempts_data[ip_address]["count"] += 1
    attempts_data[ip_address]["last_attempt"] = datetime.now(timezone.utc).isoformat()

    # Apply lockout when attempt count reaches the threshold
    if attempts_data[ip_address]["count"] >= max_attempts:
        lockout_until = datetime.now(timezone.utc) + timedelta(minutes=lockout_duration)
        attempts_data[ip_address]["locked_until"] = lockout_until.isoformat()
        attempts_data[ip_address]["count"] = 0  # Reset counter after locking

        save_login_attempts(attempts_data)
        return True  # IP is now locked out

    save_login_attempts(attempts_data)
    return False  # Not yet locked out


def reset_failed_attempts(ip_address: str) -> None:
    """Clear the failed attempt record for an IP after a successful login."""
    if not _config["LOGIN_ENABLED"] or os.environ.get("TESTING"):
        return

    attempts_data = load_login_attempts()
    if ip_address in attempts_data:
        del attempts_data[ip_address]
        save_login_attempts(attempts_data)


# ---------------------------------------------------------------------------
# Authentication decorator
# ---------------------------------------------------------------------------


def require_auth(f):
    """Decorator that requires an authenticated session for a Flask route.

    When LOGIN_ENABLED is False or the app is in TESTING mode, the route is
    called unconditionally.  For unauthenticated requests the decorator either
    returns a 401 JSON response (for API/JSON requests) or redirects the
    browser to the login page.

    LOGIN_ENABLED is read from app.LOGIN_ENABLED at call time (via a lazy
    import) so that test patches on app.LOGIN_ENABLED and runtime updates via
    update_settings() are both reflected immediately.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Lazy import avoids a circular dependency at module load time while
        # still respecting live patches to app.LOGIN_ENABLED (e.g. in tests).
        import app as _app

        login_enabled = _app.LOGIN_ENABLED

        # Skip authentication when login is disabled or in testing mode
        if not login_enabled or os.environ.get("TESTING"):
            return f(*args, **kwargs)

        # Check for an authenticated session
        if not session.get("authenticated", False):
            # Endpoints that should return JSON errors instead of redirects
            api_endpoints = [
                "/summarize",
                "/speak",
                "/get_cached_summaries",
                "/search_summaries",
                "/debug_transcript",
                "/login_status",
                "/api_status",
            ]

            # Settings POST requests should get JSON, GET requests should redirect
            is_settings_post = request.path.startswith("/settings") and request.method == "POST"

            is_api_request = (
                request.content_type == "application/json"
                or any(request.path.startswith(endpoint) for endpoint in api_endpoints)
                or request.headers.get("Accept", "").startswith("application/json")
                or is_settings_post
            )

            if is_api_request:
                return (
                    jsonify(
                        {
                            "error": "Authentication required",
                            "message": "Please login to access this resource",
                        }
                    ),
                    401,
                )

            # Redirect web-browser requests to the login page
            return redirect(url_for("login_page"))

        return f(*args, **kwargs)

    return decorated_function
