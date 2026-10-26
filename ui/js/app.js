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
    currentDossierKey: 'microplastics',
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
  const btnCloseLoginModal = document.getElementById('btn-close-login-modal');
  const loginTabUser = document.getElementById('login-tab-user');
  const loginTabAdmin = document.getElementById('login-tab-admin');
  const loginScopeTitle = document.getElementById('login-scope-title');
  const loginScopeList = document.getElementById('login-scope-list');
  const loginEmail = document.getElementById('login-email');
  const loginPassword = document.getElementById('login-password');
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
  function showToast(message, icon = 'check_circle') {
    if (!toastNotice) return;
    toastMessage.textContent = message;
    const toastIcon = toastNotice.querySelector('.material-symbols-outlined');
    if (toastIcon) toastIcon.textContent = icon;
    toastNotice.classList.add('show');
    setTimeout(() => {
      toastNotice.classList.remove('show');
    }, 2500);
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

  // --- Dummy User & Admin Credentials for Strict Verification ---
  const DUMMY_CREDENTIALS = {
    admin: {
      validIds: ['admin@platform.ai', 'admin', 'admin@research.org', 'admin.evaluator@research-lab.ai'],
      password: 'admin123',
      name: 'Admin Evaluator',
      roleTag: 'Admin',
      email: 'admin@platform.ai'
    },
    user: {
      validIds: ['user@platform.ai', 'user', 'user@research.org', 'scholar@academic-research.org'],
      password: 'user123',
      name: 'User',
      roleTag: 'User',
      email: 'user@platform.ai'
    }
  };

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
      if (profileUserName) profileUserName.textContent = 'User';
      if (profileRoleTag) profileRoleTag.textContent = 'User';

      // Update Profile Dropdown
      if (dropdownAvatarIcon) dropdownAvatarIcon.textContent = 'person';
      if (dropdownProfileName) dropdownProfileName.textContent = 'User';
      if (dropdownProfileEmail) dropdownProfileEmail.textContent = 'user@platform.ai';
      if (dropdownRoleLabel) dropdownRoleLabel.textContent = 'User Account';
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

  // Login Modal Role Controller
  let selectedLoginRole = 'user';

  function updateLoginModalUI(role) {
    selectedLoginRole = role;
    const errorBanner = document.getElementById('login-error-banner');
    if (errorBanner) errorBanner.style.display = 'none';
    if (loginPassword) {
      loginPassword.value = '';
      loginPassword.classList.remove('input-error');
    }

    if (role === 'admin') {
      loginTabAdmin?.classList.add('active');
      loginTabUser?.classList.remove('active');
      if (loginEmail) {
        loginEmail.value = 'admin@platform.ai';
        loginEmail.placeholder = 'admin@platform.ai or admin';
      }
      if (loginPassword) loginPassword.placeholder = 'Enter password (admin123)';
      if (btnLoginText) btnLoginText.textContent = 'Sign In as Admin';
      if (btnLoginIcon) btnLoginIcon.textContent = 'admin_panel_settings';
    } else {
      loginTabUser?.classList.add('active');
      loginTabAdmin?.classList.remove('active');
      if (loginEmail) {
        loginEmail.value = 'user@platform.ai';
        loginEmail.placeholder = 'user@platform.ai or user';
      }
      if (loginPassword) loginPassword.placeholder = 'Enter password (user123)';
      if (btnLoginText) btnLoginText.textContent = 'Sign In as User';
      if (btnLoginIcon) btnLoginIcon.textContent = 'login';
    }
  }

  function openLoginModal(role = (state.role === 'admin' ? 'user' : 'admin')) {
    updateLoginModalUI(role);
    loginModalBackdrop?.classList.add('active');
    setTimeout(() => loginPassword?.focus(), 150);
  }

  function closeLoginModal() {
    loginModalBackdrop?.classList.remove('active');
    const errorBanner = document.getElementById('login-error-banner');
    if (errorBanner) errorBanner.style.display = 'none';
  }

  function verifyAndAuthenticate() {
    const email = loginEmail?.value.trim().toLowerCase();
    const pass = loginPassword?.value.trim();
    const errorBanner = document.getElementById('login-error-banner');
    const errorText = document.getElementById('login-error-text');

    const creds = DUMMY_CREDENTIALS[selectedLoginRole];
    const isIdMatch = creds.validIds.some(id => id.toLowerCase() === email);
    const isPassMatch = creds.password === pass;

    if (!isIdMatch || !isPassMatch) {
      if (errorBanner && errorText) {
        errorText.textContent = selectedLoginRole === 'admin'
          ? 'Verification failed: Access denied. Admin page is restricted to verified administrators.'
          : 'Verification failed: Invalid user email or password. Access denied.';
        errorBanner.style.display = 'flex';
      }
      loginPassword?.classList.add('input-error');
      setTimeout(() => loginPassword?.classList.remove('input-error'), 1000);
      showToast('Verification failed: Access denied', 'lock');
      return false;
    }

    // Authentication succeeded!
    setRole(selectedLoginRole);
    closeLoginModal();
    showToast(
      selectedLoginRole === 'admin'
        ? 'Verified successfully: Admin Evaluator access granted'
        : 'Signed in successfully as User',
      selectedLoginRole === 'admin' ? 'admin_panel_settings' : 'verified_user'
    );
    return true;
  }

  // --- Inspector Panel Rendering ---
  function setInspectorTab(tab) {
    state.inspectorTab = tab;
    [tabBtnSources, tabBtnTrace, tabBtnAudit].forEach(btn => btn?.classList.remove('active'));
    renderInspectorContent();
  }

  function renderInspectorContent() {
    const dossier = MOCK_PLATFORM_DATA.dossiers[state.currentDossierKey];
    if (!dossier || !inspectorScrollBody) return;

    // In USER MODE: Always render ONLY sources!
    if (state.role === 'user' || state.inspectorTab === 'sources') {
      tabBtnSources?.classList.add('active');
      inspectorScrollBody.innerHTML = dossier.sources.map(s => `
        <article class="source-card ${state.activeCitationId === s.id ? 'highlighted' : ''}" id="inspector-source-${s.id}">
          <div class="source-top-row">
            <div class="source-badge-row">
              <span class="source-citation-num">[${s.id}]</span>
              <span class="source-domain-name">${s.domain}</span>
            </div>
            <span style="font-size: 0.625rem; font-weight: 600; padding: 1px 6px; border-radius: var(--radius-full); background: var(--surface-container-high);">
              Cited ${s.citationsCount} ${s.citationsCount > 1 ? 'times' : 'time'}
            </span>
          </div>
          <h4 class="source-card-title">${s.title}</h4>
          <p class="source-quote-snippet">"${s.snippet}"</p>
          <div class="source-card-bottom">
            <span style="color: ${s.isPeerReviewed ? 'var(--primary-container)' : 'var(--tertiary)'}; font-weight: 600; display: inline-flex; align-items: center; gap: 0.25rem;">
              <span class="material-symbols-outlined text-[13px]">${s.isPeerReviewed ? 'check_circle' : 'pending'}</span>
              <span>${s.isPeerReviewed ? 'Peer-Reviewed' : 'Pending Verification'}</span>
            </span>
            <a class="source-outbound-link" href="${s.url}" target="_blank" rel="noopener noreferrer">
              <span>Open</span>
              <span class="material-symbols-outlined text-[12px]">arrow_outward</span>
            </a>
          </div>
        </article>
      `).join('');
    } else if (state.role === 'admin' && state.inspectorTab === 'trace') {
      tabBtnTrace?.classList.add('active');
      inspectorScrollBody.innerHTML = dossier.agentTrace.map(step => `
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
            <p class="trace-node-detail">${MOCK_PLATFORM_DATA.systemHealth.gateway}</p>
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

  function renderModalResults(query) {
    if (!modalResultsScroll) return;
    const q = query.trim().toLowerCase();

    let filtered = MOCK_PLATFORM_DATA.historyItems;
    if (q) {
      filtered = filtered.filter(item =>
        item.title.toLowerCase().includes(q) ||
        item.snippet.toLowerCase().includes(q)
      );
    }

    if (filtered.length === 0) {
      modalResultsScroll.innerHTML = `
        <div style="text-align: center; padding: 2rem 1rem; color: var(--on-surface-variant);">
          <span class="material-symbols-outlined text-[28px] text-outline mb-1">find_in_page</span>
          <div style="font-weight: 600; font-size: 0.875rem;">No indexed dossiers found</div>
        </div>
      `;
      return;
    }

    modalResultsScroll.innerHTML = filtered.map(item => `
      <div class="modal-result-item" data-dossier-id="${item.id}">
        <h4 class="modal-result-title">${item.title}</h4>
        <p class="modal-result-snippet">${item.snippet}</p>
        <div style="margin-top: 0.25rem; font-size: 0.6875rem; color: var(--primary-container); font-weight: 600;">
          ${item.timeGroup} • Verified (Score ${item.score})
        </div>
      </div>
    `).join('');

    modalResultsScroll.querySelectorAll('.modal-result-item').forEach(el => {
      el.addEventListener('click', () => {
        closeSearchModal();
        loadDossier(el.getAttribute('data-dossier-id') || 'microplastics');
      });
    });
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

  // --- Load a Dossier / Topic ---
  function loadDossier(key) {
    if (!welcomeScreen || !conversationStream) return;
    welcomeScreen.style.display = 'none';
    conversationStream.style.display = 'flex';
    if (dynamicFollowups) dynamicFollowups.innerHTML = '';

    const dossierInfo = DOSSIER_REGISTRY[key] || {
      title: key,
      query: key
    };
    const title = dossierInfo.title;

    if (headerBreadcrumbTitle) headerBreadcrumbTitle.textContent = title;

    // Update first user query bubble text
    const firstUserQuery = document.querySelector('.chat-turn-user .user-bubble-text');
    if (firstUserQuery) firstUserQuery.textContent = dossierInfo.query;

    // Update main article headline
    const headline = document.querySelector('.article-headline');
    if (headline) headline.textContent = title;
    
    document.querySelectorAll('.history-item').forEach(h => {
      h.classList.toggle('active', h.getAttribute('data-inquiry-id') === key);
    });

    renderInspectorContent();
    showToast(`Loaded: ${title}`);
    if (window.innerWidth <= 768) {
      setSidebarState(false);
    }
    scrollToBottom();
  }

  // --- Show Welcome Screen for New Inquiry ---
  function showWelcomeScreen() {
    welcomeScreen.style.display = 'flex';
    conversationStream.style.display = 'none';
    if (headerBreadcrumbTitle) headerBreadcrumbTitle.textContent = 'New Inquiry';
    composerInput.value = '';
    composerInput.focus();
    autoResizeTextarea();
    if (window.innerWidth <= 768) {
      setSidebarState(false);
    }
  }

  // --- Append a Follow-Up in the Same Continuous Conversation Stream ---
  function appendFollowUpInStream(questionText, attachments = []) {
    if (!dynamicFollowups) return;

    // 1. Append User Question Bubble in the SAME thread
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-turn-user';
    userBubble.style.marginTop = '1.5rem';

    const attachmentsHtml = attachments && attachments.length > 0 ? `
      <div class="user-attachments-badge">
        ${attachments.map(att => `
          <span class="user-attachment-pill">
            <span class="material-symbols-outlined text-[13px]">${att.type === 'folder' ? 'folder' : 'draft'}</span>
            <span>${escapeHTML(att.name)}</span>
            ${att.count ? `<span style="opacity:0.75;">(${att.count} files)</span>` : (att.size ? `<span style="opacity:0.75;">(${att.size})</span>` : '')}
          </span>
        `).join('')}
      </div>
    ` : '';

    userBubble.innerHTML = `
      <div class="user-bubble secondary-turn">
        ${attachmentsHtml}
        <p class="user-bubble-text">${escapeHTML(questionText)}</p>
      </div>
      <div class="user-bubble-actions">
        <span class="user-bubble-time">Just now</span>
        <button class="btn-copy-prompt" type="button" title="Copy" aria-label="Copy prompt">
          <svg class="copy-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect width="14" height="14" x="8" y="8" rx="2" ry="2"></rect>
            <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
          </svg>
          <svg class="check-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display: none; color: var(--primary-container);">
            <polyline points="20 6 9 17 4 12"></polyline>
          </svg>
        </button>
      </div>
    `;
    dynamicFollowups.appendChild(userBubble);
    scrollToBottom();

    // 2. Append Assistant Definitional Response in the SAME thread
    setTimeout(() => {
      const assistantNode = document.createElement('div');
      assistantNode.className = 'chat-turn-assistant';
      assistantNode.style.marginTop = '1rem';

      assistantNode.innerHTML = `
        <div class="definitional-response-card">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
              <div style="width: 1.75rem; height: 1.75rem; border-radius: var(--radius-md); background: var(--surface-container-highest); color: var(--primary-container); display: flex; align-items: center; justify-content: center;">
                <span class="material-symbols-outlined text-[16px]">account_balance</span>
              </div>
              <div>
                <h4 style="font-size: 0.9375rem; font-weight: 600; color: var(--on-surface);">Synthesis Node</h4>
                <span style="font-size: 0.6875rem; color: var(--on-surface-variant);">Empirical Definition</span>
              </div>
            </div>
            <span style="font-size: 0.6875rem; font-weight: 600; padding: 2px 8px; border-radius: var(--radius-full); background: var(--primary-fixed); color: var(--on-primary-fixed);">
              Verified Terminology
            </span>
          </div>

          <p class="article-prose">
            ${MOCK_PLATFORM_DATA.followUpExample.answerParagraphs[0]}
          </p>
          <p class="article-prose">
            ${MOCK_PLATFORM_DATA.followUpExample.answerParagraphs[1]}
          </p>

          <!-- Analytical Distinction Matrix Card -->
          <div class="analytical-distinction-card">
            <div class="distinction-column">
              <span class="distinction-label">
                <span class="material-symbols-outlined text-[15px]">biotech</span>
                Bioaccumulation
              </span>
              <p class="distinction-body">
                ${MOCK_PLATFORM_DATA.followUpExample.distinction.leftBody}
              </p>
            </div>
            <div class="distinction-separator"></div>
            <div class="distinction-column">
              <span class="distinction-label secondary">
                <span class="material-symbols-outlined text-[15px]">stacked_line_chart</span>
                Biomagnification
              </span>
              <p class="distinction-body">
                ${MOCK_PLATFORM_DATA.followUpExample.distinction.rightBody}
              </p>
            </div>
          </div>

          <!-- Utility bar -->
          <div class="report-action-bar">
            <div class="action-buttons-group">
              <button class="btn-report-tool" type="button" onclick="navigator.clipboard.writeText('Bioaccumulation: net gradual accumulation of a xenobiotic compound within somatic tissues...'); alert('Definition copied to clipboard!');">
                <span class="material-symbols-outlined text-[15px]">content_copy</span>
                <span>Copy</span>
              </button>
            </div>
          </div>
        </div>
      `;

      dynamicFollowups.appendChild(assistantNode);
      scrollToBottom();
      showToast('Follow-up answered in current thread', 'verified');
    }, 400);
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

  // --- Simulated 4-Agent Pipeline Execution ---
  function runPipeline(topicText) {
    if (!pipelineModal) return;
    pipelineModal.classList.add('active');

    const steps = [
      { step: 1, title: 'Input Safety Guardrail Check', desc: 'Validating topic against safety & adversarial injection guardrails...' },
      { step: 2, title: 'Semantic Response Cache Lookup', desc: 'Querying Redis cache for matching past monographs...' },
      { step: 3, title: 'Search Agent Activating', desc: 'Retrieving relevant peer-reviewed papers from arXiv, PubMed, NOAA & IEEE...' },
      { step: 4, title: 'Summarize Agent Condensing', desc: 'Deduplicating evidence, extracting key facts and citations...' },
      { step: 5, title: 'Write Agent Synthesis', desc: 'Drafting structured academic editorial monograph in Newsreader format...' },
      { step: 6, title: 'Verify Agent Fact-Checking', desc: 'Comparing report claims against search findings (0 revisions needed)...' },
      { step: 7, title: 'LLM-as-a-Judge Evaluation', desc: 'Applying strict rubric: Relevance, Accuracy, and Clarity (Score: 9.6/10)...' }
    ];

    let currentStepIndex = 0;

    function stepInterval() {
      if (currentStepIndex < steps.length) {
        const s = steps[currentStepIndex];
        if (pipelineLiveTitle) pipelineLiveTitle.textContent = s.title;
        if (pipelineLiveDesc) pipelineLiveDesc.textContent = s.desc;

        const miniItem = document.getElementById(`pipeline-step-${s.step}`);
        if (miniItem) {
          miniItem.classList.add('active');
          const icon = miniItem.querySelector('.material-symbols-outlined');
          if (icon) icon.textContent = 'autorenew';
        }

        if (currentStepIndex > 0) {
          const prevItem = document.getElementById(`pipeline-step-${steps[currentStepIndex - 1].step}`);
          if (prevItem) {
            prevItem.classList.remove('active');
            prevItem.classList.add('done');
            const icon = prevItem.querySelector('.material-symbols-outlined');
            if (icon) icon.textContent = 'check_circle';
          }
        }

        currentStepIndex++;
        setTimeout(stepInterval, 500);
      } else {
        setTimeout(() => {
          pipelineModal.classList.remove('active');
          loadDossier('microplastics');

          // Reset mini icons
          for (let i = 1; i <= 7; i++) {
            const item = document.getElementById(`pipeline-step-${i}`);
            if (item) {
              item.classList.remove('active', 'done');
              const icon = item.querySelector('.material-symbols-outlined');
              if (icon) icon.textContent = 'hourglass_empty';
            }
          }
        }, 400);
      }
    }

    stepInterval();
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
  btnNewInquiry?.addEventListener('click', showWelcomeScreen);

  // History item clicks
  document.querySelectorAll('.history-item').forEach(item => {
    item.addEventListener('click', () => {
      const id = item.getAttribute('data-inquiry-id');
      loadDossier(id);
    });
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
  const SEARCH_DATABASE = [
    {
      id: 'solid-state-battery',
      title: 'Solid-State Battery Electrolyte Interfaces',
      category: 'Materials Science',
      snippet: 'Evaluates sulfide vs oxide separator durability, mechanical stack pressure dynamics, and dendrite suppression kinetics.',
      date: '5 days ago',
      type: 'inquiry'
    },
    {
      id: 'crispr-analysis',
      title: 'CRISPR Prime Editing Mechanisms',
      category: 'Biomedical Genetics',
      snippet: 'PegRNA engineered reverse transcriptase complexes and double-strand break-free precision genomic substitutions.',
      date: 'Yesterday',
      type: 'inquiry'
    },
    {
      id: 'quantum-error',
      title: 'Quantum Error Mitigation & Coherence',
      category: 'Quantum Physics',
      snippet: 'Deconstructs probabilistic error cancellation, Clifford randomized benchmarking, and fault-tolerant syndrome fidelity.',
      date: 'Today, 11:15',
      type: 'inquiry'
    },
    {
      id: 'microplastics',
      title: 'Impact of Microplastics on Marine Life',
      category: 'Marine Ecology',
      snippet: 'Examines trophic bioaccumulation velocities, cellular oxidative stress in apex predators, and 2024 benchmarks.',
      date: 'Today, 14:28',
      type: 'inquiry'
    },
    {
      id: 'stellar-dynamics',
      title: 'Stellar Dynamics & Dark Matter Halos',
      category: 'Astrophysics',
      snippet: 'Gaia DR3 kinematic anisotropy and collisionless dark matter velocity dispersion profiles in galactic halos.',
      date: 'Yesterday',
      type: 'inquiry'
    },
    {
      id: 'llm-consensus',
      title: 'Epistemic Bounds in Multi-Agent Consensus',
      category: 'Computer Science',
      snippet: 'Information entropy barriers and convergence latency in distributed LLM peer-review networks.',
      date: '3 days ago',
      type: 'inquiry'
    },
    {
      id: 'paper-perovskite',
      title: 'Perovskite-Silicon Tandem Photovoltaics (Nature 2024)',
      category: 'Renewable Energy',
      snippet: 'Self-assembled monolayer passivation achieving certified 33.9% power conversion efficiency.',
      date: 'Verified Paper',
      type: 'paper'
    },
    {
      id: 'paper-alphafold',
      title: 'Biomolecular Complex Architecture (Cell 2024)',
      category: 'Structural Biology',
      snippet: 'De novo ligand-binding pocket estimation across entire proteomic structural databases.',
      date: 'Verified Paper',
      type: 'paper'
    }
  ];

  function highlightMatches(text, query) {
    if (!query) return escapeHTML(text);
    const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escapedQuery})`, 'gi');
    return escapeHTML(text).replace(regex, '<mark class="search-highlight">$1</mark>');
  }

  function renderModalResults(query = '') {
    if (!modalResultsScroll) return;
    const q = query.trim().toLowerCase();

    let filtered = SEARCH_DATABASE;
    if (q) {
      filtered = SEARCH_DATABASE.filter(item => 
        item.title.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        item.snippet.toLowerCase().includes(q)
      );
    }

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
      el.addEventListener('click', () => {
        const id = el.getAttribute('data-search-id');
        closeSearchModal();
        loadDossier(id);
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

  // Profile Dropdown Event Handlers (Single place to login as User or Admin!)
  btnProfileTrigger?.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = profileDropdown?.classList.toggle('show');
    btnProfileTrigger?.classList.toggle('active', isOpen);
  });

  profileSwitchUser?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (state.role === 'user') {
      showToast('Already logged in as User', 'person');
      profileDropdown?.classList.remove('show');
      btnProfileTrigger?.classList.remove('active');
      return;
    }
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal('user');
  });

  profileSwitchAdmin?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (state.role === 'admin') {
      showToast('Already logged in as Admin Evaluator', 'admin_panel_settings');
      profileDropdown?.classList.remove('show');
      btnProfileTrigger?.classList.remove('active');
      return;
    }
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal('admin');
  });

  btnProfileQuickSwitch?.addEventListener('click', (e) => {
    e.stopPropagation();
    const targetRole = state.role === 'admin' ? 'user' : 'admin';
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal(targetRole);
  });

  btnProfileDetails?.addEventListener('click', (e) => {
    e.stopPropagation();
    profileDropdown?.classList.remove('show');
    btnProfileTrigger?.classList.remove('active');
    openLoginModal(state.role);
  });

  // Close profile dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (profileContainer && !profileContainer.contains(e.target)) {
      profileDropdown?.classList.remove('show');
      btnProfileTrigger?.classList.remove('active');
    }
  });

  // Login Modal Event Listeners
  btnCloseLoginModal?.addEventListener('click', closeLoginModal);
  loginModalBackdrop?.addEventListener('click', (e) => {
    if (e.target === loginModalBackdrop) closeLoginModal();
  });

  loginTabUser?.addEventListener('click', () => updateLoginModalUI('user'));
  loginTabAdmin?.addEventListener('click', () => updateLoginModalUI('admin'));

  document.getElementById('btn-submit-login')?.addEventListener('click', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  });

  loginForm?.addEventListener('submit', (e) => {
    e.preventDefault();
    verifyAndAuthenticate();
  });

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

  function downloadReportPDF() {
    const article = document.querySelector('.editorial-article');
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

  function downloadReportDOC() {
    const article = document.querySelector('.editorial-article');
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

  function downloadReportTXT() {
    const article = document.querySelector('.editorial-article');
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
    if (downloadDropdownWrapper && !downloadDropdownWrapper.contains(e.target)) {
      downloadFormatMenu?.classList.remove('show');
    }
  });

  // Password Visibility Toggle in Login Modal
  document.getElementById('btn-toggle-password')?.addEventListener('click', () => {
    if (!loginPassword) return;
    const isPass = loginPassword.type === 'password';
    loginPassword.type = isPass ? 'text' : 'password';
    const toggleIcon = document.getElementById('icon-toggle-password');
    if (toggleIcon) toggleIcon.textContent = isPass ? 'visibility_off' : 'visibility';
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
      loadDossier('microplastics');
      if (retryIcon) retryIcon.classList.remove('spin-refresh');
      showToast('Research synthesis regenerated', 'refresh');
    }, 450);
  });

  // --- Initial Setup: Auto-adapt for mobile & User Mode ---
  if (window.innerWidth <= 768) {
    setSidebarState(false);
    toggleInspector(false);
  } else {
    setSidebarState(true);
  }
  setRole('user');
  setupCitations();
});
