// login: moved verbatim from the inline <script> in templates/login.html.
// Loaded as a classic script at the end of <body>, so top-level declarations
// are globals (inline onclick handlers rely on that).

const loginForm = document.getElementById('login-form');
const passcodeInput = document.getElementById('passcode');
const loginBtn = document.getElementById('login-btn');
const buttonText = loginBtn.querySelector('.button-text');
const loadingText = loginBtn.querySelector('.loading');
const errorContainer = document.getElementById('error-container');
const infoContainer = document.getElementById('info-container');

// Check URL params for messages
const urlParams = new URLSearchParams(window.location.search);
const error = urlParams.get('error');
const message = urlParams.get('message');

if (error) {
    showError(decodeURIComponent(error));
}

if (message) {
    showInfo(decodeURIComponent(message));
}

function showError(message) {
    // Use textContent (not innerHTML) so query-param messages can't
    // inject markup — these come from the URL and are attacker-controllable.
    errorContainer.innerHTML = '';
    const div = document.createElement('div');
    div.className = 'error-message';
    div.textContent = message;
    errorContainer.appendChild(div);
    infoContainer.innerHTML = '';
}

function showInfo(message) {
    infoContainer.innerHTML = '';
    const div = document.createElement('div');
    div.className = 'info-message';
    div.textContent = message;
    infoContainer.appendChild(div);
    errorContainer.innerHTML = '';
}

function clearMessages() {
    errorContainer.innerHTML = '';
    infoContainer.innerHTML = '';
}

function setLoading(loading) {
    loginBtn.disabled = loading;
    buttonText.style.display = loading ? 'none' : 'inline';
    loadingText.style.display = loading ? 'inline' : 'none';
}

loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const passcode = passcodeInput.value.trim();
    if (!passcode) {
        showError('Please enter your passcode.');
        return;
    }

    setLoading(true);
    clearMessages();

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ passcode: passcode }),
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showInfo('Login successful! Redirecting...');
            // Redirect to home page after successful login
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            showError(data.error || 'Login failed. Please try again.');
            passcodeInput.focus();
        }
    } catch (error) {
        console.error('Login error:', error);
        showError('Connection error. Please check if the server is running.');
    } finally {
        setLoading(false);
    }
});

// Focus on passcode input when page loads
document.addEventListener('DOMContentLoaded', () => {
    passcodeInput.focus();
});

// Clear messages when user starts typing
passcodeInput.addEventListener('input', () => {
    if (errorContainer.innerHTML || infoContainer.innerHTML) {
        clearMessages();
    }
});
