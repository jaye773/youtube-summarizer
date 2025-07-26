import json
import os
import tempfile
import unittest
from unittest.mock import patch

from settings_config import (
    SETTINGS_SCHEMA, 
    SettingsManager, 
    get_setting, 
    load_settings, 
    save_settings,
    validate_settings,
    reset_settings,
    export_settings,
    import_settings
)


class TestSettingsConfig(unittest.TestCase):
    """Test cases for the settings configuration system"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.settings_file = os.path.join(self.temp_dir, "test_settings.json")
        self.settings_manager = SettingsManager(self.settings_file)
    
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        os.rmdir(self.temp_dir)
    
    def test_settings_schema_exists(self):
        """Test that settings schema is properly defined"""
        self.assertIsInstance(SETTINGS_SCHEMA, dict)
        self.assertIn("google_api_key", SETTINGS_SCHEMA)
        self.assertIn("login_enabled", SETTINGS_SCHEMA)
        self.assertIn("data_dir", SETTINGS_SCHEMA)
    
    def test_load_default_settings(self):
        """Test loading default settings when no file exists"""
        settings = self.settings_manager.load_settings()
        
        # Check that we get default values
        self.assertEqual(settings["login_enabled"], False)
        self.assertEqual(settings["max_login_attempts"], 5)
        self.assertEqual(settings["theme"], "light")
        self.assertEqual(settings["language"], "en")
    
    @patch.dict(os.environ, {
        "GOOGLE_API_KEY": "test_api_key",
        "LOGIN_ENABLED": "true",
        "MAX_LOGIN_ATTEMPTS": "10"
    })
    def test_load_settings_from_env(self):
        """Test loading settings from environment variables"""
        settings = self.settings_manager.load_settings()
        
        self.assertEqual(settings["google_api_key"], "test_api_key")
        self.assertEqual(settings["login_enabled"], True)
        self.assertEqual(settings["max_login_attempts"], 10)
    
    def test_save_and_load_settings(self):
        """Test saving and loading settings from file"""
        test_settings = {
            "google_api_key": "saved_api_key",
            "login_enabled": True,
            "max_login_attempts": 3,
            "theme": "dark",
            "language": "es"
        }
        
        # Fill in missing settings with defaults
        for key, schema in SETTINGS_SCHEMA.items():
            if key not in test_settings:
                test_settings[key] = schema["default"]
        
        # Save settings
        success = self.settings_manager.save_settings(test_settings)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.settings_file))
        
        # Load settings
        loaded_settings = self.settings_manager.load_settings()
        self.assertEqual(loaded_settings["google_api_key"], "saved_api_key")
        self.assertEqual(loaded_settings["login_enabled"], True)
        self.assertEqual(loaded_settings["max_login_attempts"], 3)
        self.assertEqual(loaded_settings["theme"], "dark")
        self.assertEqual(loaded_settings["language"], "es")
    
    def test_validate_settings(self):
        """Test settings validation"""
        # Valid settings
        valid_settings = {
            "login_enabled": True,
            "max_login_attempts": 5,
            "theme": "dark",
            "language": "en"
        }
        errors = self.settings_manager.validate_settings(valid_settings)
        self.assertEqual(len(errors), 0)
        
        # Invalid settings
        invalid_settings = {
            "login_enabled": "not_a_boolean",  # Wrong type
            "max_login_attempts": "not_an_integer",  # Wrong type
            "theme": "invalid_theme",  # Not in options
            "unknown_setting": "value"  # Unknown setting
        }
        errors = self.settings_manager.validate_settings(invalid_settings)
        self.assertGreater(len(errors), 0)
    
    def test_get_setting(self):
        """Test getting individual settings"""
        test_settings = {
            "google_api_key": "test_key",
            "login_enabled": True
        }
        
        # Fill in defaults
        for key, schema in SETTINGS_SCHEMA.items():
            if key not in test_settings:
                test_settings[key] = schema["default"]
        
        self.settings_manager.save_settings(test_settings)
        
        # Test getting existing setting
        self.assertEqual(self.settings_manager.get_setting("google_api_key"), "test_key")
        self.assertEqual(self.settings_manager.get_setting("login_enabled"), True)
        
        # Test getting non-existent setting with default
        self.assertEqual(self.settings_manager.get_setting("non_existent", "default_value"), "default_value")
    
    def test_update_setting(self):
        """Test updating individual settings"""
        # Create initial settings
        initial_settings = {}
        for key, schema in SETTINGS_SCHEMA.items():
            initial_settings[key] = schema["default"]
        
        self.settings_manager.save_settings(initial_settings)
        
        # Update a setting
        success = self.settings_manager.update_setting("theme", "dark")
        self.assertTrue(success)
        
        # Verify the update
        updated_settings = self.settings_manager.load_settings()
        self.assertEqual(updated_settings["theme"], "dark")
        
        # Test updating unknown setting
        success = self.settings_manager.update_setting("unknown_setting", "value")
        self.assertFalse(success)
    
    def test_reset_settings(self):
        """Test resetting settings to defaults"""
        # Create modified settings
        modified_settings = {}
        for key, schema in SETTINGS_SCHEMA.items():
            if schema["type"] == "boolean":
                modified_settings[key] = not schema["default"]
            elif schema["type"] == "integer":
                modified_settings[key] = schema["default"] + 10
            else:
                modified_settings[key] = "modified_value"
        
        self.settings_manager.save_settings(modified_settings)
        
        # Reset specific settings
        success = self.settings_manager.reset_settings(["theme", "language"])
        self.assertTrue(success)
        
        # Verify reset
        settings = self.settings_manager.load_settings()
        self.assertEqual(settings["theme"], "light")  # Default
        self.assertEqual(settings["language"], "en")  # Default
        
        # Reset all settings
        success = self.settings_manager.reset_settings()
        self.assertTrue(success)
        
        # Verify all are reset
        settings = self.settings_manager.load_settings()
        for key, schema in SETTINGS_SCHEMA.items():
            self.assertEqual(settings[key], schema["default"])
    
    def test_export_settings(self):
        """Test exporting settings"""
        test_settings = {}
        for key, schema in SETTINGS_SCHEMA.items():
            test_settings[key] = schema["default"]
        
        test_settings["google_api_key"] = "secret_key"
        test_settings["login_code"] = "secret_code"
        
        self.settings_manager.save_settings(test_settings)
        
        # Export without sensitive data
        exported = self.settings_manager.export_settings(include_sensitive=False)
        self.assertEqual(exported["google_api_key"], "***masked***")
        self.assertEqual(exported["login_code"], "***masked***")
        self.assertEqual(exported["theme"], "light")
        
        # Export with sensitive data
        exported_with_sensitive = self.settings_manager.export_settings(include_sensitive=True)
        self.assertEqual(exported_with_sensitive["google_api_key"], "secret_key")
        self.assertEqual(exported_with_sensitive["login_code"], "secret_code")
    
    def test_import_settings(self):
        """Test importing settings"""
        import_data = {
            "theme": "dark",
            "language": "es",
            "max_login_attempts": 8
        }
        
        # Test valid import
        success, errors = self.settings_manager.import_settings(import_data)
        self.assertTrue(success)
        self.assertEqual(len(errors), 0)
        
        # Verify import
        settings = self.settings_manager.load_settings()
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["language"], "es")
        self.assertEqual(settings["max_login_attempts"], 8)
        
        # Test invalid import
        invalid_data = {
            "theme": "invalid_theme",
            "unknown_setting": "value"
        }
        success, errors = self.settings_manager.import_settings(invalid_data)
        self.assertFalse(success)
        self.assertGreater(len(errors), 0)


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience functions"""
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.settings_file = os.path.join(self.temp_dir, "test_settings.json")
        
        # Mock the global settings manager
        import settings_config
        self.original_manager = settings_config._settings_manager
        settings_config._settings_manager = SettingsManager(self.settings_file)
    
    def tearDown(self):
        """Clean up test environment"""
        # Restore original manager
        import settings_config
        settings_config._settings_manager = self.original_manager
        
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        os.rmdir(self.temp_dir)
    
    def test_convenience_functions(self):
        """Test the convenience functions work correctly"""
        # Test load_settings
        settings = load_settings()
        self.assertIsInstance(settings, dict)
        
        # Test save_settings
        success = save_settings(settings)
        self.assertTrue(success)
        
        # Test get_setting
        theme = get_setting("theme", "default")
        self.assertIn(theme, ["light", "dark", "default"])
        
        # Test other functions exist and are callable
        self.assertTrue(callable(validate_settings))
        self.assertTrue(callable(reset_settings))
        self.assertTrue(callable(export_settings))
        self.assertTrue(callable(import_settings))


if __name__ == "__main__":
    unittest.main()