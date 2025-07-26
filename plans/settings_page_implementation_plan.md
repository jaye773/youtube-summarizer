# Settings Page Implementation Plan

## Overview
This plan outlines the implementation of a settings page that allows users to configure application settings through a web interface. The settings will be stored in a file and take precedence over environment variables when the application loads.

## Architecture Overview

### 1. Settings File Structure
- **Location**: `data/settings.json` (or `./settings.json` if not in Docker)
- **Format**: JSON for easy serialization/deserialization
- **Permissions**: Read/write access for the application user

### 2. Settings Priority Order
1. Settings file (highest priority)
2. Environment variables (.env file)
3. Default values (lowest priority)

## Implementation Components

### 1. Settings Configuration Module (`settings_config.py`)
Create a new module to handle settings management:

```python
# Key features:
- Load settings from file
- Merge with environment variables
- Provide settings validation
- Handle file I/O operations
- Implement settings schema
```

#### Settings Schema
```python
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
```

### 2. Settings Management Functions

#### Core Functions to Implement:
1. **`load_settings()`**: Load settings from file, merge with env vars
2. **`save_settings(settings_dict)`**: Save settings to file
3. **`get_setting(key, default=None)`**: Get a specific setting
4. **`update_setting(key, value)`**: Update a specific setting
5. **`validate_settings(settings_dict)`**: Validate settings against schema
6. **`reset_settings()`**: Reset to default values
7. **`export_settings()`**: Export settings (excluding sensitive data)
8. **`import_settings(settings_dict)`**: Import settings with validation

### 3. API Endpoints

Add new Flask routes for settings management:

#### GET `/api/settings`
- Returns current settings (with sensitive fields masked)
- Includes metadata (descriptions, types, options)

#### POST `/api/settings`
- Updates settings
- Validates input
- Saves to file
- Returns updated settings

#### GET `/api/settings/schema`
- Returns settings schema for UI generation

#### POST `/api/settings/reset`
- Resets settings to defaults
- Optionally can reset specific settings only

#### GET `/api/settings/export`
- Exports settings (excluding sensitive data)

#### POST `/api/settings/import`
- Imports settings from uploaded file

### 4. Frontend Implementation

#### Settings Page UI (`templates/settings.html`)
Create a new settings page with:

1. **Navigation**: Add settings link to main navigation
2. **Settings Categories**:
   - API Configuration
   - Security Settings
   - Display Preferences
   - Cache Settings
   - Advanced Options

3. **UI Components**:
   - Text inputs for strings
   - Toggle switches for booleans
   - Number inputs for integers
   - Dropdown selects for options
   - Password inputs for sensitive fields
   - Save/Cancel buttons
   - Reset to defaults button
   - Import/Export buttons

4. **Features**:
   - Real-time validation
   - Unsaved changes warning
   - Success/error notifications
   - Loading states
   - Tooltips for descriptions

### 5. Security Considerations

1. **Authentication**: Settings page should require login if LOGIN_ENABLED
2. **Sensitive Data**: 
   - Mask sensitive fields in UI (show dots, provide toggle to view)
   - Exclude sensitive data from exports
   - Encrypt sensitive data in settings file (optional)
3. **Validation**: Strict input validation to prevent injection attacks
4. **File Permissions**: Ensure settings file has appropriate permissions
5. **Audit Trail**: Log settings changes (optional)

### 6. Migration Strategy

1. **On First Run**:
   - Check if settings file exists
   - If not, create from current environment variables
   - Save to settings file

2. **Backward Compatibility**:
   - Continue reading env vars as fallback
   - Provide migration script if needed

### 7. Implementation Steps

#### Phase 1: Backend Infrastructure
1. Create `settings_config.py` module
2. Implement settings schema and validation
3. Add file I/O operations
4. Create settings merger (file + env vars)
5. Update `app.py` to use new settings system

#### Phase 2: API Development
1. Implement `/api/settings` endpoints
2. Add authentication/authorization
3. Implement validation and error handling
4. Add unit tests for API endpoints

#### Phase 3: Frontend Development
1. Create settings page template
2. Implement settings UI components
3. Add JavaScript for dynamic interactions
4. Implement save/load functionality
5. Add validation and error display

#### Phase 4: Integration
1. Update existing code to use new settings system
2. Add settings link to navigation
3. Test all settings combinations
4. Update documentation

#### Phase 5: Testing & Polish
1. Unit tests for settings module
2. Integration tests for settings page
3. UI/UX improvements
4. Performance optimization
5. Security audit

### 8. Code Changes Required

#### Modified Files:
1. **`app.py`**:
   - Import and use settings module
   - Add settings API endpoints
   - Update configuration loading

2. **`templates/index.html`**:
   - Add settings navigation link

3. **`requirements.txt`**:
   - No new dependencies required (using standard library)

#### New Files:
1. **`settings_config.py`**: Settings management module
2. **`templates/settings.html`**: Settings page UI
3. **`static/js/settings.js`**: Settings page JavaScript (if not inline)
4. **`tests/test_settings.py`**: Settings module tests

### 9. Example Settings File Structure

```json
{
  "version": "1.0",
  "settings": {
    "google_api_key": "***masked***",
    "login_enabled": true,
    "login_code": "***masked***",
    "session_secret_key": "***masked***",
    "max_login_attempts": 5,
    "lockout_duration": 15,
    "data_dir": "data",
    "cache_duration": 86400,
    "theme": "light",
    "language": "en",
    "summary_length": "medium"
  },
  "metadata": {
    "last_updated": "2024-01-15T10:30:00Z",
    "updated_by": "admin"
  }
}
```

### 10. Benefits

1. **User-Friendly**: No need to edit files or restart application
2. **Persistent**: Settings survive container restarts
3. **Flexible**: Easy to add new settings
4. **Secure**: Sensitive data handling built-in
5. **Maintainable**: Clear separation of concerns

### 11. Future Enhancements

1. **Multi-user Settings**: Per-user settings profiles
2. **Settings History**: Track changes over time
3. **Settings Templates**: Pre-configured setting sets
4. **Environment-specific Settings**: Dev/staging/prod configurations
5. **Settings Sync**: Backup/restore to cloud services

## Timeline Estimate

- **Phase 1**: 2-3 days (Backend infrastructure)
- **Phase 2**: 1-2 days (API development)
- **Phase 3**: 2-3 days (Frontend development)
- **Phase 4**: 1 day (Integration)
- **Phase 5**: 1-2 days (Testing & polish)

**Total**: 7-11 days for complete implementation

## Success Criteria

1. Settings page accessible and functional
2. Settings persist across restarts
3. Settings override environment variables
4. All existing functionality continues to work
5. No security vulnerabilities introduced
6. Good user experience with clear feedback
7. Comprehensive test coverage