import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


# Settings schema definition as specified in the plan
SETTINGS_SCHEMA = {
    "google_api_key": {
        "type": "string",
        "default": "",
        "env_var": "GOOGLE_API_KEY",
        "sensitive": True,
        "description": "Google API Key for AI services"
    },
    "login_enabled": {
        "type": "boolean",
        "default": False,
        "env_var": "LOGIN_ENABLED",
        "description": "Enable login protection"
    },
    "login_code": {
        "type": "string",
        "default": "",
        "env_var": "LOGIN_CODE",
        "sensitive": True,
        "description": "Login code for authentication"
    },
    "session_secret_key": {
        "type": "string",
        "default": "",
        "env_var": "SESSION_SECRET_KEY",
        "sensitive": True,
        "description": "Secret key for session management"
    },
    "max_login_attempts": {
        "type": "integer",
        "default": 5,
        "env_var": "MAX_LOGIN_ATTEMPTS",
        "description": "Maximum login attempts before lockout"
    },
    "lockout_duration": {
        "type": "integer",
        "default": 15,
        "env_var": "LOCKOUT_DURATION",
        "description": "Lockout duration in minutes"
    },
    "data_dir": {
        "type": "string",
        "default": "data",
        "env_var": "DATA_DIR",
        "description": "Directory for storing application data"
    },
    "cache_duration": {
        "type": "integer",
        "default": 86400,
        "env_var": "CACHE_DURATION",
        "description": "Cache duration in seconds (default: 24 hours)"
    },
    "theme": {
        "type": "string",
        "default": "light",
        "options": ["light", "dark"],
        "description": "Application theme"
    },
    "language": {
        "type": "string",
        "default": "en",
        "options": ["en", "es", "fr", "de", "ja", "zh"],
        "description": "Default language for summaries"
    },
    "summary_length": {
        "type": "string",
        "default": "medium",
        "options": ["short", "medium", "long"],
        "description": "Default summary length"
    }
}


