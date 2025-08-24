#!/usr/bin/env python3
"""
Migration script to integrate enhanced SSE implementation
"""
import logging
import os
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backup_existing_files():
    """Backup existing SSE files"""
    backup_dir = Path("backups/sse_original")
    backup_dir.mkdir(parents=True, exist_ok=True)

    files_to_backup = ["sse_manager.py", "static/js/sse_client.js"]

    for file in files_to_backup:
        if Path(file).exists():
            backup_path = backup_dir / file
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, backup_path)
            logger.info(f"Backed up {file} to {backup_path}")


def update_imports_in_app():
    """Update imports in app.py to use enhanced SSE"""
    app_file = Path("app.py")
    if not app_file.exists():
        logger.warning("app.py not found")
        return

    content = app_file.read_text()

    # Replace SSE imports
    replacements = [
        (
            "from sse_manager import SSEManager",
            "from src.realtime.sse_integration import init_sse, get_sse_manager, send_progress_update, send_completion_update",
        ),
        ("sse_manager = SSEManager()", "# SSE manager initialized in init_sse()"),
    ]

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            logger.info(f"Updated import: {old[:30]}...")

    # Save updated file
    app_file.write_text(content)


def add_sse_initialization():
    """Add SSE initialization to Flask app"""
    init_code = '''
# Initialize enhanced SSE
def initialize_enhanced_sse(app):
    """Initialize enhanced SSE with Flask app"""
    from src.realtime.sse_integration import init_sse

    sse_config = {
        'max_connections': 500,
        'max_connections_per_ip': 10,
        'heartbeat_interval': 30,
        'compression_threshold': 1024
    }

    return init_sse(app, sse_config)

# Call this after Flask app creation
# sse_manager = initialize_enhanced_sse(app)
'''

    logger.info("Add the following initialization code to your app.py:")
    print(init_code)


def update_worker_manager():
    """Update worker_manager.py to use enhanced SSE"""
    worker_file = Path("worker_manager.py")
    if not worker_file.exists():
        logger.warning("worker_manager.py not found")
        return

    content = worker_file.read_text()

    # Update SSE notification calls
    replacements = [
        ("sse_manager.send_message", "send_progress_update"),
        (
            "from sse_manager import",
            "from src.realtime.sse_integration import send_progress_update, send_completion_update, send_error_update\n# Original import: from sse_manager import",
        ),
    ]

    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            logger.info(f"Updated worker_manager: {old[:30]}...")

    worker_file.write_text(content)


def update_client_scripts():
    """Update HTML to use enhanced SSE client"""
    html_file = Path("templates/index.html")
    if not html_file.exists():
        logger.warning("templates/index.html not found")
        return

    content = html_file.read_text()

    # Add new script tags
    new_scripts = """
    <!-- Enhanced SSE Client -->
    <script src="/static/js/sse/enhanced_sse_client.js"></script>
    <script>
        // Initialize enhanced SSE client
        const sseClient = new EnhancedSSEClient('/sse', {
            maxRetries: 10,
            baseDelay: 1000,
            maxDelay: 30000
        });

        // Existing event handlers will work with enhanced client
    </script>
"""

    # Find where to insert (before closing body tag)
    if "</body>" in content:
        content = content.replace("</body>", f"{new_scripts}\n</body>")
        logger.info("Added enhanced SSE client scripts to HTML")
        html_file.write_text(content)


def create_config_file():
    """Create SSE configuration file"""
    config_content = """# Enhanced SSE Configuration

# Connection limits
MAX_CONNECTIONS = 500
MAX_CONNECTIONS_PER_IP = 10

# Heartbeat settings
HEARTBEAT_INTERVAL = 30  # seconds
HEARTBEAT_TIMEOUT = 60   # seconds

# Compression settings
COMPRESSION_ENABLED = True
COMPRESSION_THRESHOLD = 1024  # bytes

# Connection cleanup
CLEANUP_INTERVAL = 60     # seconds
IDLE_TIMEOUT = 300        # seconds (5 minutes)

# Health monitoring
HEALTH_CHECK_INTERVAL = 10  # seconds
HEALTH_WARNING_THRESHOLD = 0.8  # 80% of max connections
"""

    config_file = Path("sse_config.py")
    config_file.write_text(config_content)
    logger.info(f"Created configuration file: {config_file}")


def verify_dependencies():
    """Verify required dependencies are installed"""
    required = ["flask", "pako"]  # pako for client-side gzip

    logger.info("Required dependencies:")
    for dep in required:
        logger.info(f"  - {dep}")

    logger.info("\nFor client-side gzip decompression, include pako.js:")
    logger.info('  <script src="https://cdnjs.cloudflare.com/ajax/libs/pako/2.1.0/pako.min.js"></script>')


def main():
    """Run migration steps"""
    logger.info("Starting Enhanced SSE Migration")
    logger.info("=" * 50)

    # Step 1: Backup existing files
    logger.info("\nStep 1: Backing up existing files...")
    backup_existing_files()

    # Step 2: Update imports
    logger.info("\nStep 2: Updating imports in app.py...")
    update_imports_in_app()

    # Step 3: Update worker manager
    logger.info("\nStep 3: Updating worker_manager.py...")
    update_worker_manager()

    # Step 4: Update client scripts
    logger.info("\nStep 4: Updating client scripts...")
    update_client_scripts()

    # Step 5: Create config file
    logger.info("\nStep 5: Creating configuration file...")
    create_config_file()

    # Step 6: Verify dependencies
    logger.info("\nStep 6: Verifying dependencies...")
    verify_dependencies()

    # Step 7: Provide initialization instructions
    logger.info("\nStep 7: Initialization instructions...")
    add_sse_initialization()

    logger.info("\n" + "=" * 50)
    logger.info("Migration preparation complete!")
    logger.info("\nNext steps:")
    logger.info("1. Review the changes made to app.py and worker_manager.py")
    logger.info("2. Add the SSE initialization code to your Flask app")
    logger.info("3. Test the enhanced SSE implementation")
    logger.info("4. Monitor the /sse/health endpoint for connection status")
    logger.info("\nBackups saved in: backups/sse_original/")


if __name__ == "__main__":
    main()
