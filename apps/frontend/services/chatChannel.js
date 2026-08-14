import AsyncStorage from '@react-native-async-storage/async-storage';
import platformConfig from '../utils/platformConfig';

// Minimal ActionCable client over the raw WebSocket API. We do not depend on
// `@rails/actioncable` because it expects `window`; a hand-rolled version works
// identically on ios/android/web without patching.
//
// Envelope received from the server (see ChatChannel + ChatGenerationJob):
//   { type: 'delta',   content: 'tokens' }
//   { type: 'message', message: { id, role, content, created_at } }
//   { type: 'done',    assistant_message_id }
//   { type: 'error',   message: 'human-readable error' }
//
// Reconnect policy:
//   - Transport errors (onerror / unexpected onclose) DO NOT bubble to the
//     UI. They schedule a reconnect with exponential backoff so the user
//     never sees a "websocket error" banner just because the OS killed
//     the socket while the app was backgrounded.
//   - Only `reject_subscription` (auth failure) and explicit server-emitted
//     `{ type: 'error' }` envelopes reach the `error` handler.
//   - `forceReconnect()` is exposed for the screen to call when the app
//     foregrounds, so we don't have to wait for the current backoff slot.

const IDENTIFIER = (conversationId) =>
  JSON.stringify({ channel: 'ChatChannel', conversation_id: conversationId });

const MAX_BACKOFF_MS = 30_000;
const BASE_BACKOFF_MS = 1_000;

export class ChatChannel {
  constructor(conversationId) {
    this.conversationId = conversationId;
    this.ws = null;
    this.handlers = {
      delta: null,
      message: null,
      done: null,
      error: null,
      audio: null,
      // { type: 'ack' } — ChatGenerationJob broadcasts this the moment it
      // starts, letting the screen restart its watchdog from "job started"
      // instead of timing the whole pipeline from the POST.
      ack: null,
      // Fired locally (not a server frame) when the subscription is
      // re-confirmed after a drop. Frames broadcast while the socket was
      // down are lost forever, so the screen refetches on this signal.
      resubscribed: null,
    };
    this.identifier = IDENTIFIER(conversationId);
    this.intentionallyClosed = false;
    this.reconnectAttempts = 0;
    this.reconnectTimer = null;
    this.everSubscribed = false;
  }

  on(event, fn) {
    this.handlers[event] = fn;
    return this;
  }

  async connect() {
    this.intentionallyClosed = false;
    this._clearReconnectTimer();

    const token = await AsyncStorage.getItem('access_token');
    const base = platformConfig.getCableUrl();
    const url = `${base}?token=${encodeURIComponent(token || '')}`;
    console.log('[chat-cable] connecting to', base, 'conv=', this.conversationId);

    let ws;
    try {
      ws = new WebSocket(url);
    } catch (e) {
      console.warn('[chat-cable] failed to construct WebSocket', e?.message);
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      console.log('[chat-cable] open → subscribe', this.conversationId);
      this.reconnectAttempts = 0;
      try {
        ws.send(JSON.stringify({ command: 'subscribe', identifier: this.identifier }));
      } catch (e) {
        console.warn('[chat-cable] subscribe send failed', e?.message);
      }
    };

    ws.onmessage = (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        console.warn('[chat-cable] non-JSON frame', event.data);
        return;
      }
      // ActionCable protocol envelope: { type, identifier, message }
      if (payload.type === 'ping') return;
      if (payload.type === 'welcome') {
        console.log('[chat-cable]', payload.type);
        return;
      }
      if (payload.type === 'confirm_subscription') {
        const isResubscription = this.everSubscribed;
        this.everSubscribed = true;
        console.log('[chat-cable] confirm_subscription resub=', isResubscription);
        if (isResubscription) this.handlers.resubscribed?.({});
        return;
      }
      if (payload.type === 'reject_subscription') {
        console.warn('[chat-cable] subscription rejected');
        // Auth-level failure — surface to the UI so the user can re-login.
        this.handlers.error?.({ message: 'subscription rejected' });
        return;
      }
      const body = payload.message;
      if (!body) return;
      console.log('[chat-cable] frame', body.type, body.content ? `(${body.content.length} chars)` : '');
      const handler = this.handlers[body.type];
      if (handler) handler(body);
      else console.warn('[chat-cable] no handler for', body.type);
    };

    ws.onerror = (err) => {
      // Transport-level errors are noisy and almost always followed by
      // onclose. Log but don't surface — onclose will schedule the
      // reconnect.
      console.warn('[chat-cable] transport error', err?.message);
    };

    ws.onclose = (e) => {
      console.log('[chat-cable] close code=', e?.code, 'reason=', e?.reason, 'clean=', e?.wasClean);
      this.ws = null;
      if (!this.intentionallyClosed) {
        this._scheduleReconnect();
      }
    };
  }

  forceReconnect() {
    if (this.intentionallyClosed) return;
    // Skip the backoff and try immediately. If the socket is open, leave
    // it alone; if it's down, kick a fresh connect.
    if (this.ws && this.ws.readyState === 1 /* OPEN */) return;
    this._clearReconnectTimer();
    this.reconnectAttempts = 0;
    this.connect();
  }

  _scheduleReconnect() {
    if (this.intentionallyClosed) return;
    if (this.reconnectTimer) return;
    const delay = Math.min(
      BASE_BACKOFF_MS * 2 ** this.reconnectAttempts,
      MAX_BACKOFF_MS,
    );
    this.reconnectAttempts += 1;
    console.log(
      '[chat-cable] reconnect in',
      delay,
      'ms (attempt',
      this.reconnectAttempts,
      ')',
    );
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  _clearReconnectTimer() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  disconnect() {
    this.intentionallyClosed = true;
    this._clearReconnectTimer();
    if (!this.ws) return;
    try {
      this.ws.send(JSON.stringify({ command: 'unsubscribe', identifier: this.identifier }));
    } catch {}
    try {
      this.ws.close();
    } catch {}
    this.ws = null;
  }
}
