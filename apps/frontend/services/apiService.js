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

// Credential-exchange endpoints. A 401 here is a failed login attempt (show
// the user a message); a 401 on any OTHER endpoint is an expired/invalid
// session (silently log out + redirect to login, no alert).
const AUTH_ENDPOINTS = [
  '/auth/sign_in',
  '/auth/sign_up',
  '/auth/google',
  '/auth/apple',
  '/auth/facebook',
  '/auth/refresh',
];

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

  // Raw token accessor for callers that need to attach the bearer outside
  // of the standard request() flow (FileSystem.downloadAsync, ws upgrade).
  async getRawAccessToken() {
    return AsyncStorage.getItem('access_token');
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
          // A 401 on a credential-exchange endpoint (explicit sign in / up /
          // provider / token refresh) is a login failure — surface a clean
          // message for the form, but do NOT trigger a global logout.
          if (AUTH_ENDPOINTS.some((p) => endpoint.startsWith(p))) {
            throw new Error(data.error || 'Credenciales inválidas.');
          }
          // A 401 on any other (authenticated) endpoint means the stored
          // token is expired/invalid: silently clear auth so the navigator
          // redirects to login. No user-facing alert — just return a benign
          // sentinel (error: null) so callers don't pop an error dialog.
          if (this.logoutCallback) this.logoutCallback();
          return { success: false, sessionExpired: true, error: null };
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

  // ── Avatar (appearance + behavior) ───────────────────────────────
  async getAvatar() {
    return this.request('/avatar');
  }

  async updateAvatar({ name, appearance, behavior, active_mode } = {}) {
    const body = {};
    if (name !== undefined) body.name = name;
    if (appearance !== undefined) body.appearance = appearance;
    if (behavior !== undefined) body.behavior = behavior;
    if (active_mode !== undefined) body.active_mode = active_mode;
    return this.request('/avatar', {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  }

  async listInsights() {
    return this.request('/avatar/insights');
  }

  async deleteInsight(id) {
    return this.request(`/avatar/insights/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  }

  async deleteAllInsights() {
    return this.request('/avatar/insights', { method: 'DELETE' });
  }

  async teachAvatar(message, category) {
    const body = { message };
    if (category) body.category = category;
    return this.request('/avatar/teach', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async disconnectSocial(provider) {
    return this.request(`/${provider}`, { method: 'DELETE' });
  }

  // ── Onboarding ───────────────────────────────────────────────────
  async getOnboardingStatus() {
    return this.request('/onboarding/status');
  }

  async completeOnboarding({ country, timezone, formalityLevel } = {}) {
    return this.request('/onboarding/complete', {
      method: 'POST',
      body: JSON.stringify({
        country,
        timezone,
        formality_level: formalityLevel,
      }),
    });
  }

  async resetOnboarding() {
    return this.request('/onboarding/reset', { method: 'POST' });
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

  // Cursor-paginated message history (DEV-95). Without params Rails returns
  // the LATEST `limit` (default 30) messages; pass `before` (a message id)
  // to fetch the page strictly older than that message. Response:
  // { messages: [...oldest→newest...], has_more: bool }.
  async getMessages(conversationId, { before, limit } = {}) {
    const parts = [];
    if (before) parts.push(`before=${encodeURIComponent(before)}`);
    if (limit) parts.push(`limit=${encodeURIComponent(limit)}`);
    const qs = parts.length ? `?${parts.join('&')}` : '';
    return this.request(`/chat/conversations/${encodeURIComponent(conversationId)}/messages${qs}`);
  }

  async postMessage(conversationId, content) {
    // Stamp the moment the client clicked Send so the backend can log
    // app→API latency on the assistant message metadata.telemetry.
    const clientSentAt = new Date().toISOString();
    return this.request(`/chat/conversations/${conversationId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, client_sent_at: clientSentAt }),
    });
  }

  // Multipart upload of a recorded voice message. Rails transcribes
  // synchronously, persists the user message with the transcript as
  // content + the m4a as a Shrine attachment, and enqueues a voice-mode
  // ChatGenerationJob (assistant reply gets TTS-rendered).
  async postVoiceMessage(conversationId, { uri, mime = 'audio/m4a', language } = {}) {
    if (!uri) return { success: false, error: 'no audio uri' };
    const url = `${API_URL}/chat/conversations/${encodeURIComponent(conversationId)}/messages/voice`;
    const headers = await this.getAuthHeaders(true);
    const form = new FormData();
    form.append('client_sent_at', new Date().toISOString());
    if (language) form.append('language', language);
    form.append('audio', {
      uri,
      name: 'voice-message.m4a',
      type: mime,
    });

    const controller = new AbortController();
    // Voice messages need transcription on the server before the response
    // returns; OpenAI's transcribe is ~1-3s for short clips. Give it 5x.
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT * 5);
    try {
      if (DEBUG) console.log(`[API] POST ${url} (voice)`);
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: form,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 && this.logoutCallback) this.logoutCallback();
        return { success: false, error: data.error || `HTTP ${response.status}`, status: response.status };
      }
      return { success: true, data, status: response.status };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') return { success: false, error: 'Request timeout' };
      return { success: false, error: error.message };
    }
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

  // ── Audio training ───────────────────────────────────────────────
  // Endpoints under /api/v1/audio/* — see AUDIO_TRAINING_PLAN.md.
  // Sessions are JSON; chunk uploads are multipart with an Idempotency-Key
  // header so retries from the offline queue are safe.
  async listAudioSessions() {
    return this.request('/audio/sessions');
  }

  async getAudioSession(id) {
    return this.request(`/audio/sessions/${encodeURIComponent(id)}`);
  }

  async createAudioSession() {
    return this.request('/audio/sessions', { method: 'POST' });
  }

  async finishAudioSession(id) {
    return this.request(`/audio/sessions/${encodeURIComponent(id)}/finish`, {
      method: 'POST',
    });
  }

  async cancelAudioSession(id) {
    return this.request(`/audio/sessions/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
    });
  }

  async deleteAudioSession(id) {
    return this.request(`/audio/sessions/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  }

  async wipeAllAudio() {
    return this.request('/audio/wipe', { method: 'POST' });
  }

  // Multipart chunk upload. ``localUri`` is a file:// path produced by
  // expo-audio. RN's FormData accepts the {uri, name, type} shape directly.
  async uploadAudioChunk({
    sessionId,
    sequenceNumber,
    startedAt,
    durationSeconds,
    localUri,
    mime = 'audio/m4a',
    idempotencyKey,
  }) {
    const url = `${API_URL}/audio/sessions/${encodeURIComponent(sessionId)}/chunks`;
    const headers = await this.getAuthHeaders(true);
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

    const form = new FormData();
    form.append('sequence_number', String(sequenceNumber));
    form.append('started_at', startedAt);
    form.append('duration_seconds', String(durationSeconds));
    form.append('audio', {
      uri: localUri,
      name: `chunk-${sequenceNumber}.m4a`,
      type: mime,
    });

    const controller = new AbortController();
    // Chunk uploads can be slow on bad networks — give them 5x the default.
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT * 5);

    try {
      if (DEBUG) console.log(`[API] POST ${url} (chunk ${sequenceNumber})`);
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: form,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 && this.logoutCallback) this.logoutCallback();
        return { success: false, error: data.error || `HTTP ${response.status}`, status: response.status };
      }
      return { success: true, data, status: response.status };
    } catch (error) {
      clearTimeout(timeoutId);
      if (error.name === 'AbortError') return { success: false, error: 'Request timeout' };
      return { success: false, error: error.message };
    }
  }

  async getVoiceEnrollment() {
    return this.request('/audio/voice_enrollment');
  }

  async deleteVoiceEnrollment() {
    return this.request('/audio/voice_enrollment', { method: 'DELETE' });
  }

  // Multipart enrollment — both phrases captured in one request.
  async submitVoiceEnrollment({ startUri, stopUri, startText, stopText, mime = 'audio/m4a' }) {
    const url = `${API_URL}/audio/voice_enrollment`;
    const headers = await this.getAuthHeaders(true);

    const form = new FormData();
    if (startText) form.append('start_phrase_text', startText);
    if (stopText) form.append('stop_phrase_text', stopText);
    if (startUri) {
      form.append('start_phrase', {
        uri: startUri,
        name: 'start-phrase.m4a',
        type: mime,
      });
    }
    if (stopUri) {
      form.append('stop_phrase', {
        uri: stopUri,
        name: 'stop-phrase.m4a',
        type: mime,
      });
    }

    try {
      const response = await fetch(url, { method: 'POST', headers, body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 && this.logoutCallback) this.logoutCallback();
        return { success: false, error: data.error || `HTTP ${response.status}` };
      }
      return { success: true, data };
    } catch (error) {
      return { success: false, error: error.message };
    }
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
