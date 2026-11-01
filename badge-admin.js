(function () {
  const API_BASE_URL = (window.PORTFOLIO_API_BASE_URL || 'http://localhost:8765').replace(/\/+$/, '');
  const API_ORIGIN = new URL(API_BASE_URL).origin;
  let adminAccessToken = '';
  let sessionTimer = null;

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function setMessage(element, message, state) {
    element.textContent = message;
    element.dataset.state = state || '';
  }

  async function requestJson(path, options = {}, authenticated = true) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (authenticated && adminAccessToken) {
      headers.Authorization = `Bearer ${adminAccessToken}`;
    }

    let response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers,
        cache: options.cache || 'no-store'
      });
    } catch (error) {
      if (error instanceof TypeError) {
        throw new Error('API could not be reached. Check the Vercel API URL and its FRONTEND_ORIGINS setting.');
      }
      throw error;
    }

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error(`API returned an invalid response (HTTP ${response.status}).`);
    }

    if (response.status === 401 && authenticated && adminAccessToken) {
      signOut('Your admin session expired. Sign in again.');
    }
    if (!response.ok) {
      throw new Error(typeof payload.error === 'string'
        ? payload.error
        : `API request failed (HTTP ${response.status}).`);
    }
    return payload;
  }

  function createPortfolioCard(badge) {
    const url = new URL(String(badge.url || ''));
    if (url.protocol !== 'https:' || url.username || url.password) {
      throw new Error('Badge data contains a credential link that is not HTTPS.');
    }
    const card = createElement('article', 'badge-card custom-badge-card');
    const mark = createElement('div', 'badge-link-mark');
    mark.setAttribute('aria-hidden', 'true');
    mark.append(
      createElement('span', 'badge-link-symbol', '◇'),
      createElement('span', 'badge-link-label', 'EXTERNAL CREDENTIAL')
    );

    const title = createElement('div', 'badge-name', badge.title);
    const issuer = createElement('div', 'badge-issuer', badge.issuer);
    const description = createElement(
      'p',
      'badge-description',
      badge.description || 'Credential link added through the portfolio admin console.'
    );
    const verified = createElement('div', 'verified', 'Linked credential');
    const link = createElement('a', 'credly-link', 'View credential ↗');
    link.href = url.href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    card.append(mark, title, issuer, description, verified, link);
    return card;
  }

  async function loadPublicBadges() {
    const grid = document.querySelector('#badges .badges-grid');
    const message = document.getElementById('badge-store-status');
    if (!grid || !message) return;

    try {
      const payload = await requestJson('/api/badges', {}, false);
      if (!Array.isArray(payload.badges)) {
        throw new Error('Badge service returned an unexpected response.');
      }
      payload.badges.forEach(badge => grid.appendChild(createPortfolioCard(badge)));
      message.textContent = '';
    } catch (error) {
      setMessage(message, `Additional credentials unavailable: ${error.message}`, 'error');
    }
  }

  function renderAdminBadges(list, message, badges) {
    list.replaceChildren();
    if (!badges.length) {
      list.appendChild(createElement('p', 'empty-state', 'No custom badges saved yet.'));
      return;
    }

    badges.forEach(badge => {
      const row = createElement('article', 'managed-badge');
      const details = createElement('div', 'managed-badge-details');
      details.append(
        createElement('strong', 'managed-badge-title', badge.title),
        createElement('span', 'managed-badge-issuer', `${badge.issuer} · ${badge.url}`)
      );
      const remove = createElement('button', 'button button-danger', 'REMOVE');
      remove.type = 'button';
      remove.setAttribute('aria-label', `Remove ${badge.title}`);
      remove.addEventListener('click', async () => {
        remove.disabled = true;
        try {
          await requestJson(`/api/admin/badges/${encodeURIComponent(badge.id)}`, { method: 'DELETE' });
          await loadManagedBadges(list, message);
          setMessage(message, `${badge.title} removed from the portfolio.`, 'success');
        } catch (error) {
          remove.disabled = false;
          setMessage(message, error.message, 'error');
        }
      });
      row.append(details, remove);
      list.appendChild(row);
    });
  }

  async function loadManagedBadges(list, message) {
    const payload = await requestJson('/api/admin/badges');
    if (!Array.isArray(payload.badges)) {
      throw new Error('Badge service returned an unexpected response.');
    }
    renderAdminBadges(list, message, payload.badges);
  }

  function setWorkbenchSession(type, accessToken) {
    const frame = document.getElementById('backend-workbench');
    if (!frame.contentWindow) return;
    const message = type === 'portfolio-admin-session'
      ? { type, accessToken }
      : { type };
    frame.contentWindow.postMessage(message, API_ORIGIN);
  }

  function signOut(message) {
    if (adminAccessToken) setWorkbenchSession('portfolio-admin-logout');
    adminAccessToken = '';
    clearTimeout(sessionTimer);
    document.getElementById('backend-workbench').src = 'about:blank';
    document.getElementById('admin-dashboard').hidden = true;
    document.querySelector('.login-wrap').hidden = false;
    document.getElementById('sign-out').hidden = true;
    document.getElementById('login-form').reset();
    document.getElementById('login-password').value = '';
    document.getElementById('login-username').focus();
    if (message) setMessage(document.getElementById('login-status'), message, 'error');
  }

  async function checkBackendStatus(statusElement, button) {
    button.disabled = true;
    setMessage(statusElement, 'Checking MongoDB/RAG service…', 'loading');
    try {
      const status = await requestJson('/api/status');
      if (typeof status.mongo_ok !== 'boolean') {
        throw new Error('Backend returned an unexpected status response.');
      }
      if (!status.mongo_ok) {
        throw new Error('API is reachable, but MongoDB is not connected.');
      }
      const count = Number.isFinite(Number(status.document_count))
        ? ` · ${Number(status.document_count)} indexed docs`
        : '';
      setMessage(statusElement, `CONNECTED · MongoDB online${count}`, 'success');
    } catch (error) {
      setMessage(statusElement, error.message, 'error');
    } finally {
      button.disabled = false;
    }
  }

  function initAdmin() {
    const form = document.getElementById('badge-form');
    if (!form) return;

    const loginForm = document.getElementById('login-form');
    const loginButton = document.getElementById('login-submit');
    const loginStatus = document.getElementById('login-status');
    const loginWrap = document.querySelector('.login-wrap');
    const dashboard = document.getElementById('admin-dashboard');
    const list = document.getElementById('managed-badges');
    const message = document.getElementById('badge-admin-status');
    const backendStatus = document.getElementById('backend-status');
    const workbench = document.getElementById('backend-workbench');

    document.getElementById('api-origin-label').textContent = new URL(API_BASE_URL).host;
    document.getElementById('workbench-link').href = '#backend-workbench';
    document.getElementById('workbench-panel-link').href = '#backend-workbench';

    window.addEventListener('message', event => {
      if (event.origin !== API_ORIGIN || event.data?.type !== 'portfolio-admin-session-expired') return;
      signOut('Your admin session expired. Sign in again.');
    });
    workbench.addEventListener('load', () => {
      if (adminAccessToken) setWorkbenchSession('portfolio-admin-session', adminAccessToken);
    });

    loginForm.addEventListener('submit', async event => {
      event.preventDefault();
      loginButton.disabled = true;
      setMessage(loginStatus, 'Verifying owner credentials…', 'loading');
      const values = new FormData(loginForm);
      const credentials = {
        username: values.get('username'),
        email: values.get('email'),
        password: values.get('password')
      };

      try {
        const result = await requestJson('/api/auth/login', {
          method: 'POST',
          body: JSON.stringify(credentials)
        }, false);
        if (typeof result.access_token !== 'string' || !Number.isFinite(result.expires_in)) {
          throw new Error('Authentication service returned an unexpected response.');
        }
        adminAccessToken = result.access_token;
        const identity = await requestJson('/api/auth/session');
        document.getElementById('signed-in-identity').textContent = `${identity.username} · ${identity.email}`;
        loginForm.reset();
        loginWrap.hidden = true;
        dashboard.hidden = false;
        document.getElementById('sign-out').hidden = false;
        setMessage(loginStatus, '', '');
        await loadManagedBadges(list, message);
        workbench.src = `${API_BASE_URL}/api/workbench`;
        sessionTimer = setTimeout(
          () => signOut('Your admin session expired. Sign in again.'),
          Math.max(0, result.expires_in - 15) * 1000
        );
      } catch (error) {
        adminAccessToken = '';
        setMessage(loginStatus, error.message, 'error');
      } finally {
        loginButton.disabled = false;
      }
    });

    document.getElementById('sign-out').addEventListener('click', () => signOut('Signed out.'));
    document.getElementById('backend-check').addEventListener('click', event => {
      void checkBackendStatus(backendStatus, event.currentTarget);
    });

    form.addEventListener('submit', async event => {
      event.preventDefault();
      const values = new FormData(form);
      const badge = {
        title: String(values.get('title') || '').trim(),
        issuer: String(values.get('issuer') || '').trim(),
        description: String(values.get('description') || '').trim(),
        url: String(values.get('url') || '').trim()
      };

      if (!badge.title || badge.title.length > 120 || badge.issuer.length > 80 || badge.description.length > 280) {
        setMessage(message, 'Check the title, issuer, and description lengths.', 'error');
        return;
      }
      try {
        const url = new URL(badge.url);
        if (url.protocol !== 'https:' || url.username || url.password) {
          throw new Error('Credential links must use HTTPS and cannot contain credentials.');
        }
      } catch (error) {
        setMessage(message, error.message || 'Enter a valid HTTPS credential link.', 'error');
        return;
      }

      const submit = form.querySelector('[type="submit"]');
      submit.disabled = true;
      try {
        await requestJson('/api/admin/badges', {
          method: 'POST',
          body: JSON.stringify(badge)
        });
        form.reset();
        await loadManagedBadges(list, message);
        setMessage(message, `${badge.title} added to the portfolio.`, 'success');
      } catch (error) {
        setMessage(message, error.message, 'error');
      } finally {
        submit.disabled = false;
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('login-form')) initAdmin();
    void loadPublicBadges();
  });
})();
