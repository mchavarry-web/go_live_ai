// Persistent FIFO queue for audio chunk uploads. Survives app kills via
// AsyncStorage and retries on AppState=active and NetInfo reconnect.
//
// Each entry is the metadata Rails needs to accept the chunk plus a
// stable client-side idempotency key, so a 202 we never received doesn't
// produce a duplicate row. Rails' AudioChunksController returns 200 with
// the existing chunk on duplicate sequence_number, so retries are safe
// either way — the key is for audit only.
import AsyncStorage from '@react-native-async-storage/async-storage';
// expo-file-system v19+ moved deleteAsync to the /legacy entry; the
// modular File class API is fine too, but legacy keeps the call site
// short and one-shot. We only delete chunk files post-upload.
import * as FileSystem from 'expo-file-system/legacy';
import NetInfo from '@react-native-community/netinfo';
import { AppState } from 'react-native';

import apiService from './apiService';

const STORAGE_KEY = 'audio_upload_queue_v1';
const MAX_ATTEMPTS = 5;

// Random uuid v4 — RN doesn't ship one and we don't want to add a dep.
function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

class AudioUploader {
  constructor() {
    this.queue = [];
    this.draining = false;
    this.loaded = false;
    this.subscriptions = [];
    this.listeners = new Set();
  }

  async load() {
    if (this.loaded) return;
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      this.queue = raw ? JSON.parse(raw) : [];
    } catch {
      this.queue = [];
    }
    this.loaded = true;
    this._emit();
  }

  async _persist() {
    try {
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(this.queue));
    } catch {
      // best-effort persistence
    }
  }

  start() {
    // Re-drain on reconnect and on app coming to foreground.
    const net = NetInfo.addEventListener((state) => {
      if (state.isConnected) this.drain();
    });
    const sub = AppState.addEventListener('change', (next) => {
      if (next === 'active') this.drain();
    });
    this.subscriptions.push(net, sub);
  }

  stop() {
    this.subscriptions.forEach((s) => {
      try {
        s.remove ? s.remove() : s();
      } catch {
        /* noop */
      }
    });
    this.subscriptions = [];
  }

  subscribe(listener) {
    this.listeners.add(listener);
    listener({ pending: this.queue.length });
    return () => this.listeners.delete(listener);
  }

  _emit() {
    const snapshot = { pending: this.queue.length };
    this.listeners.forEach((l) => {
      try {
        l(snapshot);
      } catch {
        /* noop */
      }
    });
  }

  async enqueue({
    sessionId,
    sequenceNumber,
    startedAt,
    durationSeconds,
    localUri,
    mime = 'audio/m4a',
  }) {
    await this.load();
    const entry = {
      idempotencyKey: uuid(),
      sessionId,
      sequenceNumber,
      startedAt,
      durationSeconds,
      localUri,
      mime,
      attempts: 0,
      status: 'pending',
    };
    this.queue.push(entry);
    await this._persist();
    this._emit();
    console.log(
      '[audio-up] enqueue session=', sessionId,
      'seq=', sequenceNumber,
      'duration=', durationSeconds, 's',
      'mime=', mime,
      'queueLen=', this.queue.length,
      'idempotency=', entry.idempotencyKey,
    );
    this.drain();
  }

  async drain() {
    await this.load();
    if (this.draining) return;
    if (this.queue.length === 0) return;

    this.draining = true;
    try {
      while (this.queue.length > 0) {
        const head = this.queue[0];
        if (head.status === 'failed') {
          // Skip permanently failed entries — caller can clear them
          // explicitly via clearFailed(). Move them to the back so the
          // rest of the queue isn't blocked.
          this.queue.push(this.queue.shift());
          continue;
        }
        const t0 = Date.now();
        console.log(
          '[audio-up] POST session=', head.sessionId,
          'seq=', head.sequenceNumber,
          'attempt=', head.attempts + 1, '/', MAX_ATTEMPTS,
        );
        const result = await apiService.uploadAudioChunk(head);
        const tookMs = Date.now() - t0;
        if (result.success) {
          console.log(
            '[audio-up] OK session=', head.sessionId,
            'seq=', head.sequenceNumber,
            'http=', result.status,
            'took=', tookMs, 'ms',
          );
          this.queue.shift();
          await this._persist();
          this._emit();
          // Best-effort cleanup; ignore failures (file may already be gone).
          try {
            await FileSystem.deleteAsync(head.localUri, { idempotent: true });
          } catch {
            /* noop */
          }
        } else {
          head.attempts += 1;
          const willGiveUp = head.attempts >= MAX_ATTEMPTS;
          if (willGiveUp) head.status = 'failed';
          await this._persist();
          this._emit();
          console.warn(
            '[audio-up]', willGiveUp ? 'DEAD' : 'FAIL',
            'session=', head.sessionId,
            'seq=', head.sequenceNumber,
            'attempt=', head.attempts, '/', MAX_ATTEMPTS,
            'http=', result.status,
            'took=', tookMs, 'ms',
            'reason=', result.error,
          );
          // Stop draining on failure — likely a transient network issue.
          // We'll retry on the next AppState/NetInfo trigger.
          break;
        }
      }
    } finally {
      this.draining = false;
    }
  }

  // Diagnostic / UI helpers.

  pendingCount() {
    return this.queue.filter((q) => q.status !== 'failed').length;
  }

  failedCount() {
    return this.queue.filter((q) => q.status === 'failed').length;
  }

  async clearFailed() {
    await this.load();
    this.queue = this.queue.filter((q) => q.status !== 'failed');
    await this._persist();
    this._emit();
  }

  async clearAll() {
    await this.load();
    this.queue = [];
    await this._persist();
    this._emit();
  }
}

export default new AudioUploader();
