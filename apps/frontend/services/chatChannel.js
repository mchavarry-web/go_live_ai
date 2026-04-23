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

const IDENTIFIER = (conversationId) =>
  JSON.stringify({ channel: 'ChatChannel', conversation_id: conversationId });

export class ChatChannel {
  constructor(conversationId) {
    this.conversationId = conversationId;
    this.ws = null;
    this.handlers = { delta: null, message: null, done: null, error: null };
    this.identifier = IDENTIFIER(conversationId);
  }

  on(event, fn) {
    this.handlers[event] = fn;
    return this;
  }

  async connect() {
    const token = await AsyncStorage.getItem('access_token');
    const base = platformConfig.getCableUrl();
    const url = `${base}?token=${encodeURIComponent(token || '')}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.ws.send(JSON.stringify({ command: 'subscribe', identifier: this.identifier }));
    };

    this.ws.onmessage = (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      // ActionCable protocol envelope: { type, identifier, message }
      if (payload.type === 'ping' || payload.type === 'welcome' || payload.type === 'confirm_subscription') return;
      if (payload.type === 'reject_subscription') {
        this.handlers.error?.({ message: 'subscription rejected' });
        return;
      }
      const body = payload.message;
      if (!body) return;
      const handler = this.handlers[body.type];
      if (handler) handler(body);
    };

    this.ws.onerror = (err) => {
      this.handlers.error?.({ message: err?.message || 'websocket error' });
    };

    this.ws.onclose = () => {
      // caller can reconnect by instantiating a new ChatChannel
    };
  }

  disconnect() {
    if (!this.ws) return;
    try {
      this.ws.send(JSON.stringify({ command: 'unsubscribe', identifier: this.identifier }));
    } catch {}
    this.ws.close();
    this.ws = null;
  }
}
