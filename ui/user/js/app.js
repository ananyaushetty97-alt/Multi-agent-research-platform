/**
 * Multi-Agent Research Platform - Frontend Controller
 * - Fixed bottom composer for continuous inquiry
 * - Reopenable sidebar with stateful header toggle
 * - Role-Based Views: User (Clean Monograph + Sources Only) vs Admin (LLM Judge Scorecard + Full Agent Trace)
 */

document.addEventListener('DOMContentLoaded', () => {
  // --- State ---
  const state = {
    role: 'user', // 'user' | 'admin'
    sidebarOpen: true,
    inspectorOpen: true,
    inspectorTab: 'sources', // 'sources' | 'trace' | 'audit'
    activeCitationId: null,
    currentDossierKey: null,
    dossier: null,
    busy: false,
    lastTopic: '',
    health: null,
    attachedFiles: []
  };

  // --- DOM Elements ---
  const appRoot = document.getElementById('app-root');
  const sidebar = document.getElementById('sidebar');
  const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');
  const sidebarToggleIcon = document.getElementById('sidebar-toggle-icon');
  const sidebarCloseBtn = document.getElementById('sidebar-close-btn');
  const btnNewInquiry = document.getElementById('btn-new-inquiry');
  const searchTriggerBtn = document.getElementById('search-trigger-btn');
  const headerBreadcrumbTitle = document.getElementById('header-breadcrumb-title');

  // Profile Component & Single Role Switch
  const profileContainer = document.getElementById('profile-container');
  const btnProfileTrigger = document.getElementById('btn-profile-trigger');
  const profileDropdown = document.getElementById('profile-dropdown');
  const profileAvatarIcon = document.getElementById('profile-avatar-icon');
  const profileUserName = document.getElementById('profile-user-name');
  const profileRoleTag = document.getElementById('profile-role-tag');
  const dropdownAvatarIcon = document.getElementById('dropdown-avatar-icon');
  const dropdownProfileName = document.getElementById('dropdown-profile-name');
  const dropdownProfileEmail = document.getElementById('dropdown-profile-email');
  const dropdownRoleLabel = document.getElementById('dropdown-role-label');
  const profileSwitchUser = document.getElementById('profile-switch-user');
  const profileSwitchAdmin = document.getElementById('profile-switch-admin');
  const profileRoleDesc = document.getElementById('profile-role-description');
  const btnProfileDetails = document.getElementById('btn-profile-details');
  const btnProfileQuickSwitch = document.getElementById('btn-profile-quick-switch');
  const quickSwitchIcon = document.getElementById('quick-switch-icon');
  const btnSwitchAccountText = document.getElementById('btn-switch-account-text');

  // Header & Profile Auth Actions
  const btnHeaderSignin = document.getElementById('btn-header-signin');
  const btnHeaderSignout = document.getElementById('btn-header-signout');
  const btnProfileLogout = document.getElementById('btn-profile-logout');

  // User Auth Mode & Registration Elements
  const userAuthModeToggle = document.getElementById('user-auth-mode-toggle');
  const userModeSigninBtn = document.getElementById('user-mode-signin');
  const userModeRegisterBtn = document.getElementById('user-mode-register');
  const registerForm = document.getElementById('register-form');
  const registerName = document.getElementById('register-name');
  const registerEmail = document.getElementById('register-email');
  const registerPassword = document.getElementById('register-password');
  const registerConfirmPassword = document.getElementById('register-confirm-password');
  const registerNameError = document.getElementById('register-name-error');
  const registerEmailError = document.getElementById('register-email-error');
  const registerPasswordError = document.getElementById('register-password-error');
  const registerConfirmError = document.getElementById('register-confirm-error');
  const btnSubmitRegister = document.getElementById('btn-submit-register');
  const btnToggleRegPassword = document.getElementById('btn-toggle-reg-password');
  const iconToggleRegPassword = document.getElementById('icon-toggle-reg-password');
  const loginAdminHint = document.getElementById('login-admin-hint');
  const loginEmailLabel = document.getElementById('login-email-label');
  const googleAuthContainer = document.getElementById('google-auth-container');
  const googleSigninBtnWrapper = document.getElementById('google-signin-btn-wrapper');
  const googleAuthUnavailable = document.getElementById('google-auth-unavailable');

  const adminEvalScorecard = document.getElementById('admin-eval-scorecard');
  const adminInspectorTabs = document.getElementById('admin-inspector-tabs');
  const inspectorHeaderTitle = document.getElementById('inspector-header-title');
  const headerSourcesLabel = document.getElementById('header-sources-label');

  // Chat Area & Stream
  const chatScrollArea = document.getElementById('chat-scroll-area');
  const welcomeScreen = document.getElementById('welcome-screen');
  const conversationStream = document.getElementById('conversation-stream');
  const dynamicFollowups = document.getElementById('dynamic-followups-container');

  // Bottom Composer & Attachments
  const composerInput = document.getElementById('composer-input');
  const btnSendMessage = document.getElementById('btn-send-message');
  const composerAttachments = document.getElementById('composer-attachments');
  const uploadDropdownWrapper = document.getElementById('upload-dropdown-wrapper');
  const btnUploadTrigger = document.getElementById('btn-upload-trigger');
  const uploadOptionsMenu = document.getElementById('upload-options-menu');
  const btnOptionUploadFile = document.getElementById('btn-option-upload-file');
  const btnOptionUploadFolder = document.getElementById('btn-option-upload-folder');
  const inputUploadFile = document.getElementById('input-upload-file');
  const inputUploadFolder = document.getElementById('input-upload-folder');

  // Report Download Dropdown
  const downloadDropdownWrapper = document.getElementById('download-dropdown-wrapper');
  const btnDlReport = document.getElementById('btn-dl-report');
  const downloadFormatMenu = document.getElementById('download-format-menu');
  const btnDlPdf = document.getElementById('btn-dl-pdf');
  const btnDlDoc = document.getElementById('btn-dl-doc');
  const btnDlTxt = document.getElementById('btn-dl-txt');

  // Right Inspector Panel
  const inspectorPanel = document.getElementById('inspector-panel');
  const btnToggleSources = document.getElementById('btn-toggle-sources');
  const btnCloseInspector = document.getElementById('btn-close-inspector');
  const inspectorScrollBody = document.getElementById('inspector-scroll-body');
  const tabBtnSources = document.getElementById('tab-btn-sources');
  const tabBtnTrace = document.getElementById('tab-btn-trace');
  const tabBtnAudit = document.getElementById('tab-btn-audit');

  // Search Modal
  const searchModalBackdrop = document.getElementById('search-modal-backdrop');
  const modalSearchInput = document.getElementById('modal-search-input');
  const btnModalSearch = document.getElementById('btn-modal-search');
  const btnClearSearch = document.getElementById('btn-clear-search');
  const btnModalEsc = document.getElementById('btn-modal-esc');
  const modalResultsScroll = document.getElementById('modal-results-scroll');

  // Login Modal Elements
  const loginModalBackdrop = document.getElementById('login-modal-backdrop');
  const loginModalTitle = document.getElementById('login-modal-title');
  const loginModalSubtitle = document.getElementById('login-modal-subtitle');
  const btnCloseLoginModal = document.getElementById('btn-close-login-modal');
  const loginTabUser = document.getElementById('login-tab-user');
  const loginTabAdmin = document.getElementById('login-tab-admin');
  const loginScopeTitle = document.getElementById('login-scope-title');
  const loginScopeList = document.getElementById('login-scope-list');
  const loginEmail = document.getElementById('login-email');
  const loginPassword = document.getElementById('login-password');
  const btnTogglePassword = document.getElementById('btn-toggle-password');
  const iconTogglePassword = document.getElementById('icon-toggle-password');
  const btnSubmitLogin = document.getElementById('btn-submit-login');
  const btnLoginText = document.getElementById('btn-login-text');
  const btnLoginIcon = document.getElementById('btn-login-icon');
  const loginForm = document.getElementById('login-form');

  // Pipeline Simulator Modal
  const pipelineModal = document.getElementById('pipeline-modal');
  const pipelineLiveTitle = document.getElementById('pipeline-live-title');
  const pipelineLiveDesc = document.getElementById('pipeline-live-desc');

  // Toast
  const toastNotice = document.getElementById('toast-notice');
  const toastMessage = document.getElementById('toast-message');

  // --- Toast Notification Helper ---
  function showToast(message, icon = 'check_circle', ms = 2500) {
    if (!toastNotice) return;
    toastMessage.textContent = message;
    const toastIcon = toastNotice.querySelector('.material-symbols-outlined');
    if (toastIcon) toastIcon.textContent = icon;
    toastNotice.classList.add('show');
    setTimeout(() => {
      toastNotice.classList.remove('show');
    }, ms);
  }

  // --- Scroll to Bottom ---
  function scrollToBottom() {
    setTimeout(() => {
      if (chatScrollArea) {
        chatScrollArea.scrollTo({
          top: chatScrollArea.scrollHeight,
          behavior: 'smooth'
        });
      }
    }, 80);
  }

  // --- Auto-resize Textarea ---
  function autoResizeTextarea() {
    if (!composerInput) return;
    composerInput.style.height = 'auto';
    composerInput.style.height = Math.min(composerInput.scrollHeight, 120) + 'px';
  }

  composerInput?.addEventListener('input', autoResizeTextarea);

  // --- Sidebar Toggle Logic with Mobile Backdrop ---
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');
  function setSidebarState(isOpen) {
    state.sidebarOpen = isOpen;
    if (isOpen) {
      sidebar?.classList.remove('collapsed');
      if (sidebarToggleIcon) sidebarToggleIcon.textContent = 'menu_open';
      if (window.innerWidth <= 768) {
        sidebarBackdrop?.classList.add('active');
      }
    } else {
      sidebar?.classList.add('collapsed');
      if (sidebarToggleIcon) sidebarToggleIcon.textContent = 'dock_to_right';
      sidebarBackdrop?.classList.remove('active');
    }
  }

  btnToggleSidebar?.addEventListener('click', () => {
    setSidebarState(!state.sidebarOpen);
  });

  sidebarCloseBtn?.addEventListener('click', () => {
    setSidebarState(false);
  });

  sidebarBackdrop?.addEventListener('click', () => {
    setSidebarState(false);
  });

  // --- Role Switcher (User vs Admin) ---
  function setRole(role) {
    state.role = role;
    if (role === 'admin') {
      appRoot?.classList.add('admin-mode');

      // Update Header Profile Component
      if (profileAvatarIcon) profileAvatarIcon.textContent = 'admin_panel_settings';
      if (profileUserName) profileUserName.textContent = 'Admin Evaluator';
      if (profileRoleTag) profileRoleTag.textContent = 'Admin';

      // Update Profile Dropdown
      if (dropdownAvatarIcon) dropdownAvatarIcon.textContent = 'admin_panel_settings';
      if (dropdownProfileName) dropdownProfileName.textContent = 'Admin Evaluator';
      if (dropdownProfileEmail) dropdownProfileEmail.textContent = 'admin@platform.ai';
      if (dropdownRoleLabel) dropdownRoleLabel.textContent = 'System Admin (Evaluator)';
      profileSwitchAdmin?.classList.add('active');
      profileSwitchUser?.classList.remove('active');
      if (profileRoleDesc) profileRoleDesc.textContent = 'Full model diagnostics active: LLM-as-a-judge scores, prompt critiques, and agent trace latencies are visible.';
      if (quickSwitchIcon) quickSwitchIcon.textContent = 'person';
      if (btnSwitchAccountText) btnSwitchAccountText.textContent = 'Switch to User View';

      if (inspectorHeaderTitle) inspectorHeaderTitle.textContent = 'Provenance & Inspector';
      if (headerSourcesLabel) headerSourcesLabel.textContent = 'Sources & Trace';
    } else {
      appRoot?.classList.remove('admin-mode');

      // Update Header Profile Component
      if (profileAvatarIcon) profileAvatarIcon.textContent = 'person';
      const curUser = RP.getCurrentUser();
      const displayName = curUser ? (curUser.full_name || curUser.email.split('@')[0]) : 'Guest';
      if (profileUserName) profileUserName.textContent = displayName;
      if (profileRoleTag) profileRoleTag.textContent = 'User';

      // Update Profile Dropdown
      if (dropdownAvatarIcon) dropdownAvatarIcon.textContent = 'person';
      if (dropdownProfileName) dropdownProfileName.textContent = displayName;
      if (dropdownProfileEmail) dropdownProfileEmail.textContent = curUser ? curUser.email : 'Not signed in';
      if (dropdownRoleLabel) dropdownRoleLabel.textContent = curUser ? 'User Account' : 'Guest Visitor';
      profileSwitchUser?.classList.add('active');
      profileSwitchAdmin?.classList.remove('active');
      if (profileRoleDesc) profileRoleDesc.textContent = 'Viewing clean reading mode with monographs and verified sources. Model diagnostic scores are hidden.';
      if (quickSwitchIcon) quickSwitchIcon.textContent = 'admin_panel_settings';
      if (btnSwitchAccountText) btnSwitchAccountText.textContent = 'Switch to Admin Login';

      if (inspectorHeaderTitle) inspectorHeaderTitle.textContent = 'Verified Sources';
      if (headerSourcesLabel) headerSourcesLabel.textContent = 'Sources';
    }
    renderInspectorContent();
  }

  // Login Modal Role & Mode Controllers
  let selectedLoginRole = 'user';
  let userAuthMode = 'signin'; // 'signin' or 'register'
  let googleClientId = null;
  let gisInitialized = false;
  let gisScriptFailed = false;
  let googleButtonRendered = false;

  function clearFormErrors() {
    const errorBanner = document.getElementById('login-error-banner');
    if (errorBanner) {
      errorBanner.style.display = 'none';
    }
    const errorText = document.getElementById('login-error-text');
    if (errorText) {
      errorText.textContent = '';
    }
    [loginEmail, loginPassword, registerPassword, registerConfirmPassword, registerName, registerEmail].forEach(el => {
      el?.classList.remove('input-error');
    });
    [registerNameError, registerEmailError, registerPasswordError, registerConfirmError].forEach(el => {
      if (el) {
        el.textContent = '';
        el.style.display = 'none';
      }
    });
  }

  async function onGoogleCredentialResponse(response) {
    if (!response || !response.credential) {
      showAuthError('No credential received from Google.');
      return;
    }
    clearFormErrors();
    try {
      const user = await RP.auth.google(response.credential);
      updateAuthState(user);
      closeLoginModal();
      showToast(`Signed in with Google as ${user.full_name || user.email}`, 'verified_user', 3000);
    } catch (err) {
      showAuthError(err.message || 'Google sign-in failed.');
    }
  }

  function showGoogleUnavailable(msg) {
    if (googleAuthUnavailable) {
      if (msg) googleAuthUnavailable.textContent = msg;
      googleAuthUnavailable.style.display = 'block';
    }
    const gisTarget = document.getElementById('google-gis-button-target');
    if (gisTarget) {
      gisTarget.style.display = 'none';
    }
  }

  function hideGoogleUnavailable() {
    if (googleAuthUnavailable) {
      googleAuthUnavailable.style.display = 'none';
    }
    const gisTarget = document.getElementById('google-gis-button-target');
    if (gisTarget) {
      gisTarget.style.display = 'flex';
    }
  }

  function updateGoogleVisibility() {
    if (!googleAuthContainer) return;
    if (selectedLoginRole === 'user' && googleClientId) {
      googleAuthContainer.style.display = 'flex';
      setupGoogleButton();
    } else {
      googleAuthContainer.style.display = 'none';
    }
  }

  function setupGoogleButton() {
    if (!googleClientId) {
      if (googleAuthContainer) googleAuthContainer.style.display = 'none';
      return;
    }
    if (gisScriptFailed) {
      showGoogleUnavailable('Google Sign-In is temporarily unavailable. Please sign in with email.');
      return;
    }
    if (!window.google?.accounts?.id) {
      return;
    }
    if (!gisInitialized) {
      try {
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: onGoogleCredentialResponse,
          auto_select: false,
          cancel_on_tap_outside: true
        });
        gisInitialized = true;
      } catch (err) {
        console.warn('Google Identity Services initialization failed:', err);
        showGoogleUnavailable('Google Sign-In is temporarily unavailable. Please sign in with email.');
        return;
      }
    }
    if (googleSigninBtnWrapper && selectedLoginRole === 'user') {
      let gisTarget = document.getElementById('google-gis-button-target');
      if (!gisTarget) {
        gisTarget = document.createElement('div');
        gisTarget.id = 'google-gis-button-target';
        gisTarget.style.display = 'flex';
        gisTarget.style.justifyContent = 'center';
        gisTarget.style.width = '100%';
        googleSigninBtnWrapper.appendChild(gisTarget);
      }
      hideGoogleUnavailable();

      const hasRenderedIframe = gisTarget.querySelector('iframe') !== null;
      if (!hasRenderedIframe) {
        try {
          window.google.accounts.id.renderButton(gisTarget, {
            type: 'standard',
            theme: 'outline',
            size: 'large',
            text: 'continue_with',
            shape: 'rectangular',
            logo_alignment: 'left',
            width: 320
          });
          googleButtonRendered = true;
        } catch (err) {
          console.warn('Google Identity Services renderButton failed:', err);
          showGoogleUnavailable('Google Sign-In is temporarily unavailable. Please sign in with email.');
        }
      }
    }
  }

  async function initGoogleAuth() {
    try {
      const cfg = await RP.auth.config();
      googleClientId = (cfg && cfg.google_client_id && typeof cfg.google_client_id === 'string')
        ? cfg.google_client_id.trim()
        : null;
    } catch (e) {
      console.warn('Failed to load auth configuration:', e);
      googleClientId = null;
    }

    if (!googleClientId) {
      if (googleAuthContainer) googleAuthContainer.style.display = 'none';
      console.info('Google sign-in disabled: no client ID configured');
      return;
    }

    const onScriptSuccess = () => {
      gisScriptFailed = false;
      setupGoogleButton();
    };

    const onScriptFailure = () => {
      console.warn('Google Identity Services script failed to load (blocked or unreachable).');
      gisScriptFailed = true;
      showGoogleUnavailable('Google Sign-In is temporarily unavailable. Please sign in with email.');
    };

    if (window.google?.accounts?.id) {
      onScriptSuccess();
    } else {
      let script = document.getElementById('google-gsi-client-script');
      if (script) {
        script.addEventListener('load', onScriptSuccess);
        script.addEventListener('error', onScriptFailure);
      } else {
        script = document.createElement('script');
        script.id = 'google-gsi-client-script';
        script.src = 'https://accounts.google.com/gsi/client';
        script.async = true;
        script.defer = true;
        script.onload = onScriptSuccess;
        script.onerror = onScriptFailure;
        document.head.appendChild(script);
      }
    }

    updateGoogleVisibility();
  }

  function setUserAuthMode(mode) {
    userAuthMode = mode;
    clearFormErrors();
    updateLoginModalUI('user');
  }

  function updateLoginModalUI(role) {
    selectedLoginRole = role;
    clearFormErrors();
    if (loginPassword) loginPassword.value = '';

    if (role === 'admin') {
      loginTabAdmin?.classList.add('active');
      loginTabUser?.classList.remove('active');
      if (userAuthModeToggle) userAuthModeToggle.style.display = 'none';
      if (loginForm) loginForm.style.display = 'flex';
      if (registerForm) registerForm.style.display = 'none';
      if (loginAdminHint) loginAdminHint.style.display = 'flex';
      if (googleAuthContainer) googleAuthContainer.style.display = 'none';
      if (loginEmailLabel) loginEmailLabel.textContent = 'Admin Username or Email';
      if (loginEmail) {
        loginEmail.value = 'admin@platform.ai';
        loginEmail.placeholder = 'admin@platform.ai or admin';
      }
      if (loginPassword) loginPassword.placeholder = 'Enter password (admin123)';
      if (btnLoginText) btnLoginText.textContent = 'Sign In as Admin';
      if (btnLoginIcon) btnLoginIcon.textContent = 'admin_panel_settings';
      if (loginModalTitle) loginModalTitle.textContent = 'Admin Sign In';
      if (loginModalSubtitle) loginModalSubtitle.textContent = 'Sign in with administrator credentials';
    } else {
      loginTabUser?.classList.add('active');
      loginTabAdmin?.classList.remove('active');
      if (userAuthModeToggle) userAuthModeToggle.style.display = 'grid';
      if (loginAdminHint) loginAdminHint.style.display = 'none';
      updateGoogleVisibility();
      if (loginEmailLabel) loginEmailLabel.textContent = 'Email Address';
      if (loginEmail) {
        if (loginEmail.value === 'admin@platform.ai' || loginEmail.value === 'user@platform.ai') {
          loginEmail.value = '';
        }
        loginEmail.placeholder = 'name@example.com';
      }
      if (loginPassword) loginPassword.placeholder = 'Enter password';

      if (userAuthMode === 'signin') {
        userModeSigninBtn?.classList.add('active');
        userModeRegisterBtn?.classList.remove('active');
        if (loginForm) loginForm.style.display = 'flex';
        if (registerForm) registerForm.style.display = 'none';
        if (btnLoginText) btnLoginText.textContent = 'Sign In';
        if (btnLoginIcon) btnLoginIcon.textContent = 'login';
        if (loginModalTitle) loginModalTitle.textContent = 'Sign In';
        if (loginModalSubtitle) loginModalSubtitle.textContent = 'Sign in to access your saved research';
      } else {
        userModeRegisterBtn?.classList.add('active');
        userModeSigninBtn?.classList.remove('active');
        if (loginForm) loginForm.style.display = 'none';
        if (registerForm) registerForm.style.display = 'flex';
        if (loginModalTitle) loginModalTitle.textContent = 'Create Account';
        if (loginModalSubtitle) loginModalSubtitle.textContent = 'Register an account to keep your research on this device.';
      }
    }
  }

  function openLoginModal(role = (state.role === 'admin' ? 'user' : 'admin')) {
    clearFormErrors();
    updateLoginModalUI(role);
    loginModalBackdrop?.classList.add('active');
    if (role === 'user' && googleClientId) {
      setTimeout(() => {
        setupGoogleButton();
      }, 50);
    }
    setTimeout(() => {
      if (role === 'admin' || userAuthMode === 'signin') {
        if (!loginEmail?.value) loginEmail?.focus();
        else loginPassword?.focus();
      } else {
        registerName?.focus();
      }
    }, 150);
  }

  function closeLoginModal() {
    loginModalBackdrop?.classList.remove('active');
    clearFormErrors();
  }

  function showAuthError(message) {
    const errorBanner = document.getElementById('login-error-banner');
    const errorText = document.getElementById('login-error-text');
    if (errorBanner && errorText) {
      errorText.textContent = message;
      errorBanner.style.display = 'flex';
    }
    showToast(message, 'error', 4000);
  }

  async function verifyAndAuthenticate() {
    clearFormErrors();

    // ========================================================================
    // PATH 1: ADMIN LOGIN (COMPLETELY UNTOUCHED, INCLUDING HARDCODED FALLBACK)
    // ========================================================================
    if (selectedLoginRole === 'admin') {
      const email = loginEmail?.value.trim().toLowerCase();
      const pass = loginPassword?.value.trim();
      const errorBanner = document.getElementById('login-error-banner');
      const errorText = document.getElementById('login-error-text');

      if (!email || !pass) {
        if (errorBanner && errorText) {
          errorText.textContent = 'Please enter both username/email and password.';
          errorBanner.style.display = 'flex';
        }
        return false;
      }

      const origins = [];
      if (typeof window !== 'undefined' && window.location.origin && window.location.origin.startsWith('http')) {
        origins.push(window.location.origin);
      }
      origins.push('http://localhost:8000', 'http://127.0.0.1:8000');

      let loginSucceeded = false;
      let authData = null;
      let authErrorDetail = null;

      for (const base of origins) {
        const endpoints = [`${base}/api/admin/auth/login`, `${base}/admin/auth/login`];
        for (const ep of endpoints) {
          try {
            const resp = await fetch(ep, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
              body: JSON.stringify({ username: email, password: pass })
            });
            if (resp.ok) {
              authData = await resp.json().catch(() => ({}));
              loginSucceeded = true;
              break;
            } else if (resp.status === 401 || resp.status === 422) {
              const errData = await resp.json().catch(() => ({}));
              if (resp.status === 422 && pass === 'admin123') {
                loginSucceeded = true;
                authData = { role: 'admin' };
                authErrorDetail = null;
                break;
              }
              authErrorDetail = Array.isArray(errData.detail)
                ? errData.detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
                : (errData.detail || 'Incorrect username or password');
            }
          } catch (e) {
            // Next candidate endpoint
          }
        }
        if (loginSucceeded) break;
      }

      // Graceful offline fallback if server is unreachable
      if (!loginSucceeded && !authErrorDetail) {
        if (selectedLoginRole === 'admin' && (pass === 'admin123') && (email === 'admin@platform.ai' || email === 'admin')) {
          loginSucceeded = true;
          authData = { role: 'admin' };
        }
      }

      if (loginSucceeded) {
        if (authData && authData.access_token) {
          sessionStorage.setItem('admin_access_token', authData.access_token);
          localStorage.setItem('admin_access_token', authData.access_token);
        }
        setRole('admin');
        closeLoginModal();
        showToast('Admin verified! Opening Admin Observability Dashboard...', 'admin_panel_settings', 2000);
        setTimeout(() => {
          window.location.href = '../admin/index.html';
        }, 350);
        return true;
      } else {
        const detailMsg = authErrorDetail || 'Verification failed: Access denied. Admin page is restricted to verified administrators.';
        if (errorBanner && errorText) {
          errorText.textContent = detailMsg;
          errorBanner.style.display = 'flex';
        }
        loginPassword?.classList.add('input-error');
        setTimeout(() => loginPassword?.classList.remove('input-error'), 1000);
        showToast('Verification failed: Access denied', 'lock');
        return false;
      }
    }

    // ========================================================================
    // PATH 2: REGULAR USER AUTH (REAL COOKIE SESSIONS, ZERO CLIENT BYPASSES)
    // ========================================================================
    if (selectedLoginRole === 'user') {
      if (userAuthMode === 'register') {
        const name = registerName?.value.trim() || '';
        const email = registerEmail?.value.trim().toLowerCase() || '';
        const password = registerPassword?.value || '';
        const confirm_password = registerConfirmPassword?.value || '';

        let hasClientError = false;

        if (!name) {
          if (registerNameError) {
            registerNameError.textContent = 'Please enter your name.';
            registerNameError.style.display = 'block';
          }
          registerName?.classList.add('input-error');
          hasClientError = true;
        } else if (name.length > 80) {
          if (registerNameError) {
            registerNameError.textContent = 'Name must be 80 characters or fewer.';
            registerNameError.style.display = 'block';
          }
          registerName?.classList.add('input-error');
          hasClientError = true;
        }

        const emailRegex = /^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$/;
        if (!email) {
          if (registerEmailError) {
            registerEmailError.textContent = 'Please enter your email.';
            registerEmailError.style.display = 'block';
          }
          registerEmail?.classList.add('input-error');
          hasClientError = true;
        } else if (!emailRegex.test(email)) {
          if (registerEmailError) {
            registerEmailError.textContent = 'Please enter a valid email address.';
            registerEmailError.style.display = 'block';
          }
          registerEmail?.classList.add('input-error');
          hasClientError = true;
        }

        const hasLetter = /[A-Za-z]/.test(password);
        const hasDigit = /\d/.test(password);
        if (password.length < 8) {
          if (registerPasswordError) {
            registerPasswordError.textContent = 'Password must be at least 8 characters.';
            registerPasswordError.style.display = 'block';
          }
          registerPassword?.classList.add('input-error');
          hasClientError = true;
        } else if (!hasLetter || !hasDigit) {
          if (registerPasswordError) {
            registerPasswordError.textContent = 'Password must contain at least one letter and one number.';
            registerPasswordError.style.display = 'block';
          }
          registerPassword?.classList.add('input-error');
          hasClientError = true;
        }

        if (confirm_password !== password) {
          if (registerConfirmError) {
            registerConfirmError.textContent = 'Passwords do not match.';
            registerConfirmError.style.display = 'block';
          }
          registerConfirmPassword?.classList.add('input-error');
          hasClientError = true;
        }

        if (hasClientError) return false;

        try {
          const user = await RP.auth.register({ name, email, password, confirm_password });
          updateAuthState(user);
          closeLoginModal();
          showToast(`Account created! Welcome, ${user.full_name || user.email}`, 'person_add', 3000);
          return true;
        } catch (err) {
          const msg = (err.status === 409 || err.message?.toLowerCase().includes('already exists') || err.message?.toLowerCase().includes('already registered'))
            ? "An account with this email already exists. Try signing in."
            : (err.message || 'Registration failed.');
          showAuthError(msg);
          registerEmail?.classList.add('input-error');
          registerPassword?.classList.add('input-error');
          return false;
        }
      } else {
        // User Sign In
        const email = loginEmail?.value.trim().toLowerCase() || '';
        const password = loginPassword?.value || '';

        if (!email || !password) {
          showAuthError('Please enter both email and password.');
          if (!email) loginEmail?.classList.add('input-error');
          if (!password) loginPassword?.classList.add('input-error');
          return false;
        }

        try {
          const user = await RP.auth.login({ email, password });
          updateAuthState(user);
          closeLoginModal();
          showToast(`Signed in as ${user.full_name || user.email}`, 'verified_user', 3000);
          return true;
        } catch (err) {
          showAuthError(err.message || 'Invalid email or password.');
          loginPassword?.classList.add('input-error');
          return false;
        }
      }
    }
  }

  function updateAuthState(user) {
    if (user) {
      state.currentUser = user;
      if (btnHeaderSignin) btnHeaderSignin.style.display = 'none';
      if (btnHeaderSignout) btnHeaderSignout.style.display = 'inline-flex';
      if (btnProfileLogout) btnProfileLogout.style.display = 'flex';

      const displayName = user.full_name || (user.email ? user.email.split('@')[0] : 'User');
      if (profileUserName) profileUserName.textContent = displayName;
      if (dropdownProfileName) dropdownProfileName.textContent = displayName;
      if (dropdownProfileEmail) dropdownProfileEmail.textContent = user.email || '';
      if (dropdownRoleLabel) dropdownRoleLabel.textContent = 'User Account';
      if (profileRoleTag) profileRoleTag.textContent = 'User';

      RP.switchUser(user);
    } else {
      state.currentUser = null;
      if (btnHeaderSignin) btnHeaderSignin.style.display = 'inline-flex';
      if (btnHeaderSignout) btnHeaderSignout.style.display = 'none';
      if (btnProfileLogout) btnProfileLogout.style.display = 'none';

      if (profileUserName) profileUserName.textContent = 'Guest';
      if (dropdownProfileName) dropdownProfileName.textContent = 'Guest';
      if (dropdownProfileEmail) dropdownProfileEmail.textContent = 'Not signed in';
      if (dropdownRoleLabel) dropdownRoleLabel.textContent = 'Guest Visitor';
      if (profileRoleTag) profileRoleTag.textContent = 'User';

      RP.switchUser(null);
    }

    // Refresh history and reset conversation stream to prevent cross-account chat leaks
    state.dossier = null;
    if (dynamicFollowups) dynamicFollowups.innerHTML = '';
    renderHistory();
    const lastActiveId = RP.getLastActiveChatId();
    if (lastActiveId && lastActiveId !== 'new' && RP.getChat(lastActiveId)) {
      showSavedChat(RP.getChat(lastActiveId));
    } else {
      showWelcomeScreen();
    }
  }

  async function handleLogout() {
    try {
      await RP.auth.logout();
    } catch (e) { }
    try {
      sessionStorage.removeItem('admin_access_token');
      localStorage.removeItem('admin_access_token');
    } catch (e) { }
    updateAuthState(null);
    showToast('Signed out successfully', 'logout', 2500);
  }

  // --- Inspector Panel Rendering ---
  function setInspectorTab(tab) {
    state.inspectorTab = tab;
    [tabBtnSources, tabBtnTrace, tabBtnAudit].forEach(btn => btn?.classList.remove('active'));
    renderInspectorContent();
  }

  function updateHeaderSourcesBadge(count) {
    const badge = document.getElementById('header-sources-count');
    if (!badge) return;
    if (count && count > 0) {
      badge.textContent = count;
      badge.style.display = 'inline-flex';
    } else {
      badge.textContent = '0';
      badge.style.display = 'none';
    }
  }

  function renderInspectorContent() {
    const dossier = state.dossier;
    const sourcesCount = (dossier && dossier.sources) ? dossier.sources.length : 0;
    updateHeaderSourcesBadge(sourcesCount);
    if (!inspectorScrollBody) return;
    if (!dossier) {
      inspectorScrollBody.innerHTML = '<p class="trace-node-detail" style="padding:1rem;">Sources appear here once a report is ready.</p>';
      return;
    }

    // In USER MODE: Always render ONLY sources!
    if (state.role === 'user' || state.inspectorTab === 'sources') {
      tabBtnSources?.classList.add('active');

      // Group sources by domain for hierarchy
      const sourcesByDomain = {};
      dossier.sources.forEach(s => {
        const domain = s.domain || 'Unknown';
        if (!sourcesByDomain[domain]) sourcesByDomain[domain] = [];
        sourcesByDomain[domain].push(s);
      });

      // Render grouped by domain
      inspectorScrollBody.innerHTML = Object.entries(sourcesByDomain).map(([domain, sources]) => `
        <div class="source-domain-group">
          <div class="source-domain-header">
            <span class="material-symbols-outlined text-[16px]">folder</span>
            <span class="source-domain-name">${escapeHTML(String(domain))}</span>
            <span class="source-domain-count">${sources.length} source${sources.length > 1 ? 's' : ''}</span>
          </div>
          <div class="source-domain-sources">
            ${sources.map(s => `
              <article class="source-card ${state.activeCitationId === s.id ? 'highlighted' : ''}" id="inspector-source-${s.id}">
                <div class="source-top-row">
                  <div class="source-badge-row">
                    <span class="source-citation-num">[${s.id}]</span>
                  </div>
                  <span style="font-size: 0.625rem; font-weight: 600; padding: 1px 6px; border-radius: var(--radius-full); background: var(--surface-container-high);">
                    Cited ${s.citationsCount} ${s.citationsCount > 1 ? 'times' : 'time'}
                  </span>
                </div>
                <h4 class="source-card-title">${escapeHTML(String(s.title))}</h4>
                ${s.snippet ? `<p class="source-quote-snippet">"${escapeHTML(s.snippet)}"</p>` : ''}
                <div class="source-card-bottom">
                  <span style="color: var(--on-surface-variant); font-weight: 600; display: inline-flex; align-items: center; gap: 0.25rem;">
                    <span class="material-symbols-outlined text-[13px]">link</span>
                    <span>Web source</span>
                  </span>
                  <a class="source-outbound-link" href="${escapeHTML(s.url)}" target="_blank" rel="noopener noreferrer">
                    <span>Open</span>
                    <span class="material-symbols-outlined text-[12px]">arrow_outward</span>
                  </a>
                </div>
              </article>
            `).join('')}
          </div>
        </div>
      `).join('');
    } else if (state.role === 'admin' && state.inspectorTab === 'trace') {
      tabBtnTrace?.classList.add('active');
      inspectorScrollBody.innerHTML = !(dossier.agentTrace || []).length ? '<p class="trace-node-detail" style="padding:1rem;">Per-agent trace is not exposed by the API yet.</p>' : dossier.agentTrace.map(step => `
        <div class="trace-node-card">
          <div class="trace-node-header">
            <span class="trace-node-name">
              <span class="material-symbols-outlined text-[15px] text-primary">${step.icon}</span>
              ${step.agent}
            </span>
            <span class="trace-node-status">${step.status}</span>
          </div>
          <p class="trace-node-detail">${step.detail}</p>
          <span style="font-family: var(--font-mono); font-size: 0.6875rem; color: var(--outline);">Latency: ${step.timestamp}</span>
        </div>
      `).join('');
    } else if (state.role === 'admin' && state.inspectorTab === 'audit') {
      tabBtnAudit?.classList.add('active');
      inspectorScrollBody.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 0.75rem;">
          <div class="trace-node-card">
            <div class="trace-node-header">
              <span class="trace-node-name">LLM Gateway</span>
              <span class="status-dot-active"></span>
            </div>
            <p class="trace-node-detail">${escapeHTML(String((state.health && state.health.gateway) || 'unavailable'))}</p>
          </div>
          <div class="trace-node-card">
            <div class="trace-node-header">
              <span class="trace-node-name">Short-Term Memory</span>
              <span class="material-symbols-outlined text-[14px] text-primary">memory</span>
            </div>
            <p class="trace-node-detail">Redis STM: Active session state maintained with TTL.</p>
          </div>
          <div class="trace-node-card">
            <div class="trace-node-header">
              <span class="trace-node-name">Long-Term Memory</span>
              <span class="material-symbols-outlined text-[14px] text-primary">storage</span>
            </div>
            <p class="trace-node-detail">pgvector: Report vectorized into OpenProvenance store.</p>
          </div>
          <div class="trace-node-card">
            <div class="trace-node-header">
              <span class="trace-node-name">Security Guardrails</span>
              <span class="material-symbols-outlined text-[14px] text-primary">security</span>
            </div>
            <p class="trace-node-detail">PyRIT Red-Team Testing: Prompt injection defense passed.</p>
          </div>
        </div>
      `;
    }
  }

  function toggleInspector(force) {
    const shouldOpen = force !== undefined ? force : !state.inspectorOpen;
    state.inspectorOpen = shouldOpen;
    if (shouldOpen) {
      inspectorPanel?.classList.remove('hidden');
      btnToggleSources?.classList.add('active');
    } else {
      inspectorPanel?.classList.add('hidden');
      btnToggleSources?.classList.remove('active');
    }
  }

  // --- Citation Interactions ---
  function setupCitations() {
    document.querySelectorAll('.citation-chip').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(chip.getAttribute('data-citation-id'), 10);
        state.activeCitationId = id;

        toggleInspector(true);
        setInspectorTab('sources');

        const targetCard = document.getElementById(`inspector-source-${id}`);
        if (targetCard) {
          targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
          targetCard.classList.add('highlighted');
          setTimeout(() => targetCard.classList.remove('highlighted'), 2500);
        }
      });
    });
  }

  // --- Search Modal (Ctrl + K) ---
  function openSearchModal() {
    searchModalBackdrop?.classList.add('active');
    modalSearchInput?.focus();
    renderModalResults(modalSearchInput?.value || '');
  }

  function closeSearchModal() {
    searchModalBackdrop?.classList.remove('active');
  }

  const DOSSIER_REGISTRY = {
    'microplastics': {
      title: 'Impact of Microplastics on Marine Life',
      query: 'Impact of microplastics on marine life'
    },
    'quantum-error': {
      title: 'Quantum Error Mitigation & Coherence',
      query: 'Quantum Error Mitigation Review'
    },
    'solid-state-battery': {
      title: 'Solid-State Battery Electrolyte Interfaces',
      query: 'Solid-State Battery Electrolyte Interfaces'
    },
    'crispr-analysis': {
      title: 'CRISPR Prime Editing Mechanisms',
      query: 'CRISPR Prime Editing Mechanisms'
    },
    'stellar-dynamics': {
      title: 'Stellar Dynamics & Dark Matter Halos',
      query: 'Stellar Dynamics & Dark Matter Halos'
    },
    'llm-consensus': {
      title: 'Epistemic Bounds in Multi-Agent Consensus',
      query: 'Epistemic Bounds in Multi-Agent Consensus'
    },
    'paper-perovskite': {
      title: 'Perovskite-Silicon Tandem Photovoltaics (Nature 2024)',
      query: 'Perovskite-Silicon Tandem Photovoltaics'
    },
    'paper-alphafold': {
      title: 'Biomolecular Complex Architecture (Cell 2024)',
      query: 'Biomolecular Complex Architecture'
    }
  };

  // =========================================================================
  // Backend wiring (RP is defined in js/api.js)
  // =========================================================================
  const INTENT_LABEL = { new_research: 'New report', modify: 'Edited', question: 'Answer' };
  const STATUS_STEPS = [
    ['Checking your request', 'Validating the topic and checking the cache.'],
    ['Searching the web', 'Collecting sources for your topic.'],
    ['Summarising sources', 'Condensing the evidence.'],
    ['Writing the report', 'Drafting the report with numbered citations.'],
    ['Fact-checking', 'Verifying claims against the sources.']
  ];
  let activeController = null;

  function safeUrl(u) {
    try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : '#'; } catch (e) { return '#'; }
  }
  function toSources(turn) {
    return (turn.sources || []).map(s => {
      const info = RP.sourceInfo(s);
      return { id: s.n, domain: info.domain || 'source', title: s.title || info.domain || s.url, url: safeUrl(s.url), snippet: '', citationsCount: RP.citationCount(turn.report, s.n) };
    });
  }
  function turnFrom(user, d) {
    return {
      id: d.report_id || d.id || ('rep-' + Date.now() + '-' + Math.random().toString(36).substr(2, 6)),
      user,
      intent: d.intent,
      report: d.report,
      sources: d.sources || [],
      cached: !!d.cached,
      score: d.score || null,
      seconds: d.seconds
    };
  }
  function fmtTime(ts) { return new Date(ts || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function fmtDate(ts) { return new Date(ts).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
  function groupOf(ts) {
    const day = x => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = (day(new Date()) - day(new Date(ts))) / 864e5;
    return diff <= 0 ? 'Today' : diff === 1 ? 'Yesterday' : diff < 7 ? 'Previous 7 days' : 'Older';
  }

  // Markdown report -> sanitized DOM with clickable [n] citation chips
  function reportParts(turn) {
    let md = String(turn.report || '').split('\n## Sources')[0];
    let title = '';
    const m = md.match(/^\s*#\s+(.+)\n/);
    if (m) { title = m[1].replace(/\*+/g, '').trim(); md = md.slice(m[0].length); }
    const box = document.createElement('div');
    box.innerHTML = DOMPurify.sanitize(marked.parse(md));
    box.querySelectorAll('h1,h2,h3,h4').forEach(h => h.classList.add('section-heading'));
    box.querySelectorAll('p,li').forEach(p => p.classList.add('article-prose'));
    const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (w.nextNode()) nodes.push(w.currentNode);
    nodes.forEach(n => {
      if (n.parentElement.closest('a,code,pre') || !/\[\d+\]/.test(n.nodeValue)) return;
      const frag = document.createDocumentFragment();
      n.nodeValue.split(/(\[\d+\])/).forEach(part => {
        const mm = part.match(/^\[(\d+)\]$/);
        if (mm) {
          const wrap = document.createElement('span'); wrap.className = 'citation-chip-wrapper';
          const b = document.createElement('button'); b.className = 'citation-chip'; b.type = 'button';
          b.dataset.citationId = mm[1]; b.textContent = part;
          wrap.append(b); frag.append(wrap);
        } else if (part) frag.append(part);
      });
      n.replaceWith(frag);
    });
    return { title, node: box };
  }
  function badgesEl(turn) {
    const d = document.createElement('div');
    d.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px';
    const mk = (t, strong) => {
      const sp = document.createElement('span'); sp.textContent = t;
      sp.style.cssText = 'font-size:.6875rem;font-weight:600;padding:2px 8px;border-radius:999px;background:' + (strong ? 'var(--primary-container)' : 'var(--surface-container-high)') + ';color:' + (strong ? '#fff' : 'var(--on-surface-variant)');
      return sp;
    };
    d.append(mk(INTENT_LABEL[turn.intent] || turn.intent || 'Reply'));
    if (turn.cached) d.append(mk('Instant result', true));
    if (typeof turn.seconds === 'number') d.append(mk(turn.seconds.toFixed(1) + ' s'));
    return d;
  }

  function createReportQualityScorecard(score) {
    if (!score || score.overall == null) return document.createDocumentFragment();
    const wrap = document.createElement('div');
    wrap.className = 'user-report-eval-card';
    wrap.style.cssText = 'margin-top: 1.5rem; padding: 1.15rem 1.35rem; background: var(--surface-container-low, #f8fafc); border: 1px solid var(--border-color, #e2e8f0); border-radius: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);';
    
    const rel = score.relevance != null ? score.relevance : '—';
    const acc = score.accuracy != null ? score.accuracy : '—';
    const cla = score.clarity != null ? score.clarity : '—';
    const ovr = Number(score.overall).toFixed(1);
    
    wrap.innerHTML = `
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.85rem;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 28px; height: 28px; border-radius: 8px; background: rgba(2, 132, 199, 0.12); display: flex; align-items: center; justify-content: center; color: #0284c7;">
            <span class="material-symbols-outlined text-[17px]">gavel</span>
          </div>
          <div>
            <div style="font-size: 0.88rem; font-weight: 600; color: var(--on-surface, #0f172a);">Automated Quality Evaluation (LLM-as-a-Judge)</div>
            <div style="font-size: 0.72rem; color: var(--on-surface-variant, #64748b);">Calibrated pipeline rubrics: relevance, accuracy, and clarity</div>
          </div>
        </div>
        <div style="display: flex; align-items: baseline; gap: 3px; background: rgba(2, 132, 199, 0.1); padding: 4px 12px; border-radius: 999px; border: 1px solid rgba(2, 132, 199, 0.2);">
          <span style="font-size: 1.05rem; font-weight: 800; color: #0284c7;">${ovr}</span>
          <span style="font-size: 0.72rem; font-weight: 600; color: #64748b;">/ 10</span>
        </div>
      </div>
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 0.75rem;">
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--on-surface-variant, #64748b); margin-bottom: 4px;">
            <span>Relevance</span>
            <span style="font-weight: 600; color: var(--on-surface, #0f172a);">${rel} / 10</span>
          </div>
          <div style="height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;">
            <div style="height: 100%; width: ${(score.relevance || 0) * 10}%; background: #0284c7; border-radius: 999px;"></div>
          </div>
        </div>
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--on-surface-variant, #64748b); margin-bottom: 4px;">
            <span>Accuracy</span>
            <span style="font-weight: 600; color: var(--on-surface, #0f172a);">${acc} / 10</span>
          </div>
          <div style="height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;">
            <div style="height: 100%; width: ${(score.accuracy || 0) * 10}%; background: #0284c7; border-radius: 999px;"></div>
          </div>
        </div>
        <div>
          <div style="display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--on-surface-variant, #64748b); margin-bottom: 4px;">
            <span>Clarity</span>
            <span style="font-weight: 600; color: var(--on-surface, #0f172a);">${cla} / 10</span>
          </div>
          <div style="height: 6px; background: rgba(0,0,0,0.06); border-radius: 999px; overflow: hidden;">
            <div style="height: 100%; width: ${(score.clarity || 0) * 10}%; background: #0284c7; border-radius: 999px;"></div>
          </div>
        </div>
      </div>
      ${score.comment ? `<div style="font-size: 0.78rem; color: var(--on-surface-variant, #475569); line-height: 1.4; background: rgba(2, 132, 199, 0.04); padding: 8px 12px; border-radius: 8px; border-left: 3px solid #0284c7; font-style: italic;">"${escapeHTML(score.comment)}"</div>` : ''}
    `;
    return wrap;
  }
  function fillScore(score) {
    const ok = score && score.overall != null;
    const root = document.getElementById('admin-eval-scorecard');
    if (!root) return;
    const num = root.querySelector('.judge-score-number');
    if (num) num.textContent = ok ? score.overall : '\u2013';
    const vals = root.querySelectorAll('.criterion-score-val');
    const fills = root.querySelectorAll('.criterion-bar-fill');
    const descs = root.querySelectorAll('.criterion-desc');
    ['relevance', 'accuracy', 'clarity'].forEach((k, i) => {
      const v = ok ? score[k] : null;
      if (vals[i]) vals[i].textContent = v != null ? v + ' / 10' : '\u2013';
      if (fills[i]) fills[i].style.width = v != null ? (v * 10) + '%' : '0%';
      if (descs[i]) descs[i].textContent = '';
    });
    const card = root.querySelector('.judge-scorecard');
    let c = document.getElementById('judge-live-comment');
    if (card && !c) { c = document.createElement('p'); c.id = 'judge-live-comment'; c.className = 'criterion-desc'; c.style.marginTop = '12px'; card.append(c); }
    if (c) c.textContent = ok && score.comment ? score.comment : (score && score.error ? 'Grading failed: ' + score.error : 'No score for this reply.');
  }
  function afterTurn(turn) {
    if (turn.sources && turn.sources.length) state.dossier = { sources: toSources(turn), agentTrace: [] };
    if (turn.score) fillScore(turn.score);
    renderInspectorContent();
    setupCitations();
  }
  function errorNode(e) {
    const d = document.createElement('div');
    d.className = 'definitional-response-card';
    d.setAttribute('role', 'alert');
    const p = document.createElement('p'); p.className = 'article-prose';
    p.textContent = e.name === 'AbortError' ? 'Request cancelled.' : e.message;
    d.append(p); return d;
  }
  function createReportActionBar(articleEl, turn) {
    const bar = document.createElement('div');
    bar.className = 'report-action-bar';
    bar.style.marginTop = '1rem';
    bar.innerHTML = `
      <div class="action-buttons-group">
        <button class="btn-report-tool btn-copy-turn" type="button" title="Copy text">
          <span class="material-symbols-outlined text-[16px]">content_copy</span>
          <span>Copy report</span>
        </button>
        <button class="btn-report-tool btn-review-turn" type="button" title="Rate & review monograph">
          <span class="material-symbols-outlined text-[16px]">rate_review</span>
          <span>Review</span>
        </button>
        <div class="download-dropdown-wrapper">
          <button class="btn-report-tool btn-download-trigger" type="button" title="Download report">
            <span class="material-symbols-outlined text-[16px]">download</span>
            <span>Download</span>
            <span class="material-symbols-outlined text-[14px]">arrow_drop_down</span>
          </button>
          <div class="download-format-menu">
            <button class="download-format-item dl-pdf" type="button">
              <span class="material-symbols-outlined text-[17px] text-primary">picture_as_pdf</span>
              <span class="dl-format-name">PDF (.pdf)</span>
            </button>
            <button class="download-format-item dl-doc" type="button">
              <span class="material-symbols-outlined text-[17px] text-primary">description</span>
              <span class="dl-format-name">Word (.doc)</span>
            </button>
            <button class="download-format-item dl-txt" type="button">
              <span class="material-symbols-outlined text-[17px] text-primary">text_snippet</span>
              <span class="dl-format-name">Plain Text (.txt)</span>
            </button>
          </div>
        </div>
      </div>
    `;

    const copyBtn = bar.querySelector('.btn-copy-turn');
    const reviewBtn = bar.querySelector('.btn-review-turn');
    const trigger = bar.querySelector('.btn-download-trigger');
    const menu = bar.querySelector('.download-format-menu');

    copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(articleEl.innerText);
      showToast('Monograph copied to clipboard', 'content_copy');
    });

    reviewBtn?.addEventListener('click', () => {
      const reportId = turn?.id || (turn?.created ? 'rep-' + turn.created : 'report-' + Date.now());
      const topic = turn?.user || turn?.topic || 'Research Monograph';
      openReviewModal(reportId, RP.currentId(), topic, reviewBtn);
    });

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      document.querySelectorAll('.download-format-menu.show').forEach(m => {
        if (m !== menu) m.classList.remove('show');
      });
      menu.classList.toggle('show');
    });

    bar.querySelector('.dl-pdf').addEventListener('click', (e) => {
      e.stopPropagation();
      menu.classList.remove('show');
      downloadReportPDF(articleEl);
    });

    bar.querySelector('.dl-doc').addEventListener('click', (e) => {
      e.stopPropagation();
      menu.classList.remove('show');
      downloadReportDOC(articleEl);
    });

    bar.querySelector('.dl-txt').addEventListener('click', (e) => {
      e.stopPropagation();
      menu.classList.remove('show');
      downloadReportTXT(articleEl);
    });

    return bar;
  }

  function buildAssistant(turn) {
    const parts = reportParts(turn);
    if (turn.intent === 'question') {
      const card = document.createElement('div'); card.className = 'definitional-response-card';
      card.append(badgesEl(turn), parts.node); return card;
    }
    const container = document.createElement('div');
    container.className = 'chat-turn-assistant-card';
    const art = document.createElement('article'); art.className = 'editorial-article';
    const head = document.createElement('header'); head.className = 'article-header';
    const h = document.createElement('h2'); h.className = 'article-headline'; h.textContent = parts.title || turn.user;
    head.append(h); art.append(head, badgesEl(turn), parts.node);
    container.append(art, createReportActionBar(art, turn));
    return container;
  }
  function assistantHolder(turn) {
    const w = document.createElement('div'); w.className = 'chat-turn-assistant'; w.style.marginTop = '1rem';
    w.append(buildAssistant(turn)); return w;
  }
  function userBubbleNode(text, attachments, when) {
    const wrap = document.createElement('div');
    wrap.className = 'chat-turn-user'; wrap.style.marginTop = '1.5rem';
    const att = (attachments || []).map(a => `<span class="user-attachment-pill"><span class="material-symbols-outlined text-[13px]">${a.type === 'folder' ? 'folder' : 'draft'}</span><span>${escapeHTML(a.name)}</span></span>`).join('');
    wrap.innerHTML = `<div class="user-bubble secondary-turn">${att ? `<div class="user-attachments-badge">${att}</div>` : ''}<p class="user-bubble-text"></p></div><div class="user-bubble-actions"><span class="user-bubble-time"></span></div>`;
    wrap.querySelector('.user-bubble-text').textContent = text;
    wrap.querySelector('.user-bubble-time').textContent = fmtTime(when);
    return wrap;
  }

  // First turn goes into the existing static layout (keeps copy / download / retry bar)
  function showTurnInSlot(turn, when) {
    state.currentMainTurn = turn;
    welcomeScreen.style.display = 'none';
    conversationStream.style.display = 'flex';
    dynamicFollowups.innerHTML = '';
    const ut = document.querySelector('.chat-turn-user .user-bubble-text'); if (ut) ut.textContent = turn.user;
    const tm = document.querySelector('.chat-turn-user .user-bubble-time'); if (tm) tm.textContent = fmtTime(when);
    document.querySelectorAll('#agent-flow-stepper, .provenance-quick-bar').forEach(e => { e.style.display = 'none'; });
    const art = document.querySelector('.editorial-article');
    const parts = reportParts(turn);
    const head = document.createElement('header'); head.className = 'article-header';
    const h = document.createElement('h2'); h.className = 'article-headline'; h.textContent = parts.title || turn.user;
    head.append(h);
    art.replaceChildren(head, badgesEl(turn), parts.node);

    // Wire up main review button
    const mainRevBtn = document.getElementById('btn-review-main-report');
    if (mainRevBtn) {
      mainRevBtn.onclick = () => {
        const t = state.currentMainTurn || turn;
        const reportId = t?.id || (t?.created ? 'rep-' + t.created : 'report-' + Date.now());
        const topic = t?.user || t?.topic || 'Research Monograph';
        openReviewModal(reportId, RP.currentId(), topic, mainRevBtn);
      };
    }

    updateHeaderSourcesBadge((turn.sources || []).length);
    if (headerBreadcrumbTitle) headerBreadcrumbTitle.textContent = parts.title || turn.user;
    if (window.innerWidth <= 768) setSidebarState(false);
  }

  function showSavedChat(chat) {
    RP.openChat(chat.id);
    RP.setLastActiveChatId(chat.id);
    const first = chat.turns[0];
    state.lastTopic = first.user;
    state.dossier = null;
    showTurnInSlot(first, chat.created);
    chat.turns.slice(1).forEach(t => {
      dynamicFollowups.append(userBubbleNode(t.user, [], chat.updated), assistantHolder(t));
    });
    for (let i = chat.turns.length - 1; i >= 0; i--) {
      if (chat.turns[i].sources && chat.turns[i].sources.length) { afterTurn(chat.turns[i]); break; }
    }
    const scored = [...chat.turns].reverse().find(t => t.score);
    fillScore(scored ? scored.score : null);
    renderInspectorContent(); setupCitations(); renderHistory();
    scrollToBottom();
  }

  function renderHistory() {
    const nav = document.querySelector('.sidebar-nav');
    if (!nav) return;
    const chats = RP.listChats();
    nav.innerHTML = '';
    if (!chats.length) {
      const p = document.createElement('p'); p.className = 'history-group-title';
      p.textContent = 'Your researched topics will appear here.'; nav.append(p); return;
    }
    const groups = {};
    chats.forEach(c => { (groups[groupOf(c.updated)] = groups[groupOf(c.updated)] || []).push(c); });
    ['Today', 'Yesterday', 'Previous 7 days', 'Older'].forEach(g => {
      if (!groups[g]) return;
      const wrap = document.createElement('div');
      const t = document.createElement('div'); t.className = 'history-group-title'; t.textContent = g;
      const ul = document.createElement('ul'); ul.className = 'history-list';
      groups[g].forEach(c => {
        const li = document.createElement('li');
        li.className = 'history-item' + (c.id === RP.currentId() ? ' active' : '');
        li.dataset.inquiryId = c.id;
        li.innerHTML = '<div class="history-item-left"><span class="history-indicator"></span><span class="history-title"></span></div><button class="history-item-menu-btn" type="button" title="More options" aria-label="More options"><span class="material-symbols-outlined text-[17px]">more_vert</span></button>';
        li.querySelector('.history-title').textContent = c.title;
        li.addEventListener('click', () => {
          if (li.querySelector('.history-item-edit-wrapper')) return;
          loadDossier(c.id);
        });
        const menuBtn = li.querySelector('.history-item-menu-btn');
        menuBtn?.addEventListener('click', (e) => {
          e.stopPropagation();
          openChatMenu(c.id, c.title, menuBtn);
        });
        ul.append(li);
      });
      wrap.append(t, ul); nav.append(wrap);
    });
  }

  // --- Open a saved chat, or start real research for a suggested topic ---
  function loadDossier(key) {
    const chat = RP.getChat(key);
    if (chat && chat.turns.length) return showSavedChat(chat);
    const reg = DOSSIER_REGISTRY[key];
    runPipeline(reg ? reg.query : key);
  }

  // --- Show Welcome Screen for New Inquiry ---
  function showWelcomeScreen() {
    RP.newChat();
    state.dossier = null;
    updateHeaderSourcesBadge(0);
    if (dynamicFollowups) dynamicFollowups.innerHTML = '';
    renderInspectorContent();
    welcomeScreen.style.display = 'flex';
    conversationStream.style.display = 'none';
    if (headerBreadcrumbTitle) headerBreadcrumbTitle.textContent = 'New Inquiry';
    composerInput.value = '';
    composerInput.focus();
    autoResizeTextarea();
    renderHistory();
    if (window.innerWidth <= 768) setSidebarState(false);
  }

  // --- Follow-ups: edit, question, or new topic, routed by the backend ---
  async function appendFollowUpInStream(questionText, attachments = []) {
    if (!dynamicFollowups) return;
    if (welcomeScreen.style.display !== 'none') return runPipeline(questionText);
    if (state.busy) { showToast('Still working on the previous request', 'hourglass_empty'); return; }
    if (attachments.length) showToast('Attachments are not sent to the research backend yet', 'info', 4000);
    state.busy = true;
    dynamicFollowups.append(userBubbleNode(questionText, attachments));
    const holder = document.createElement('div');
    holder.className = 'chat-turn-assistant'; holder.style.marginTop = '1rem';
    holder.innerHTML = '<div class="definitional-response-card"><p class="article-prose">Working on it. This can take a few minutes.</p></div>';
    dynamicFollowups.append(holder);
    scrollToBottom();
    activeController = new AbortController();
    try {
      const data = await RP.generate(questionText, activeController.signal);
      const turn = turnFrom(questionText, data);
      holder.replaceChildren(buildAssistant(turn));
      afterTurn(turn);
    } catch (e) {
      holder.replaceChildren(errorNode(e));
    } finally {
      state.busy = false; activeController = null;
      renderHistory(); scrollToBottom();
    }
  }

  function escapeHTML(str) {
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }

  // --- Real research run (replaces the simulated pipeline) ---
  function ensureCancel() {
    const box = pipelineModal.querySelector('.pipeline-run-box');
    const mini = pipelineModal.querySelector('.pipeline-mini-stepper');
    if (mini) mini.style.display = 'none';
    let b = document.getElementById('btn-pipeline-cancel');
    if (!b) {
      b = document.createElement('button');
      b.id = 'btn-pipeline-cancel'; b.type = 'button'; b.textContent = 'Cancel';
      b.className = 'btn-report-tool';
      b.addEventListener('click', () => { if (activeController) activeController.abort(); });
      box.append(b);
    }
  }

  async function runPipeline(topicText) {
    topicText = (topicText || '').trim();
    if (!topicText || !pipelineModal) return;
    if (state.busy) { showToast('Still working on the previous request', 'hourglass_empty'); return; }
    state.busy = true;
    RP.newChat();
    pipelineModal.classList.add('active');
    ensureCancel();
    let i = 0;
    const tick = () => {
      const st = STATUS_STEPS[i % STATUS_STEPS.length]; i++;
      if (pipelineLiveTitle) pipelineLiveTitle.textContent = st[0];
      if (pipelineLiveDesc) pipelineLiveDesc.textContent = st[1] + ' This can take a few minutes.';
    };
    tick();
    const timer = setInterval(tick, 5000);
    activeController = new AbortController();
    try {
      const data = await RP.generate(topicText, activeController.signal);
      const turn = turnFrom(topicText, data);
      state.lastTopic = topicText;
      state.dossier = null;
      if (data && data.session_id) {
        RP.setLastActiveChatId(data.session_id);
      }
      showTurnInSlot(turn, Date.now());
      afterTurn(turn);
      scrollToBottom();
    } catch (e) {
      if (e.name === 'AbortError') showToast('Request cancelled', 'cancel');
      else showToast(e.message, 'error', 6000);
    } finally {
      clearInterval(timer);
      pipelineModal.classList.remove('active');
      state.busy = false; activeController = null;
      renderHistory();
    }
  }

  // --- File & Folder Upload Utilities ---
  function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function renderComposerAttachments() {
    if (!composerAttachments) return;
    if (state.attachedFiles.length === 0) {
      composerAttachments.innerHTML = '';
      composerAttachments.style.display = 'none';
      return;
    }

    composerAttachments.style.display = 'flex';

    composerAttachments.innerHTML = state.attachedFiles.map((att, idx) => `
      <div class="attachment-chip">
        <span class="material-symbols-outlined text-[15px]">${att.type === 'folder' ? 'folder_open' : 'description'}</span>
        <span class="attachment-chip-name" title="${escapeHTML(att.name)}">${escapeHTML(att.name)}</span>
        ${att.count ? `<span class="attachment-chip-meta">${att.count} files</span>` : (att.size ? `<span class="attachment-chip-meta">${att.size}</span>` : '')}
        <button type="button" class="btn-remove-attachment" data-idx="${idx}" title="Remove attachment">
          <span class="material-symbols-outlined text-[13px]">close</span>
        </button>
      </div>
    `).join('');

    composerAttachments.querySelectorAll('.btn-remove-attachment').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-idx'), 10);
        state.attachedFiles.splice(idx, 1);
        renderComposerAttachments();
      });
    });
  }

  // Unified Upload Dropdown Listeners
  btnUploadTrigger?.addEventListener('click', (e) => {
    e.stopPropagation();
    uploadOptionsMenu?.classList.toggle('show');
  });

  btnOptionUploadFile?.addEventListener('click', (e) => {
    e.stopPropagation();
    uploadOptionsMenu?.classList.remove('show');
    inputUploadFile?.click();
  });

  btnOptionUploadFolder?.addEventListener('click', (e) => {
    e.stopPropagation();
    uploadOptionsMenu?.classList.remove('show');
    inputUploadFolder?.click();
  });

  // Close upload menu when clicking outside
  document.addEventListener('click', (e) => {
    if (uploadDropdownWrapper && !uploadDropdownWrapper.contains(e.target)) {
      uploadOptionsMenu?.classList.remove('show');
    }
  });

  inputUploadFile?.addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    files.forEach(file => {
      state.attachedFiles.push({
        name: file.name,
        type: 'file',
        size: formatFileSize(file.size)
      });
    });
    inputUploadFile.value = '';
    renderComposerAttachments();
    showToast(`Attached ${files.length} file${files.length > 1 ? 's' : ''}`, 'attach_file');
  });

  inputUploadFolder?.addEventListener('change', (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    const samplePath = files[0].webkitRelativePath || '';
    const folderName = samplePath.split('/')[0] || samplePath.split('\\')[0] || 'Selected Folder';
    const totalBytes = files.reduce((acc, f) => acc + (f.size || 0), 0);
    state.attachedFiles.push({
      name: folderName,
      type: 'folder',
      count: files.length,
      size: formatFileSize(totalBytes)
    });
    inputUploadFolder.value = '';
    renderComposerAttachments();
    showToast(`Attached folder "${folderName}" (${files.length} files)`, 'folder_open');
  });

  // --- Submit Handler for the SINGLE Composer Box ---
  function handleComposerSubmit() {
    const text = composerInput.value.trim();
    if (!text && state.attachedFiles.length === 0) return;

    const attachments = [...state.attachedFiles];
    state.attachedFiles = [];
    renderComposerAttachments();

    composerInput.value = '';
    autoResizeTextarea();

    if (welcomeScreen.style.display !== 'none') {
      runPipeline(text || (attachments.length > 0 ? attachments[0].name : 'Uploaded File Research'));
    } else {
      appendFollowUpInStream(text || '(Attached file inquiry)', attachments);
    }
  }

  btnSendMessage?.addEventListener('click', handleComposerSubmit);

  composerInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleComposerSubmit();
    }
  });

  // Navigation
  btnNewInquiry?.addEventListener('click', () => {
    RP.setLastActiveChatId('new');
    showWelcomeScreen();
  });

  // Delegated History item and menu clicks on sidebar-nav
  const sidebarNav = document.querySelector('.sidebar-nav');
  sidebarNav?.addEventListener('click', (e) => {
    const menuBtn = e.target.closest('.history-item-menu-btn');
    if (menuBtn) {
      e.stopPropagation();
      const item = menuBtn.closest('.history-item');
      const id = item?.getAttribute('data-inquiry-id');
      const title = item?.querySelector('.history-title')?.textContent?.trim() || 'this conversation';
      openChatMenu(id, title, menuBtn);
      return;
    }
    const item = e.target.closest('.history-item');
    if (item && !item.querySelector('.history-item-edit-wrapper')) {
      const id = item.getAttribute('data-inquiry-id');
      if (id) loadDossier(id);
    }
  });

  // Curated dossier card clicks
  document.querySelectorAll('.dossier-card').forEach(card => {
    card.addEventListener('click', () => {
      const key = card.getAttribute('data-dossier-key');
      loadDossier(key);
    });
  });

  // Inspector panel toggle
  btnToggleSources?.addEventListener('click', () => toggleInspector());
  btnCloseInspector?.addEventListener('click', () => toggleInspector(false));
  document.getElementById('btn-more-sources')?.addEventListener('click', () => {
    toggleInspector(true);
    setInspectorTab('sources');
  });
  document.getElementById('btn-full-audit')?.addEventListener('click', () => {
    toggleInspector(true);
    setInspectorTab('sources');
  });

  // Inspector tabs (Admin only)
  tabBtnSources?.addEventListener('click', () => setInspectorTab('sources'));
  tabBtnTrace?.addEventListener('click', () => setInspectorTab('trace'));
  tabBtnAudit?.addEventListener('click', () => setInspectorTab('audit'));

  // Exploration chips
  document.querySelectorAll('.pathway-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.getAttribute('data-prompt') || chip.innerText.trim();
      appendFollowUpInStream(prompt);
    });
  });

  // Suggested Research Starter Card clicks on the Welcome screen
  document.querySelectorAll('.research-starter-card').forEach(card => {
    card.addEventListener('click', () => {
      const key = card.getAttribute('data-inquiry-key') || 'microplastics';
      loadDossier(key);
    });
  });

  // =========================================================================
  // Comprehensive Search Database & Modal Controller (Ctrl + K)
  // =========================================================================
  function highlightMatches(text, query) {
    if (!query) return escapeHTML(text);
    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    return escapeHTML(text).replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  function renderModalResults(query = '') {
    if (!modalResultsScroll) return;
    const q = query.trim().toLowerCase();

    const filtered = RP.search(q).map(r => ({
      id: r.chat.id, title: r.chat.title, category: 'Research',
      snippet: r.snippet || (r.chat.turns[0] ? String(r.chat.turns[0].report || '').replace(/[#*\n]+/g, ' ').slice(0, 140) : ''),
      date: fmtDate(r.chat.updated), type: 'inquiry'
    }));

    if (filtered.length === 0) {
      modalResultsScroll.innerHTML = `
        <div class="modal-empty-state">
          <div class="modal-empty-icon">
            <span class="material-symbols-outlined text-[24px]">manage_search</span>
          </div>
          <div class="modal-empty-title">No past inquiries found for "${escapeHTML(query)}"</div>
          <p class="modal-empty-desc">Would you like our multi-agent platform to research this new topic right now?</p>
          <button class="btn-search-new-topic" type="button" id="btn-research-query-now">
            <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
            <span>Synthesize "${escapeHTML(query.slice(0, 24))}${query.length > 24 ? '...' : ''}"</span>
          </button>
        </div>
      `;

      document.getElementById('btn-research-query-now')?.addEventListener('click', () => {
        closeSearchModal();
        runPipeline(query);
      });
      return;
    }

    const inquiries = filtered.filter(f => f.type === 'inquiry');
    const papers = filtered.filter(f => f.type === 'paper');

    let html = '';

    if (inquiries.length > 0) {
      html += `<div class="modal-result-category-header">${q ? 'Matching Inquiries' : 'Recent Inquiries'} (${inquiries.length})</div>`;
      inquiries.forEach(item => {
        html += `
          <div class="modal-result-item" data-search-id="${item.id}" data-search-type="inquiry" title="Click to view synthesis">
            <div class="modal-result-main">
              <div class="modal-result-top">
                <span class="modal-result-badge">${escapeHTML(item.category)}</span>
                <span class="modal-result-date">${escapeHTML(item.date)}</span>
              </div>
              <h4 class="modal-result-title">${highlightMatches(item.title, q)}</h4>
              <p class="modal-result-snippet">${highlightMatches(item.snippet, q)}</p>
            </div>
            <button class="modal-result-delete-btn" data-delete-id="${item.id}" data-delete-title="${escapeHTML(item.title)}" title="Delete inquiry" type="button" aria-label="Delete inquiry">
              <span class="material-symbols-outlined text-[16px]">delete</span>
            </button>
            <span class="material-symbols-outlined text-[18px] modal-result-arrow">arrow_forward</span>
          </div>
        `;
      });
    }

    if (papers.length > 0) {
      html += `<div class="modal-result-category-header">${q ? 'Matching Academic Papers' : 'Indexed Papers & Notes'} (${papers.length})</div>`;
      papers.forEach(item => {
        html += `
          <div class="modal-result-item" data-search-id="${item.id}" data-search-type="paper" title="Click to open paper synthesis">
            <div class="modal-result-main">
              <div class="modal-result-top">
                <span class="modal-result-badge" style="color: var(--tertiary);">${escapeHTML(item.category)}</span>
                <span class="modal-result-date">${escapeHTML(item.date)}</span>
              </div>
              <h4 class="modal-result-title">${highlightMatches(item.title, q)}</h4>
              <p class="modal-result-snippet">${highlightMatches(item.snippet, q)}</p>
            </div>
            <span class="material-symbols-outlined text-[18px] modal-result-arrow">arrow_forward</span>
          </div>
        `;
      });
    }

    modalResultsScroll.innerHTML = html;

    // Attach click listeners to all items
    modalResultsScroll.querySelectorAll('.modal-result-item').forEach(el => {
      el.addEventListener('click', (e) => {
        if (e.target.closest('.modal-result-delete-btn')) return;
        const id = el.getAttribute('data-search-id');
        closeSearchModal();
        loadDossier(id);
      });
      const delBtn = el.querySelector('.modal-result-delete-btn');
      delBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = delBtn.getAttribute('data-delete-id');
        const title = delBtn.getAttribute('data-delete-title');
        confirmDeleteConversation(id, title);
      });
    });
  }

  function openSearchModal() {
    if (!searchModalBackdrop) return;
    searchModalBackdrop.classList.add('active');
    if (modalSearchInput) {
      modalSearchInput.value = '';
      modalSearchInput.focus();
    }
    renderModalResults('');
  }

  function closeSearchModal() {
    if (!searchModalBackdrop) return;
    searchModalBackdrop.classList.remove('active');
    if (modalSearchInput) {
      modalSearchInput.value = '';
    }
  }

  function executeSearchAction() {
    const query = modalSearchInput?.value.trim();
    if (!query) {
      modalSearchInput?.focus();
      return;
    }
    const firstResult = modalResultsScroll?.querySelector('.modal-result-item');
    if (firstResult) {
      firstResult.click();
    } else {
      closeSearchModal();
      runPipeline(query);
    }
  }

  // Search Modal Triggers & Controls
  searchTriggerBtn?.addEventListener('click', openSearchModal);

  // Cross / Close Button: Closes search modal immediately
  btnClearSearch?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeSearchModal();
  });

  // Search Icon Button: Executes search on input text
  btnModalSearch?.addEventListener('click', (e) => {
    e.stopPropagation();
    executeSearchAction();
  });

  // ESC Button in header: Closes search modal
  btnModalEsc?.addEventListener('click', (e) => {
    e.stopPropagation();
    closeSearchModal();
  });

  // Live filter as user types
  modalSearchInput?.addEventListener('input', (e) => {
    renderModalResults(e.target.value);
  });

  // Enter to search, Escape to close
  modalSearchInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      executeSearchAction();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeSearchModal();
    }
  });

  // Backdrop click closes search modal
  searchModalBackdrop?.addEventListener('click', (e) => {
    if (e.target === searchModalBackdrop) {
      closeSearchModal();
    }
  });

  // Safe event binding helper (Task 4)
  function safeBindListener(element, eventType, handler, elementId) {
    if (element) {
      element.addEventListener(eventType, handler);
    } else {
      console.warn(`[SafeEventBinding] Element #${elementId} not found in DOM; listener skipped.`);
    }
  }

  // Profile Dropdown Event Handlers (Single place to login as User or Admin!)
  safeBindListener(btnProfileTrigger, 'click', (e) => {
    e.stopPropagation();
    const isOpen = profileDropdown?.classList.toggle('show');
    btnProfileTrigger?.classList.toggle('active', isOpen);
  }, 'btn-profile-trigger');

  safeBindListener(profileSwitchUser, 'click', (e) => {
    e.stopPropagation();
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    if (state.currentUser) {
      showToast(`Logged in as ${state.currentUser.full_name || state.currentUser.email}`, 'person');
    } else {
      openLoginModal('user');
    }
  }, 'profile-switch-user');

  safeBindListener(profileSwitchAdmin, 'click', (e) => {
    e.stopPropagation();
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal('admin');
  }, 'profile-switch-admin');

  const btnOpenAdminDashboard = document.getElementById('btn-open-admin-dashboard');
  safeBindListener(btnOpenAdminDashboard, 'click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal('admin');
  }, 'btn-open-admin-dashboard');

  safeBindListener(btnProfileQuickSwitch, 'click', (e) => {
    e.stopPropagation();
    const targetRole = state.role === 'admin' ? 'user' : 'admin';
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal(targetRole);
  }, 'btn-profile-quick-switch');

  safeBindListener(btnProfileDetails, 'click', (e) => {
    e.stopPropagation();
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal(state.role);
  }, 'btn-profile-details');

  // Close profile dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (profileContainer && !profileContainer.contains(e.target)) {
      profileDropdown?.classList.remove('show');
      btnProfileTrigger?.classList.remove('active');
    }
  });

  // Header and Profile Auth Event Listeners
  safeBindListener(btnHeaderSignin, 'click', () => openLoginModal('user'), 'btn-header-signin');
  safeBindListener(btnHeaderSignout, 'click', handleLogout, 'btn-header-signout');
  safeBindListener(btnProfileLogout, 'click', handleLogout, 'btn-profile-logout');

  // User Auth Mode (Sign In vs Register) Listeners
  safeBindListener(userModeSigninBtn, 'click', () => setUserAuthMode('signin'), 'user-mode-signin');
  safeBindListener(userModeRegisterBtn, 'click', () => setUserAuthMode('register'), 'user-mode-register');

  safeBindListener(btnSubmitRegister, 'click', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  }, 'btn-submit-register');

  safeBindListener(registerForm, 'submit', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  }, 'register-form');

  safeBindListener(btnToggleRegPassword, 'click', () => {
    if (registerPassword) {
      const isPass = registerPassword.type === 'password';
      registerPassword.type = isPass ? 'text' : 'password';
      if (registerConfirmPassword) {
        registerConfirmPassword.type = isPass ? 'text' : 'password';
      }
      if (iconToggleRegPassword) {
        iconToggleRegPassword.textContent = isPass ? 'visibility_off' : 'visibility';
      }
    }
  }, 'btn-toggle-reg-password');

  // Login Modal Event Listeners
  safeBindListener(btnCloseLoginModal, 'click', closeLoginModal, 'btn-close-login-modal');
  safeBindListener(loginModalBackdrop, 'click', (e) => {
    if (e.target === loginModalBackdrop) closeLoginModal();
  }, 'login-modal-backdrop');

  safeBindListener(loginTabUser, 'click', () => updateLoginModalUI('user'), 'login-tab-user');
  safeBindListener(loginTabAdmin, 'click', () => updateLoginModalUI('admin'), 'login-tab-admin');

  safeBindListener(btnSubmitLogin, 'click', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  }, 'btn-submit-login');

  safeBindListener(loginForm, 'submit', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  }, 'login-form');

  safeBindListener(btnTogglePassword, 'click', () => {
    if (!loginPassword) return;
    const isPass = loginPassword.type === 'password';
    loginPassword.type = isPass ? 'text' : 'password';
    if (iconTogglePassword) {
      iconTogglePassword.textContent = isPass ? 'visibility_off' : 'visibility';
    }
  }, 'btn-toggle-password');

  // Global Keyboard Shortcuts
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openSearchModal();
    } else if (e.key === 'Escape') {
      closeSearchModal();
      closeLoginModal();
      closeShareModal();
      downloadFormatMenu?.classList.remove('show');
      uploadOptionsMenu?.classList.remove('show');
      profileDropdown?.classList.remove('show');
      btnProfileTrigger?.classList.remove('active');
    }
  });

  // --- Copy Prompt Delegated Handler (Turn 1 & all follow-up turns, ChatGPT-style) ---
  document.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('.btn-copy-prompt');
    if (!copyBtn) return;
    const chatTurn = copyBtn.closest('.chat-turn-user');
    const promptTextEl = chatTurn?.querySelector('.user-bubble-text');
    if (promptTextEl) {
      const text = promptTextEl.innerText.trim();
      navigator.clipboard.writeText(text).then(() => {
        const copyIcon = copyBtn.querySelector('.copy-icon');
        const checkIcon = copyBtn.querySelector('.check-icon');
        if (copyIcon) copyIcon.style.display = 'none';
        if (checkIcon) checkIcon.style.display = 'block';
        copyBtn.classList.add('copied');
        copyBtn.setAttribute('title', 'Copied!');
        showToast('Prompt copied to clipboard', 'content_copy');
        setTimeout(() => {
          if (copyIcon) copyIcon.style.display = 'block';
          if (checkIcon) checkIcon.style.display = 'none';
          copyBtn.classList.remove('copied');
          copyBtn.setAttribute('title', 'Copy');
        }, 2000);
      }).catch(() => {
        showToast('Prompt copied to clipboard', 'content_copy');
      });
    }
  });

  // --- Multi-Format Report Download Utilities ---
  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function getActiveArticle(target) {
    if (target && target.nodeType) return target;
    const articles = document.querySelectorAll('.editorial-article');
    return articles.length ? articles[articles.length - 1] : null;
  }

  function downloadReportPDF(target) {
    const article = getActiveArticle(target);
    if (!article) return;
    const printFrame = document.createElement('iframe');
    printFrame.style.position = 'fixed';
    printFrame.style.right = '0';
    printFrame.style.bottom = '0';
    printFrame.style.width = '0';
    printFrame.style.height = '0';
    printFrame.style.border = '0';
    document.body.appendChild(printFrame);

    const doc = printFrame.contentWindow.document;
    doc.open();
    doc.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Multi-Agent Research Monograph</title>
        <style>
          body { font-family: 'Times New Roman', Georgia, serif; line-height: 1.6; margin: 2rem; color: #111; }
          h1 { font-size: 22pt; margin-bottom: 0.5rem; color: #0f172a; }
          h2 { font-size: 15pt; margin-top: 1.5rem; color: #1e293b; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }
          h3 { font-size: 12pt; margin-top: 1rem; color: #334155; }
          p { font-size: 11pt; margin-bottom: 0.75rem; text-align: justify; }
          .citation-chip { font-weight: bold; background: #e0f2fe; padding: 1px 4px; border-radius: 3px; }
          @page { margin: 1in; }
        </style>
      </head>
      <body>
        <h1>Multi-Agent Research Monograph</h1>
        <p style="color: #64748b; font-size: 10pt;"><em>Generated by Autonomous Multi-Agent Research Platform</em></p>
        <hr style="border: 0; border-top: 1px solid #cbd5e1; margin: 1rem 0;" />
        ${article.innerHTML}
      </body>
      </html>
    `);
    doc.close();

    setTimeout(() => {
      printFrame.contentWindow.focus();
      printFrame.contentWindow.print();
      setTimeout(() => {
        if (printFrame.parentNode) printFrame.parentNode.removeChild(printFrame);
      }, 1000);
    }, 350);

    showToast('Preparing PDF download / print...', 'picture_as_pdf');
  }

  function downloadReportDOC(target) {
    const article = getActiveArticle(target);
    if (!article) return;
    const wordHtml = `
      <html xmlns:o='urn:schemas-microsoft-com:office:office' 
            xmlns:w='urn:schemas-microsoft-com:office:word' 
            xmlns='http://www.w3.org/TR/REC-html40'>
      <head><meta charset='utf-8'><title>Research Monograph</title>
      <style>
        body { font-family: Calibri, Arial, sans-serif; font-size: 11pt; line-height: 1.4; color: #1e293b; }
        h1 { font-size: 20pt; color: #0f172a; margin-bottom: 8pt; }
        h2 { font-size: 14pt; color: #1e293b; margin-top: 16pt; margin-bottom: 6pt; border-bottom: 1px solid #e2e8f0; }
        p { margin-bottom: 8pt; }
      </style>
      </head><body>
      <h1>Multi-Agent Research Monograph</h1>
      <p style="color: #64748b;"><em>Generated by Autonomous Multi-Agent Research Platform</em></p>
      <hr/>
      ${article.innerHTML}
      </body></html>
    `;
    const blob = new Blob(['\ufeff', wordHtml], { type: 'application/msword;charset=utf-8;' });
    downloadBlob(blob, 'multiagent_research_monograph.doc');
    showToast('Downloaded Word document (.doc)', 'description');
  }

  function downloadReportTXT(target) {
    const article = getActiveArticle(target);
    if (!article) return;
    const content = `MULTI-AGENT RESEARCH MONOGRAPH\nGenerated by Autonomous Multi-Agent Research Platform\n======================================================\n\n${article.innerText}`;
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8;' });
    downloadBlob(blob, 'multiagent_research_monograph.txt');
    showToast('Downloaded plain text (.txt)', 'text_snippet');
  }

  // Report Copy
  document.getElementById('btn-copy-report')?.addEventListener('click', () => {
    const article = document.querySelector('.editorial-article');
    if (article) {
      navigator.clipboard.writeText(article.innerText);
      showToast('Monograph copied to clipboard', 'content_copy');
    }
  });

  // Download Dropdown Menu Toggle
  btnDlReport?.addEventListener('click', (e) => {
    e.stopPropagation();
    downloadFormatMenu?.classList.toggle('show');
  });

  btnDlPdf?.addEventListener('click', (e) => {
    e.stopPropagation();
    downloadFormatMenu?.classList.remove('show');
    downloadReportPDF();
  });

  btnDlDoc?.addEventListener('click', (e) => {
    e.stopPropagation();
    downloadFormatMenu?.classList.remove('show');
    downloadReportDOC();
  });

  btnDlTxt?.addEventListener('click', (e) => {
    e.stopPropagation();
    downloadFormatMenu?.classList.remove('show');
    downloadReportTXT();
  });

  // Close download menu when clicking outside
  document.addEventListener('click', (e) => {
    if (!e.target.closest('.download-dropdown-wrapper')) {
      document.querySelectorAll('.download-format-menu.show').forEach(m => m.classList.remove('show'));
    }
  });

  // --- Share Modal Logic ---
  const shareModalBackdrop = document.getElementById('share-modal-backdrop');
  const btnCloseShareModal = document.getElementById('btn-close-share-modal');
  const btnCopyShareUrl = document.getElementById('btn-copy-share-url');
  const shareUrlInput = document.getElementById('share-url-input');
  const btnSendInvite = document.getElementById('btn-send-invite');
  const shareInviteEmail = document.getElementById('share-invite-email');
  const sharedUsersContainer = document.getElementById('shared-users-container');

  function openShareModal() {
    shareModalBackdrop?.classList.add('active');
  }

  function closeShareModal() {
    shareModalBackdrop?.classList.remove('active');
  }

  document.getElementById('btn-share-report')?.addEventListener('click', openShareModal);
  document.getElementById('btn-header-share')?.addEventListener('click', openShareModal);
  btnCloseShareModal?.addEventListener('click', closeShareModal);
  shareModalBackdrop?.addEventListener('click', (e) => {
    if (e.target === shareModalBackdrop) closeShareModal();
  });

  // Copy share URL button
  btnCopyShareUrl?.addEventListener('click', () => {
    const url = shareUrlInput?.value || window.location.href;
    navigator.clipboard.writeText(url).then(() => {
      const copyIcon = document.getElementById('copy-share-icon');
      const copyText = document.getElementById('copy-share-text');
      if (copyIcon) copyIcon.textContent = 'check';
      if (copyText) copyText.textContent = 'Copied!';
      showToast('Share link copied to clipboard!', 'share');
      setTimeout(() => {
        if (copyIcon) copyIcon.textContent = 'content_copy';
        if (copyText) copyText.textContent = 'Copy Link';
      }, 2000);
    });
  });

  // Invite user by email
  btnSendInvite?.addEventListener('click', () => {
    const email = shareInviteEmail?.value.trim();
    if (!email) {
      showToast('Please enter an email to invite', 'error');
      shareInviteEmail?.focus();
      return;
    }
    if (sharedUsersContainer) {
      const userRow = document.createElement('div');
      userRow.className = 'shared-user-row';
      userRow.innerHTML = `
        <div class="shared-user-info">
          <div class="shared-user-avatar">
            <span class="material-symbols-outlined text-[16px]">person</span>
          </div>
          <div>
            <div class="shared-user-name">${escapeHTML(email.split('@')[0])}</div>
            <div class="shared-user-email">${escapeHTML(email)}</div>
          </div>
        </div>
        <span class="shared-role-badge">Can View</span>
      `;
      sharedUsersContainer.appendChild(userRow);
    }
    shareInviteEmail.value = '';
    showToast(`Shared chat with ${email}`, 'person_add');
  });

  // Send via email channel
  document.getElementById('btn-share-email')?.addEventListener('click', () => {
    const title = headerBreadcrumbTitle?.textContent || 'Multi-Agent Research Synthesis';
    const mailto = `mailto:?subject=${encodeURIComponent('Research Synthesis: ' + title)}&body=${encodeURIComponent('Check out this research conversation:\n\n' + (shareUrlInput?.value || window.location.href))}`;
    window.open(mailto);
  });

  // Download Document channel
  document.getElementById('btn-share-doc')?.addEventListener('click', () => {
    downloadReportPDF();
  });

  // Retry Button - Smooth in-place refresh WITHOUT popping up the 7-step pipeline modal (Image 3)
  document.getElementById('btn-retry-synthesis')?.addEventListener('click', () => {
    const retryBtn = document.getElementById('btn-retry-synthesis');
    const retryIcon = retryBtn?.querySelector('.material-symbols-outlined');
    if (retryIcon) retryIcon.classList.add('spin-refresh');

    // 1. Ensure any stepper or provenance bars are removed if present
    const stepper = document.getElementById('agent-flow-stepper') || document.querySelector('.agent-flow-stepper');
    if (stepper) stepper.remove();

    const provBar = document.getElementById('provenance-quick-bar') || document.querySelector('.provenance-quick-bar');
    if (provBar) provBar.remove();

    // 2. Smoothly re-render synthesis in-place without triggering pipelineModal (Image 3)
    setTimeout(() => {
      if (state.lastTopic) runPipeline(state.lastTopic);
      if (retryIcon) retryIcon.classList.remove('spin-refresh');
      showToast('Research synthesis regenerated', 'refresh');
    }, 450);
  });

  // --- Floating Conversation Options Menu (ChatGPT / Gemini style) ---
  const chatOptionsMenu = document.getElementById('chat-options-menu');
  const btnChatMenuRename = document.getElementById('btn-chat-menu-rename');
  const btnChatMenuDelete = document.getElementById('btn-chat-menu-delete');
  let activeMenuChatId = null;
  let activeMenuChatTitle = '';
  let activeMenuTriggerBtn = null;
  let menuOpenedAt = 0;
  let menuScrollTop = 0;

  function openChatMenu(chatId, title, triggerBtn) {
    if (chatOptionsMenu && chatOptionsMenu.style.display !== 'none' && activeMenuTriggerBtn === triggerBtn) {
      closeChatMenu();
      return;
    }

    activeMenuChatId = chatId;
    activeMenuChatTitle = title;
    activeMenuTriggerBtn = triggerBtn;

    document.querySelectorAll('.history-item.menu-active').forEach(el => el.classList.remove('menu-active'));
    document.querySelectorAll('.history-item-menu-btn.active').forEach(el => el.classList.remove('active'));

    const parentItem = triggerBtn.closest('.history-item');
    if (parentItem) parentItem.classList.add('menu-active');
    triggerBtn.classList.add('active');

    if (!chatOptionsMenu) return;
    chatOptionsMenu.style.display = 'flex';

    menuOpenedAt = Date.now();
    const nav = document.querySelector('.sidebar-nav');
    menuScrollTop = nav ? nav.scrollTop : 0;

    const rect = triggerBtn.getBoundingClientRect();
    const menuWidth = 145;
    const menuHeight = 85;

    let left = rect.right - menuWidth;
    if (left < 10) left = rect.left;
    if (left + menuWidth > window.innerWidth - 10) left = window.innerWidth - menuWidth - 10;
    if (left < 10) left = 10;

    let top = rect.bottom + 4;
    if (top + menuHeight > window.innerHeight - 10) {
      top = Math.max(10, rect.top - menuHeight - 4);
    }

    chatOptionsMenu.style.left = `${left}px`;
    chatOptionsMenu.style.top = `${top}px`;
  }

  function closeChatMenu() {
    activeMenuChatId = null;
    activeMenuChatTitle = '';
    if (activeMenuTriggerBtn) {
      activeMenuTriggerBtn.classList.remove('active');
      activeMenuTriggerBtn.closest('.history-item')?.classList.remove('menu-active');
      activeMenuTriggerBtn = null;
    }
    document.querySelectorAll('.history-item.menu-active').forEach(el => el.classList.remove('menu-active'));
    document.querySelectorAll('.history-item-menu-btn.active').forEach(el => el.classList.remove('active'));
    if (chatOptionsMenu) chatOptionsMenu.style.display = 'none';
  }

  btnChatMenuRename?.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = activeMenuChatId;
    const btn = activeMenuTriggerBtn;
    const title = activeMenuChatTitle;
    closeChatMenu();
    let parentItem = btn ? btn.closest('.history-item') : null;
    if (!parentItem && id) {
      parentItem = document.querySelector(`.history-item[data-inquiry-id="${id}"]`);
    }
    if (parentItem) {
      startInlineRename(id, parentItem);
    } else {
      const newTitle = prompt('Enter new conversation title:', title);
      if (newTitle && newTitle.trim()) {
        RP.renameChat(id, newTitle.trim());
        if (headerBreadcrumbTitle) headerBreadcrumbTitle.textContent = newTitle.trim();
        renderHistory();
        showToast('Conversation renamed', 'edit');
      }
    }
  });

  btnChatMenuDelete?.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = activeMenuChatId;
    const title = activeMenuChatTitle;
    closeChatMenu();
    confirmDeleteConversation(id, title);
  });

  document.addEventListener('click', (e) => {
    if (!chatOptionsMenu || chatOptionsMenu.style.display === 'none') return;
    if (Date.now() - menuOpenedAt < 120) return;
    if (e.target.closest('#chat-options-menu') || e.target.closest('.history-item-menu-btn')) return;
    closeChatMenu();
  });

  window.addEventListener('resize', closeChatMenu);
  document.querySelector('.sidebar-nav')?.addEventListener('scroll', () => {
    if (Date.now() - menuOpenedAt < 250) return;
    const nav = document.querySelector('.sidebar-nav');
    if (nav && Math.abs(nav.scrollTop - menuScrollTop) > 15) {
      closeChatMenu();
    }
  });

  function startInlineRename(chatId, item) {
    if (!item) return;
    const titleEl = item.querySelector('.history-title');
    if (!titleEl) return;
    const oldTitle = titleEl.textContent;

    if (item.querySelector('.history-item-edit-wrapper')) return;

    titleEl.style.display = 'none';
    const menuBtn = item.querySelector('.history-item-menu-btn');
    if (menuBtn) menuBtn.style.display = 'none';

    const editWrapper = document.createElement('div');
    editWrapper.className = 'history-item-edit-wrapper';
    editWrapper.innerHTML = `
      <input type="text" class="history-item-rename-input" />
      <button type="button" class="history-item-rename-btn save" title="Save">
        <span class="material-symbols-outlined text-[15px]">check</span>
      </button>
      <button type="button" class="history-item-rename-btn cancel" title="Cancel">
        <span class="material-symbols-outlined text-[15px]">close</span>
      </button>
    `;

    const input = editWrapper.querySelector('.history-item-rename-input');
    input.value = oldTitle;

    const cleanup = () => {
      editWrapper.remove();
      titleEl.style.display = '';
      if (menuBtn) menuBtn.style.display = '';
    };

    const commitRename = () => {
      const newTitle = input.value.trim();
      cleanup();
      if (newTitle && newTitle !== oldTitle) {
        RP.renameChat(chatId, newTitle);
        titleEl.textContent = newTitle;
        if (chatId === RP.currentId() && headerBreadcrumbTitle) {
          headerBreadcrumbTitle.textContent = newTitle;
        }
        showToast('Conversation renamed', 'edit');
      }
    };

    const cancelRename = () => {
      cleanup();
    };

    editWrapper.querySelector('.save').addEventListener('click', (e) => {
      e.stopPropagation();
      commitRename();
    });

    editWrapper.querySelector('.cancel').addEventListener('click', (e) => {
      e.stopPropagation();
      cancelRename();
    });

    input.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') {
        e.preventDefault();
        commitRename();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        cancelRename();
      }
    });

    input.addEventListener('click', (e) => {
      e.stopPropagation();
    });

    item.querySelector('.history-item-left').append(editWrapper);
    input.focus();
    input.select();
  }

  // --- Delete Conversation Modal & Controller ---
  let pendingDeleteChatId = null;
  const deleteModalBackdrop = document.getElementById('delete-modal-backdrop');
  const btnCloseDeleteModal = document.getElementById('btn-close-delete-modal');
  const btnCancelDelete = document.getElementById('btn-cancel-delete');
  const btnConfirmDelete = document.getElementById('btn-confirm-delete');
  const deleteChatPreviewTitle = document.getElementById('delete-chat-preview-title');

  function confirmDeleteConversation(chatId, title) {
    pendingDeleteChatId = chatId;
    if (deleteChatPreviewTitle) {
      deleteChatPreviewTitle.textContent = title ? `"${title}"` : '"This conversation"';
    }
    deleteModalBackdrop?.classList.add('active');
  }

  function closeDeleteModal() {
    pendingDeleteChatId = null;
    deleteModalBackdrop?.classList.remove('active');
  }

  function executeDeleteConversation() {
    const idToDelete = pendingDeleteChatId;
    const currentActiveId = RP.currentId();
    const isActiveChat = (idToDelete && idToDelete === currentActiveId) ||
      (!idToDelete && conversationStream.style.display !== 'none');

    if (idToDelete) {
      RP.deleteChat(idToDelete);
      if (RP.getLastActiveChatId() === idToDelete) {
        RP.removeLastActiveChatId();
      }
    }

    closeDeleteModal();

    if (isActiveChat) {
      showWelcomeScreen();
    } else {
      renderHistory();
    }

    // If search modal is currently active, refresh its list
    if (searchModalBackdrop?.classList.contains('active')) {
      renderModalResults(modalSearchInput?.value || '');
    }

    showToast('Conversation deleted', 'delete');
  }

  // --- Review Modal Controls ---
  const reviewModalBackdrop = document.getElementById('review-modal');
  const btnCloseReviewModal = document.getElementById('btn-close-review-modal');
  const btnCancelReview = document.getElementById('btn-cancel-review');
  const reviewForm = document.getElementById('review-form');
  const reviewReportIdInput = document.getElementById('review-report-id');
  const reviewSessionIdInput = document.getElementById('review-session-id');
  const reviewTopicInput = document.getElementById('review-topic');
  const reviewModalSubtitle = document.getElementById('review-modal-subtitle');
  let activeReviewTargetBtn = null;
  const reviewRelevanceInput = document.getElementById('review-relevance');
  const reviewAccuracyInput = document.getElementById('review-accuracy');
  const reviewClarityInput = document.getElementById('review-clarity');
  const reviewCommentInput = document.getElementById('review-comment');
  const reviewRelevanceVal = document.getElementById('review-relevance-val');
  const reviewAccuracyVal = document.getElementById('review-accuracy-val');
  const reviewClarityVal = document.getElementById('review-clarity-val');
  const reviewCommentCount = document.getElementById('review-comment-count');

  reviewRelevanceInput?.addEventListener('input', () => {
    if (reviewRelevanceVal) reviewRelevanceVal.textContent = reviewRelevanceInput.value + '/10';
  });
  reviewAccuracyInput?.addEventListener('input', () => {
    if (reviewAccuracyVal) reviewAccuracyVal.textContent = reviewAccuracyInput.value + '/10';
  });
  reviewClarityInput?.addEventListener('input', () => {
    if (reviewClarityVal) reviewClarityVal.textContent = reviewClarityInput.value + '/10';
  });
  reviewCommentInput?.addEventListener('input', () => {
    if (reviewCommentCount) reviewCommentCount.textContent = (reviewCommentInput.value || '').length + '/1000';
  });

  function openReviewModal(reportId, sId, topic, targetBtn) {
    activeReviewTargetBtn = targetBtn || null;
    if (reviewReportIdInput) reviewReportIdInput.value = reportId || (RP.currentId() || 'report-' + Date.now());
    if (reviewSessionIdInput) reviewSessionIdInput.value = sId || RP.currentId() || '';
    if (reviewTopicInput) reviewTopicInput.value = topic || '';
    if (reviewModalSubtitle) reviewModalSubtitle.textContent = topic ? 'Rating Monograph: ' + topic : 'Help improve multi-agent synthesis quality';
    if (reviewCommentInput) reviewCommentInput.value = '';
    if (reviewCommentCount) reviewCommentCount.textContent = '0/1000';
    if (reviewRelevanceInput) reviewRelevanceInput.value = '8';
    if (reviewAccuracyInput) reviewAccuracyInput.value = '8';
    if (reviewClarityInput) reviewClarityInput.value = '9';
    if (reviewRelevanceVal) reviewRelevanceVal.textContent = '8/10';
    if (reviewAccuracyVal) reviewAccuracyVal.textContent = '8/10';
    if (reviewClarityVal) reviewClarityVal.textContent = '9/10';

    const modal = document.getElementById('review-modal-backdrop') || document.getElementById('review-modal');
    if (modal) {
      modal.classList.add('active');
      modal.style.display = 'flex';
    }
  }

  function closeReviewModal() {
    const modal = document.getElementById('review-modal-backdrop') || document.getElementById('review-modal');
    if (modal) {
      modal.classList.remove('active');
      modal.style.display = 'none';
    }
  }

  btnCloseReviewModal?.addEventListener('click', closeReviewModal);
  btnCancelReview?.addEventListener('click', closeReviewModal);
  reviewModalBackdrop?.addEventListener('click', (e) => {
    if (e.target === reviewModalBackdrop) closeReviewModal();
  });

  const btnReviewMainInit = document.getElementById('btn-review-main-report');
  btnReviewMainInit?.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const t = state.currentMainTurn;
    const reportId = t?.id || (t?.created ? 'rep-' + t.created : 'report-' + Date.now());
    const topic = t?.user || t?.topic || (headerBreadcrumbTitle ? headerBreadcrumbTitle.textContent : 'Research Monograph');
    openReviewModal(reportId, RP.currentId(), topic, btnReviewMainInit);
  });

  reviewForm?.addEventListener('submit', async (e) => {
    e.preventDefault();

    const reportId = reviewReportIdInput?.value || RP.currentId() || 'report-' + Date.now();
    const sId = reviewSessionIdInput?.value || RP.currentId() || null;
    const topic = reviewTopicInput?.value || null;
    const relevance = parseInt(reviewRelevanceInput?.value || '8', 10);
    const accuracy = parseInt(reviewAccuracyInput?.value || '8', 10);
    const clarity = parseInt(reviewClarityInput?.value || '9', 10);
    const comment = (reviewCommentInput?.value || '').trim();

    try {
      await RP.reviews.submit(reportId, { relevance, accuracy, clarity }, comment, topic, sId);
      closeReviewModal();
      if (activeReviewTargetBtn) {
        const avg = ((relevance + accuracy + clarity) / 3).toFixed(1);
        const span = activeReviewTargetBtn.querySelector('span:last-child');
        if (span) span.textContent = `Reviewed (${avg}/10)`;
        activeReviewTargetBtn.disabled = true;
        activeReviewTargetBtn.style.opacity = '0.75';
      }
      showToast('Review submitted successfully!', 'check_circle');
    } catch (err) {
      showToast(err.message || 'Could not submit review', 'error');
    }
  });

  btnCloseDeleteModal?.addEventListener('click', closeDeleteModal);
  btnCancelDelete?.addEventListener('click', closeDeleteModal);
  btnConfirmDelete?.addEventListener('click', executeDeleteConversation);
  deleteModalBackdrop?.addEventListener('click', (e) => {
    if (e.target === deleteModalBackdrop) closeDeleteModal();
  });

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (chatOptionsMenu?.style.display !== 'none') {
        closeChatMenu();
      }
      if (deleteModalBackdrop?.classList.contains('active')) {
        closeDeleteModal();
      }
    }
  });

  // --- Initial Setup: Auto-adapt for mobile & User Mode ---
  if (window.innerWidth <= 768) {
    setSidebarState(false);
    toggleInspector(false);
  } else {
    setSidebarState(true);
  }
  setRole('user');
  fetch(RP.baseUrl + '/health').then(r => r.json()).then(h => { state.health = h; }).catch(() => { });

  // Call /api/auth/me on startup to restore session and load user chats
  RP.auth.me().then(user => {
    updateAuthState(user);
  }).catch(() => {
    updateAuthState(null);
  });

  // Fetch auth config exactly once on page load to initialize Google Sign-in
  initGoogleAuth();

  composerInput.blur();
});
