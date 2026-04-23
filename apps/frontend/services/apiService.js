import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import platformConfig from '../utils/platformConfig';

// Thin fetch wrapper that talks to the Rails API at /api/v1/.
// Token shape is Rails's: { access_token, refresh_token, user }.
// access_token is kept in AsyncStorage under the 'access_token' key.
const config = Constants.expoConfig?.extra || {};
const API_URL = platformConfig.getApiUrl();
const API_TIMEOUT = parseInt(config.API_TIMEOUT) || 15000;
const DEBUG = config.DEBUG === 'true' || config.DEBUG === true;

class ApiService {
  constructor() {
    this.logoutCallback = null;
  }

  setLogoutCallback(cb) {
    this.logoutCallback = cb;
  }

  async getAuthHeaders(isMultipart = false) {
    const token = await AsyncStorage.getItem('access_token');
    const headers = { Authorization: token ? `Bearer ${token}` : '' };
    if (!isMultipart) headers['Content-Type'] = 'application/json';
    return headers;
  }

  async request(endpoint, options = {}) {
    const url = `${API_URL}${endpoint}`;
    const isMultipart = options.body instanceof FormData;
    const headers = await this.getAuthHeaders(isMultipart);

    const reqConfig = { headers, ...options };
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);
    reqConfig.signal = controller.signal;

    try {
      if (DEBUG) console.log(`[API] ${options.method || 'GET'} ${url}`);
      const response = await fetch(url, reqConfig);
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          if (this.logoutCallback) this.logoutCallback();
          throw new Error('Token inválido. Por favor, inicie sesión nuevamente.');
        }
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      if (DEBUG) console.log(`[API] Success: ${endpoint}`);
      return { success: true, data };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') return { success: false, error: 'Request timeout' };
      console.error(`API request failed for ${endpoint}:`, error);
      return { success: false, error: error.message };
    }
  }

  // ── Auth ──────────────────────────────────────────────────────────
  async signIn(email, password) {
    return this.request('/auth/sign_in', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  }

  async signUp({ email, password, firstName, lastName }) {
    return this.request('/auth/sign_up', {
      method: 'POST',
      body: JSON.stringify({
        email,
        password,
        first_name: firstName,
        last_name: lastName,
      }),
    });
  }

  async signInWithGoogle(idToken) {
    return this.request('/auth/google', {
      method: 'POST',
      body: JSON.stringify({ id_token: idToken }),
    });
  }

  async signInWithApple(idToken) {
    return this.request('/auth/apple', {
      method: 'POST',
      body: JSON.stringify({ id_token: idToken }),
    });
  }

  async signInWithFacebook(accessToken) {
    return this.request('/auth/facebook', {
      method: 'POST',
      body: JSON.stringify({ access_token: accessToken }),
    });
  }

  async refreshToken(refreshToken) {
    return this.request('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  }

  async me() {
    return this.request('/auth/me');
  }

  async signOut() {
    return this.request('/auth/sign_out', { method: 'DELETE' });
  }

  // ── Onboarding ───────────────────────────────────────────────────
  async getOnboardingStatus() {
    return this.request('/onboarding/status');
  }

  async completeOnboarding({ country, timezone, formalityLevel }) {
    return this.request('/onboarding/complete', {
      method: 'POST',
      body: JSON.stringify({
        country,
        timezone,
        formality_level: formalityLevel,
      }),
    });
  }

  // ── Chat ─────────────────────────────────────────────────────────
  async listConversations() {
    return this.request('/chat/conversations');
  }

  async createConversation(title) {
    return this.request('/chat/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    });
  }

  async getConversation(id) {
    return this.request(`/chat/conversations/${id}`);
  }

  async postMessage(conversationId, content) {
    return this.request(`/chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    });
  }

  async proactiveGreeting({
    localTime,
    localDate,
    absenceMinutes,
    latitude,
    longitude,
    timezone,
  }) {
    return this.request('/chat/proactive-greeting', {
      method: 'POST',
      body: JSON.stringify({
        local_time: localTime,
        local_date: localDate,
        absence_minutes: absenceMinutes,
        latitude,
        longitude,
        timezone,
      }),
    });
  }

  // ── Social connections (flat per-platform) ───────────────────────
  async socialStatus(provider) {
    return this.request(`/${provider}/status`);
  }

  async ingestSocial(provider, payload) {
    return this.request(`/${provider}/ingest`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async extractSocial(provider) {
    return this.request(`/${provider}/extract`, { method: 'POST' });
  }

  async spotifyAuthUrl() {
    return this.request('/spotify/auth_url');
  }

  // ── Device tokens ────────────────────────────────────────────────
  async registerDeviceToken({ token, platform, metadata }) {
    return this.request('/notifications/device_tokens', {
      method: 'POST',
      body: JSON.stringify({ token, platform, metadata }),
    });
  }

  async unregisterDeviceToken(token) {
    return this.request(`/notifications/device_tokens/${encodeURIComponent(token)}`, {
      method: 'DELETE',
    });
  }
}

export default new ApiService();
