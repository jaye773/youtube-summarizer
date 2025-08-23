#!/bin/bash

# YouTube Summarizer - Code Quality and Testing Script
# This script runs various code quality checks and tests

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Banner
echo "================================================="
echo "YouTube Summarizer - Code Quality & Testing Suite"
echo "================================================="
echo ""

# Check Python version
print_status "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
print_success "Python version: $python_version"
echo ""

# Install/upgrade development dependencies
print_status "Installing/upgrading development dependencies..."
pip3 install --upgrade pip >/dev/null 2>&1
pip3 install --upgrade -r requirements-dev.txt >/dev/null 2>&1
pip3 install --upgrade black autopep8 isort flake8 pylint >/dev/null 2>&1
print_success "Development dependencies installed"
echo ""

# Option parsing
RUN_ALL=true
RUN_FORMAT=false
RUN_LINT=false
RUN_TESTS=false
RUN_COVERAGE=false
FIX_ISSUES=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --format)
            RUN_FORMAT=true
            RUN_ALL=false
            shift
            ;;
        --lint)
            RUN_LINT=true
            RUN_ALL=false
            shift
            ;;
        --test)
            RUN_TESTS=true
            RUN_ALL=false
            shift
            ;;
        --coverage)
            RUN_COVERAGE=true
            RUN_ALL=false
            shift
            ;;
        --fix)
            FIX_ISSUES=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --format    Run only code formatting checks"
            echo "  --lint      Run only linting checks"
            echo "  --test      Run only tests"
            echo "  --coverage  Run only test coverage"
            echo "  --fix       Automatically fix issues where possible"
            echo "  --help      Show this help message"
            echo ""
            echo "By default (no options), all checks are run"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Step 1: Clean up trailing whitespace and add final newlines
if [ "$RUN_ALL" = true ] || [ "$RUN_FORMAT" = true ]; then
    print_status "Cleaning up whitespace issues..."
    
    # Remove trailing whitespace
    find . -name "*.py" -not -path "./venv/*" -not -path "./htmlcov/*" -exec sed -i '' 's/[[:space:]]*$//' {} \; 2>/dev/null || true
    
    # Add final newlines where missing
    find . -name "*.py" -not -path "./venv/*" -not -path "./htmlcov/*" -exec sh -c 'tail -c1 {} | read -r _ || echo >> {}' \; 2>/dev/null || true
    
    print_success "Whitespace cleanup completed"
    echo ""
fi

# Step 2: Sort imports with isort
if [ "$RUN_ALL" = true ] || [ "$RUN_FORMAT" = true ]; then
    print_status "Sorting imports with isort..."
    
    if [ "$FIX_ISSUES" = true ]; then
        python3 -m isort . --skip venv --skip htmlcov --line-length 120
        print_success "Imports sorted"
    else
        if python3 -m isort . --check-only --diff --skip venv --skip htmlcov --line-length 120; then
            print_success "Import order is correct"
        else
            print_warning "Import order issues found. Run with --fix to auto-fix"
        fi
    fi
    echo ""
fi

# Step 3: Format code with black
if [ "$RUN_ALL" = true ] || [ "$RUN_FORMAT" = true ]; then
    print_status "Checking code formatting with black..."
    
    if [ "$FIX_ISSUES" = true ]; then
        black . --exclude='/(venv|htmlcov)/' --line-length 120
        print_success "Code formatted with black"
    else
        if black . --check --exclude='/(venv|htmlcov)/' --line-length 120; then
            print_success "Code formatting is correct"
        else
            print_warning "Formatting issues found. Run with --fix to auto-format"
        fi
    fi
    echo ""
fi

# Step 4: Run flake8 linting
if [ "$RUN_ALL" = true ] || [ "$RUN_LINT" = true ]; then
    print_status "Running flake8 linting..."
    
    # Create flake8 config if it doesn't exist
    if [ ! -f .flake8 ]; then
        cat > .flake8 << EOF
[flake8]
max-line-length = 120
exclude = venv,htmlcov,.git,__pycache__
ignore = E203,W503,E501
EOF
    fi
    
    if flake8 .; then
        print_success "Flake8 checks passed"
    else
        print_warning "Flake8 found some issues"
    fi
    echo ""
fi

# Step 5: Run pylint
if [ "$RUN_ALL" = true ] || [ "$RUN_LINT" = true ]; then
    print_status "Running pylint..."
    
    # Run pylint on main app
    print_status "Analyzing app.py..."
    pylint_score=$(python3 -m pylint app.py --exit-zero | grep "Your code has been rated at" | awk '{print $7}')
    echo "Pylint score for app.py: $pylint_score"
    
    # Run pylint on tests
    print_status "Analyzing test files..."
    python3 -m pylint tests/*.py --exit-zero | grep "Your code has been rated at" || true
    
    echo ""
fi

# Step 6: Run tests with pytest
if [ "$RUN_ALL" = true ] || [ "$RUN_TESTS" = true ]; then
    print_status "Running tests with pytest..."
    
    # Set testing environment variable
    export TESTING=true
    
    # Run tests with verbose output
    if python3 -m pytest -v; then
        print_success "All tests passed"
    else
        print_error "Some tests failed"
        exit 1
    fi
    echo ""
fi

# Step 7: Run test coverage
if [ "$RUN_ALL" = true ] || [ "$RUN_COVERAGE" = true ]; then
    print_status "Running test coverage analysis..."
    
    # Set testing environment variable
    export TESTING=true
    
    # Run coverage
    python3 -m coverage run -m pytest
    python3 -m coverage report -m
    
    # Generate HTML coverage report
    python3 -m coverage html
    print_success "Coverage report generated in htmlcov/"
    echo ""
fi

# Step 8: Security check with bandit
if [ "$RUN_ALL" = true ] || [ "$RUN_LINT" = true ]; then
    print_status "Running security checks with bandit..."
    
    if python3 -c "import bandit" 2>/dev/null; then
        python3 -m bandit -r . -x /venv/,/htmlcov/,/tests/ -ll || true
        print_success "Security scan completed"
    else
        print_warning "Bandit not installed. Run: pip install bandit"
    fi
    echo ""
fi



# Summary
echo "================================================="
echo "Code Quality Check Summary"
echo "================================================="

if [ "$FIX_ISSUES" = true ]; then
    print_success "Automatic fixes have been applied where possible"
    echo ""
    echo "Fixes applied:"
    echo "  ✓ Trailing whitespace removed"
    echo "  ✓ Missing final newlines added"
    echo "  ✓ Imports sorted with isort"
    echo "  ✓ Code formatted with black"
else
    echo ""
    echo "To automatically fix formatting issues, run:"
    echo "  $0 --fix"
fi

echo ""
echo "For continuous integration, add this script to your CI/CD pipeline"
echo ""

# Create pre-commit hook if .git exists and hook doesn't exist
if [ -d .git ] && [ ! -f .git/hooks/pre-commit ]; then
    print_status "Creating git pre-commit hook..."
    cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
# Pre-commit hook for code quality checks

echo "Running pre-commit checks..."

# Run format checks only (faster for pre-commit)
./run_quality_checks.sh --format

# If format checks fail, prevent commit
if [ $? -ne 0 ]; then
    echo "Pre-commit checks failed. Please fix issues before committing."
    exit 1
fi

echo "Pre-commit checks passed!"
EOF
    chmod +x .git/hooks/pre-commit
    print_success "Git pre-commit hook created"
fi

print_success "Quality checks completed!" 