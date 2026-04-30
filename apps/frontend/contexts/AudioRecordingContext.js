// Global recording state. Lives next to AuthContext so it survives route
// transitions and tab switches. Also drives the chunk-rotation timer:
// every CHUNK_MINUTES we stop the active recording, hand the file to the
// upload queue, and start a fresh one without exposing the seam to the
// caller.
//
// Status machine:
//   idle       — feature off / not started yet
//   enrolling  — voice enrollment in progress (no session yet)
//   ready      — enrolled, no active session
//   recording  — active session, mic capturing
//   paused     — active session, mic stopped (UI affordance for now)
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';

import apiService from '../services/apiService';
import audioUploader from '../services/audioUploader';
import { useAuth } from './AuthContext';

const CHUNK_MINUTES = 5;
const CHUNK_MS = CHUNK_MINUTES * 60 * 1000;

const AudioRecordingContext = createContext(null);

export function useAudioRecording() {
  const ctx = useContext(AudioRecordingContext);
  if (!ctx) throw new Error('useAudioRecording must be used within AudioRecordingProvider');
  return ctx;
}

export function AudioRecordingProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const [status, setStatus] = useState('idle'); // idle | ready | recording | paused
  const [session, setSession] = useState(null); // { id, startedAt, sequenceNumber }
  const [enrollment, setEnrollment] = useState(null);
  const [pendingUploads, setPendingUploads] = useState(0);
  const [error, setError] = useState(null);

  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const sessionRef = useRef(null);
  const sequenceRef = useRef(0);
  const chunkStartRef = useRef(null);
  const rotationTimerRef = useRef(null);

  // ── boot: load uploader queue + enrollment + start auto-drain ───────
  // Gated on auth: hitting /audio/voice_enrollment without a JWT triggers
  // apiService's auto-logout path and surfaces a spurious "invalid token"
  // error on the very first launch.
  useEffect(() => {
    if (!isAuthenticated) {
      setEnrollment(null);
      setStatus('idle');
      return undefined;
    }
    audioUploader.load().then(() => {
      setPendingUploads(audioUploader.pendingCount());
    });
    const unsub = audioUploader.subscribe((s) => setPendingUploads(s.pending));
    audioUploader.start();
    refreshEnrollment();
    return () => {
      unsub();
      audioUploader.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  const refreshEnrollment = useCallback(async () => {
    const res = await apiService.getVoiceEnrollment();
    if (res.success) {
      const e = res.data?.enrollment || res.data || null;
      setEnrollment(e);
      if (e && e.status === 'ready' && status === 'idle') setStatus('ready');
    }
  }, [status]);

  const ensurePermission = useCallback(async () => {
    const res = await AudioModule.requestRecordingPermissionsAsync();
    return res.granted === true || res.status === 'granted';
  }, []);

  // ── chunk rotation ────────────────────────────────────────────────
  // Every CHUNK_MS, stop the recorder (which finalizes the file and gives
  // us the URI), enqueue the file for upload, then start a new recorder.
  const rotateChunk = useCallback(async ({ final = false } = {}) => {
    const sess = sessionRef.current;
    if (!sess) return;

    const startedAt = chunkStartRef.current || new Date().toISOString();
    const endAt = new Date();
    const durationSeconds = Math.max(
      0,
      Math.round((endAt - new Date(startedAt)) / 1000),
    );
    const sequenceNumber = sequenceRef.current++;

    let localUri = null;
    try {
      await recorder.stop();
      localUri = recorder.uri || null;
    } catch (err) {
      // If stop fails we can't recover the file; mark error and continue.
      console.warn('[Audio] recorder.stop failed', err);
    }

    if (localUri) {
      await audioUploader.enqueue({
        sessionId: sess.id,
        sequenceNumber,
        startedAt,
        durationSeconds,
        localUri,
      });
    }

    if (final) return;

    // Start the next chunk immediately. Any small gap (~50–150ms) is OK.
    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
      chunkStartRef.current = new Date().toISOString();
    } catch (err) {
      console.error('[Audio] failed to start next chunk', err);
      setError('No se pudo continuar la grabación.');
      setStatus('ready');
    }
  }, [recorder]);

  const _scheduleRotation = useCallback(() => {
    if (rotationTimerRef.current) clearTimeout(rotationTimerRef.current);
    rotationTimerRef.current = setTimeout(() => {
      rotateChunk().finally(() => _scheduleRotation());
    }, CHUNK_MS);
  }, [rotateChunk]);

  const _clearRotation = useCallback(() => {
    if (rotationTimerRef.current) {
      clearTimeout(rotationTimerRef.current);
      rotationTimerRef.current = null;
    }
  }, []);

  // ── public API ─────────────────────────────────────────────────────
  const start = useCallback(async () => {
    setError(null);
    if (!enrollment || enrollment.status !== 'ready') {
      setError('Necesitás completar el enrolamiento de voz primero.');
      return { success: false, reason: 'enrollment_required' };
    }
    const ok = await ensurePermission();
    if (!ok) {
      setError('Necesitamos permiso para usar el micrófono.');
      return { success: false, reason: 'permission_denied' };
    }

    const created = await apiService.createAudioSession();
    if (!created.success) {
      setError(created.error || 'No se pudo crear la sesión de audio.');
      return { success: false, reason: 'server_error' };
    }
    const sess = created.data?.session || created.data;
    sessionRef.current = sess;
    sequenceRef.current = 0;

    await setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    });

    try {
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (err) {
      console.error('[Audio] failed to start recording', err);
      setError('No se pudo iniciar la grabación.');
      return { success: false, reason: 'recorder_error' };
    }

    chunkStartRef.current = new Date().toISOString();
    setSession(sess);
    setStatus('recording');
    _scheduleRotation();
    return { success: true, session: sess };
  }, [enrollment, ensurePermission, recorder, _scheduleRotation]);

  const stop = useCallback(async () => {
    _clearRotation();
    const sess = sessionRef.current;
    if (!sess) {
      setStatus('ready');
      return { success: false };
    }
    await rotateChunk({ final: true });
    await apiService.finishAudioSession(sess.id);
    sessionRef.current = null;
    setSession(null);
    setStatus('ready');
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: false });
    return { success: true };
  }, [_clearRotation, rotateChunk]);

  const cancel = useCallback(async () => {
    _clearRotation();
    const sess = sessionRef.current;
    try {
      await recorder.stop();
    } catch {
      /* noop */
    }
    if (sess) await apiService.cancelAudioSession(sess.id);
    sessionRef.current = null;
    setSession(null);
    setStatus('ready');
    await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: false });
  }, [_clearRotation, recorder]);

  const enroll = useCallback(async ({ startUri, stopUri, startText, stopText }) => {
    setStatus('enrolling');
    const res = await apiService.submitVoiceEnrollment({
      startUri, stopUri, startText, stopText,
    });
    if (!res.success) {
      setStatus(enrollment?.status === 'ready' ? 'ready' : 'idle');
      setError(res.error || 'No se pudo guardar el enrolamiento.');
      return { success: false, error: res.error };
    }
    const next = res.data?.enrollment || res.data;
    setEnrollment(next);
    setStatus(next?.status === 'ready' ? 'ready' : 'idle');
    return { success: true, enrollment: next };
  }, [enrollment]);

  const resetEnrollment = useCallback(async () => {
    const res = await apiService.deleteVoiceEnrollment();
    if (res.success) {
      setEnrollment(null);
      setStatus('idle');
    }
    return res;
  }, []);

  // unmount cleanup
  useEffect(() => () => _clearRotation(), [_clearRotation]);

  const value = useMemo(() => ({
    status,
    session,
    enrollment,
    pendingUploads,
    error,
    chunkMinutes: CHUNK_MINUTES,
    start,
    stop,
    cancel,
    enroll,
    resetEnrollment,
    refreshEnrollment,
  }), [
    status, session, enrollment, pendingUploads, error,
    start, stop, cancel, enroll, resetEnrollment, refreshEnrollment,
  ]);

  return (
    <AudioRecordingContext.Provider value={value}>
      {children}
    </AudioRecordingContext.Provider>
  );
}
