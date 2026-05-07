// Plays the assistant's TTS audio reply.
//
// The Rails audio endpoint requires a JWT bearer header, which an HTMLAudio
// element / expo-audio player cannot send. So:
//   1. Fetch bytes via apiService (with auth) → save to a cache file URI
//      (native) or wrap in a Blob URL (web).
//   2. Hand the local URI to a fresh AudioPlayer and play.
//
// We keep a single "active" player so a new audio frame stops whatever was
// playing — the avatar doesn't talk over itself.
import { Platform } from 'react-native';
// expo-file-system 19 split: the new top-level entry exposes File/Paths
// classes only; the cacheDirectory + downloadAsync helpers live at
// /legacy (matching what services/audioUploader.js uses).
import * as FileSystem from 'expo-file-system/legacy';
import { createAudioPlayer, setAudioModeAsync } from 'expo-audio';

import platformConfig from '../utils/platformConfig';
import apiService from './apiService';

let activePlayer = null;
// Track which message is currently in the player so a re-tap of the same
// bubble during playback toggles pause; tapping a different bubble
// replaces it.
let activeMessageId = null;
const blobUrls = new Map(); // web: messageId → ObjectURL (revoked on cleanup)

function cacheUriFor(messageId) {
  // expo-file-system 19+ exposes cacheDirectory; on web it's null.
  const dir = FileSystem.cacheDirectory;
  if (!dir) return null;
  return `${dir}msg-${messageId}.mp3`;
}

async function ensureCachedNative(messageId) {
  const path = cacheUriFor(messageId);
  if (!path) return null;
  // Reuse the cache when present — TTS replies are immutable.
  try {
    const info = await FileSystem.getInfoAsync(path);
    if (info.exists && info.size > 0) return path;
  } catch {
    // proceed to (re)download
  }

  const apiUrl = platformConfig.getApiUrl();
  const url = `${apiUrl}/chat/messages/${encodeURIComponent(messageId)}/audio`;
  const token = await apiService.getRawAccessToken();
  const result = await FileSystem.downloadAsync(url, path, {
    headers: { Authorization: token ? `Bearer ${token}` : '' },
  });
  if (!result || result.status >= 400) {
    console.warn('[audio-play] download failed', result?.status);
    return null;
  }
  return result.uri;
}

async function ensureCachedWeb(messageId) {
  const cached = blobUrls.get(messageId);
  if (cached) return cached;
  const apiUrl = platformConfig.getApiUrl();
  const url = `${apiUrl}/chat/messages/${encodeURIComponent(messageId)}/audio`;
  const token = await apiService.getRawAccessToken();
  const response = await fetch(url, {
    headers: { Authorization: token ? `Bearer ${token}` : '' },
  });
  if (!response.ok) {
    console.warn('[audio-play] fetch failed', response.status);
    return null;
  }
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  blobUrls.set(messageId, objectUrl);
  return objectUrl;
}

async function ensureCached(messageId) {
  return Platform.OS === 'web'
    ? ensureCachedWeb(messageId)
    : ensureCachedNative(messageId);
}

function teardownActive() {
  if (!activePlayer) return;
  try { activePlayer.pause(); } catch {}
  try { activePlayer.remove?.(); } catch {}
  activePlayer = null;
  activeMessageId = null;
}

export async function playMessageAudio(messageId) {
  if (!messageId) return false;

  // If the same message is already in the player, treat the second tap as
  // a stop/replay toggle — the user can re-tap the bubble to interrupt.
  if (activeMessageId === messageId && activePlayer) {
    try {
      // expo-audio AudioPlayer exposes `playing`; if we're paused, resume.
      if (activePlayer.playing) {
        activePlayer.pause();
        return true;
      }
      activePlayer.play();
      return true;
    } catch (err) {
      console.warn('[audio-play] toggle failed', err?.message);
      teardownActive();
    }
  }

  teardownActive();

  const uri = await ensureCached(messageId);
  if (!uri) return false;

  try {
    await setAudioModeAsync({
      allowsRecording: false,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    });
  } catch {
    // setAudioModeAsync is a no-op on web; tolerate failure.
  }

  try {
    const player = createAudioPlayer({ uri });
    activePlayer = player;
    activeMessageId = messageId;
    player.play();
    console.log('[audio-play] playing message=', messageId, 'uri=', uri);
    return true;
  } catch (err) {
    console.warn('[audio-play] player failed', err?.message);
    teardownActive();
    return false;
  }
}

export function stopMessageAudio() {
  teardownActive();
}

export function cleanupBlobUrls() {
  // Call on logout / app teardown so we don't leak ObjectURLs on web.
  blobUrls.forEach((url) => {
    try { URL.revokeObjectURL(url); } catch {}
  });
  blobUrls.clear();
}