class SettingsManager:
    """Manages application settings with file-based persistence and environment variable fallback"""
    
    def __init__(self, settings_file_path: Optional[str] = None):
        """Initialize the settings manager
        
        Args:
            settings_file_path: Path to the settings file. If None, will be determined automatically.
        """
        if settings_file_path is None:
            # Use data directory if running in Docker/Podman, otherwise use current directory
            base_dir = "data" if os.path.exists("/.dockerenv") else "."
            os.makedirs(base_dir, exist_ok=True)
            self.settings_file = os.path.join(base_dir, "settings.json")
        else:
            self.settings_file = settings_file_path
            
        self._settings_cache = None
        self._last_modified = None
    
    def _get_env_value(self, key: str, schema_item: Dict[str, Any]) -> Any:
        """Get value from environment variable with proper type conversion"""
        env_var = schema_item.get("env_var")
        if not env_var:
            return schema_item["default"]
            
        env_value = os.environ.get(env_var)
        if env_value is None:
            return schema_item["default"]
            
        # Convert based on type
        value_type = schema_item["type"]
        try:
            if value_type == "boolean":
                return env_value.lower() in ("true", "1", "yes", "on")
            elif value_type == "integer":
                return int(env_value)
            elif value_type == "string":
                return env_value
            else:
                return env_value
        except (ValueError, TypeError):
            print(f"Warning: Invalid value '{env_value}' for {env_var}, using default")
            return schema_item["default"]
    
    def _load_settings_from_file(self) -> Dict[str, Any]:
        """Load settings from file"""
        if not os.path.exists(self.settings_file):
            return {}
            
        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)
                return data.get("settings", {})
        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
            print(f"Warning: Could not load settings file: {e}")
            return {}
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from file and merge with environment variables
        
        Priority order:
        1. Settings file (highest priority)
        2. Environment variables
        3. Default values (lowest priority)
        """
        # Check if we need to reload
        if self._settings_cache is not None and os.path.exists(self.settings_file):
            current_mtime = os.path.getmtime(self.settings_file)
            if self._last_modified is not None and current_mtime == self._last_modified:
                return self._settings_cache
        
        file_settings = self._load_settings_from_file()
        merged_settings = {}
        
        # Process each setting according to schema
        for key, schema_item in SETTINGS_SCHEMA.items():
            if key in file_settings:
                # Use file setting if available
                merged_settings[key] = file_settings[key]
            else:
                # Fall back to environment variable or default
                merged_settings[key] = self._get_env_value(key, schema_item)
        
        # Cache the results
        self._settings_cache = merged_settings
        if os.path.exists(self.settings_file):
            self._last_modified = os.path.getmtime(self.settings_file)
            
        return merged_settings
    
    def save_settings(self, settings_dict: Dict[str, Any]) -> bool:
        """Save settings to file
        
        Args:
            settings_dict: Dictionary of settings to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate settings before saving
            validation_errors = self.validate_settings(settings_dict)
            if validation_errors:
                print(f"Validation errors: {validation_errors}")
                return False
            
            # Create the full settings file structure
            settings_data = {
                "version": "1.0",
                "settings": settings_dict,
                "metadata": {
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "updated_by": "system"
                }
            }
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            
            # Write to file
            with open(self.settings_file, "w") as f:
                json.dump(settings_data, f, indent=4)
            
            # Clear cache to force reload
            self._settings_cache = None
            self._last_modified = None
            
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a specific setting value
        
        Args:
            key: Setting key
            default: Default value if key not found
            
        Returns:
            Setting value or default
        """
        settings = self.load_settings()
        return settings.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> bool:
        """Update a specific setting
        
        Args:
            key: Setting key
            value: New value
            
        Returns:
            True if successful, False otherwise
        """
        if key not in SETTINGS_SCHEMA:
            print(f"Warning: Unknown setting key '{key}'")
            return False
            
        settings = self.load_settings()
        settings[key] = value
        return self.save_settings(settings)
    
    def validate_settings(self, settings_dict: Dict[str, Any]) -> List[str]:
        """Validate settings against schema
        
        Args:
            settings_dict: Settings to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for key, value in settings_dict.items():
            if key not in SETTINGS_SCHEMA:
                errors.append(f"Unknown setting: {key}")
                continue
                
            schema_item = SETTINGS_SCHEMA[key]
            value_type = schema_item["type"]
            
            # Type validation
            if value_type == "boolean" and not isinstance(value, bool):
                errors.append(f"{key}: Expected boolean, got {type(value).__name__}")
            elif value_type == "integer" and not isinstance(value, int):
                errors.append(f"{key}: Expected integer, got {type(value).__name__}")
            elif value_type == "string" and not isinstance(value, str):
                errors.append(f"{key}: Expected string, got {type(value).__name__}")
            
            # Options validation
            if "options" in schema_item and value not in schema_item["options"]:
                errors.append(f"{key}: Value '{value}' not in allowed options: {schema_item['options']}")
        
        return errors
    
    def reset_settings(self, keys: Optional[List[str]] = None) -> bool:
        """Reset settings to default values
        
        Args:
            keys: List of specific keys to reset. If None, reset all settings.
            
        Returns:
            True if successful, False otherwise
        """
        settings = self.load_settings()
        
        keys_to_reset = keys if keys is not None else list(SETTINGS_SCHEMA.keys())
        
        for key in keys_to_reset:
            if key in SETTINGS_SCHEMA:
                settings[key] = SETTINGS_SCHEMA[key]["default"]
        
        return self.save_settings(settings)
    
    def export_settings(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Export settings (optionally excluding sensitive data)
        
        Args:
            include_sensitive: Whether to include sensitive settings
            
        Returns:
            Dictionary of settings
        """
        settings = self.load_settings()
        
        if include_sensitive:
            return settings.copy()
        
        # Filter out sensitive settings
        filtered_settings = {}
        for key, value in settings.items():
            if key in SETTINGS_SCHEMA:
                schema_item = SETTINGS_SCHEMA[key]
                if not schema_item.get("sensitive", False):
                    filtered_settings[key] = value
                else:
                    filtered_settings[key] = "***masked***"
            else:
                filtered_settings[key] = value
        
        return filtered_settings
    
    def import_settings(self, settings_dict: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Import settings with validation
        
        Args:
            settings_dict: Settings to import
            
        Returns:
            Tuple of (success, list of error messages)
        """
        # Validate the imported settings
        validation_errors = self.validate_settings(settings_dict)
        if validation_errors:
            return False, validation_errors
        
        # Load current settings and update with imported ones
        current_settings = self.load_settings()
        current_settings.update(settings_dict)
        
        success = self.save_settings(current_settings)
        return success, [] if success else ["Failed to save imported settings"]
    
    def get_settings_schema(self) -> Dict[str, Any]:
        """Get the settings schema for UI generation
        
        Returns:
            Settings schema dictionary
        """
        return SETTINGS_SCHEMA.copy()


# Global settings manager instance
_settings_manager = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance"""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager


# Convenience functions for backward compatibility
def load_settings() -> Dict[str, Any]:
    """Load settings from file, merge with env vars"""
    return get_settings_manager().load_settings()


def save_settings(settings_dict: Dict[str, Any]) -> bool:
    """Save settings to file"""
    return get_settings_manager().save_settings(settings_dict)


def get_setting(key: str, default: Any = None) -> Any:
    """Get a specific setting"""
    return get_settings_manager().get_setting(key, default)


def update_setting(key: str, value: Any) -> bool:
    """Update a specific setting"""
    return get_settings_manager().update_setting(key, value)


def validate_settings(settings_dict: Dict[str, Any]) -> List[str]:
    """Validate settings against schema"""
    return get_settings_manager().validate_settings(settings_dict)


def reset_settings(keys: Optional[List[str]] = None) -> bool:
    """Reset settings to defaults"""
    return get_settings_manager().reset_settings(keys)


def export_settings(include_sensitive: bool = False) -> Dict[str, Any]:
    """Export settings (excluding sensitive data by default)"""
    return get_settings_manager().export_settings(include_sensitive)


def import_settings(settings_dict: Dict[str, Any]) -> tuple[bool, List[str]]:
    """Import settings with validation"""
    return get_settings_manager().import_settings(settings_dict)