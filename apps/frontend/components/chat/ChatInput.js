// Pill-shaped input with two trailing buttons:
//   - send (↑) when there is trimmed text
//   - mic when the field is empty
//
// While recording, the row is replaced by a recording bar: red pulsing
// dot, mm:ss timer, cancel (×), and send (↑). The recorder comes from
// expo-audio's useAudioRecorder hook (the imperative AudioRecorder class
// is NOT a runtime export in 1.1.x — only the hook + factory are).
import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  Animated,
  Easing,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from 'expo-audio';

import { colors, spacing, borders, typography } from '../../theme';
import Text from '../ui/Text';

// Hard cap so a stuck recorder doesn't fill disk. The Rails uploader caps
// at 25MB; HIGH_QUALITY m4a is ~16KB/s → 60s ≈ 1MB. 2 minutes is plenty
// for a chat voice message and well under the storage cap.
const MAX_DURATION_MS = 120_000;

function formatElapsed(ms) {
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function ChatInput({
  onSend,
  onSendVoice,
  disabled = false,
  placeholder = 'Escribe un mensaje...',
}) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [permError, setPermError] = useState(false);
  const inputRef = useRef(null);
  const startedAtRef = useRef(null);
  const elapsedTimerRef = useRef(null);
  const autoStopTimerRef = useRef(null);
  const pulseAnim = useRef(new Animated.Value(0)).current;

  // Hook returns an `AudioRecorder` shared object. Reused across recordings.
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);

  const canSend = text.trim().length > 0 && !disabled;
  const canRecord = !disabled && typeof onSendVoice === 'function';

  useEffect(() => {
    if (!recording) {
      pulseAnim.setValue(0);
      return undefined;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 0, duration: 600, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [recording, pulseAnim]);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    const message = text.trim();
    setText('');
    onSend(message);
    inputRef.current?.focus();
  }, [canSend, text, onSend]);

  const stopElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
  }, []);

  const startRecording = useCallback(async () => {
    console.log('[chat-input] mic press canRecord=', canRecord);
    if (!canRecord) return;
    setPermError(false);

    const status = await requestRecordingPermissionsAsync();
    const granted = status?.granted === true || status?.status === 'granted';
    console.log('[chat-input] mic permission granted=', granted);
    if (!granted) {
      setPermError(true);
      return;
    }

    try {
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
        shouldPlayInBackground: false,
      });
      await recorder.prepareToRecordAsync();
      recorder.record();
    } catch (err) {
      console.warn('[chat-input] recorder start failed', err?.message);
      setPermError(true);
      return;
    }

    startedAtRef.current = Date.now();
    setRecording(true);
    setElapsed(0);
    elapsedTimerRef.current = setInterval(() => {
      setElapsed(Date.now() - (startedAtRef.current || Date.now()));
    }, 250);
    autoStopTimerRef.current = setTimeout(() => {
      console.log('[chat-input] auto-stop at MAX_DURATION_MS');
      finishRecording();
    }, MAX_DURATION_MS);
  // finishRecording is captured by closure; intentionally omitted from deps
  // to avoid a render cycle that would re-create the timeout.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRecord, recorder]);

  const cancelRecording = useCallback(async () => {
    console.log('[chat-input] cancel');
    stopElapsedTimer();
    setRecording(false);
    setElapsed(0);
    try { await recorder.stop(); } catch {}
    try {
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch {}
  }, [recorder, stopElapsedTimer]);

  const finishRecording = useCallback(async () => {
    console.log('[chat-input] finish (stopping)');
    stopElapsedTimer();
    setRecording(false);
    const startedAt = startedAtRef.current;
    startedAtRef.current = null;

    let uri = null;
    try {
      await recorder.stop();
      uri = recorder.uri || null;
    } catch (err) {
      console.warn('[chat-input] recorder stop failed', err?.message);
    }
    try {
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
    } catch {}
    setElapsed(0);

    const durationSeconds = startedAt ? Math.max(0, Math.round((Date.now() - startedAt) / 1000)) : 0;
    console.log('[chat-input] finish uri=', uri, 'duration=', durationSeconds, 's');

    // Min duration guard so a stray tap doesn't upload silence.
    if (!uri || durationSeconds < 1) return;
    onSendVoice({ uri, durationSeconds, mime: 'audio/m4a' });
  }, [recorder, onSendVoice, stopElapsedTimer]);

  // Defensive cleanup if the screen unmounts while recording.
  useEffect(() => () => {
    stopElapsedTimer();
  }, [stopElapsedTimer]);

  const pulseStyle = useMemo(() => ({
    opacity: pulseAnim.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }),
    transform: [{ scale: pulseAnim.interpolate({ inputRange: [0, 1], outputRange: [0.8, 1.15] }) }],
  }), [pulseAnim]);

  if (recording) {
    return (
      <View style={styles.container}>
        <View style={[styles.inputRow, styles.recordingRow]}>
          <Pressable
            onPress={cancelRecording}
            style={styles.cancelButton}
            accessibilityRole="button"
            accessibilityLabel="Cancelar grabación"
          >
            <Ionicons name="close" size={20} color={colors.textPrimary} />
          </Pressable>
          <View style={styles.recordingMeta}>
            <Animated.View style={[styles.recordingDot, pulseStyle]} />
            <Text variant="body" color={colors.textPrimary} style={styles.recordingTimer}>
              {formatElapsed(elapsed)}
            </Text>
            <Text variant="caption" color={colors.textTertiary}>
              Grabando…
            </Text>
          </View>
          <Pressable
            onPress={finishRecording}
            style={[styles.sendButton, styles.sendButtonActive]}
            accessibilityRole="button"
            accessibilityLabel="Enviar audio"
          >
            <Text variant="label" color={colors.textInverse} style={styles.sendIcon}>
              ↑
            </Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {permError ? (
        <Text variant="caption" color={colors.error} style={styles.permError}>
          Necesitamos permiso para usar el micrófono.
        </Text>
      ) : null}
      <View style={styles.inputRow}>
        <TextInput
          ref={inputRef}
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder}
          placeholderTextColor={colors.textTertiary}
          multiline
          maxLength={10000}
          editable={!disabled}
          returnKeyType="default"
          blurOnSubmit={false}
          accessibilityLabel="Mensaje"
          accessibilityHint="Escribe un mensaje para tu avatar"
          selectionColor={colors.primary}
        />
        {canSend ? (
          <Pressable
            onPress={handleSend}
            style={({ pressed }) => [
              styles.sendButton,
              styles.sendButtonActive,
              pressed && styles.sendButtonPressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel="Enviar mensaje"
          >
            <Text
              variant="label"
              color={colors.textInverse}
              style={styles.sendIcon}
            >
              ↑
            </Text>
          </Pressable>
        ) : (
          <Pressable
            onPress={startRecording}
            disabled={!canRecord}
            style={({ pressed }) => [
              styles.sendButton,
              canRecord && styles.micButtonActive,
              pressed && canRecord && styles.sendButtonPressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel="Grabar mensaje de voz"
            accessibilityState={{ disabled: !canRecord }}
          >
            <Ionicons
              name="mic"
              size={18}
              color={canRecord ? colors.textInverse : colors.textTertiary}
            />
          </Pressable>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.background,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    paddingBottom: Platform.OS === 'ios' ? spacing.md : spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: colors.surface,
    borderRadius: borders.radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingLeft: spacing.md,
    paddingRight: spacing.xxs,
    paddingVertical: Platform.OS === 'ios' ? spacing.xs : 0,
  },
  recordingRow: {
    alignItems: 'center',
    paddingLeft: spacing.xxs,
    paddingVertical: spacing.xs,
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    fontSize: typography.sizes.md,
    color: colors.textPrimary,
    maxHeight: 120,
    paddingVertical: spacing.xs,
    lineHeight: 22,
  },
  sendButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
    marginLeft: spacing.xs,
  },
  sendButtonActive: {
    backgroundColor: colors.primary,
  },
  micButtonActive: {
    backgroundColor: colors.primary,
  },
  sendButtonPressed: {
    opacity: 0.8,
  },
  sendIcon: {
    fontSize: typography.sizes.lg,
    fontWeight: '700',
  },
  cancelButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordingMeta: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  recordingDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.error,
  },
  recordingTimer: {
    fontVariant: ['tabular-nums'],
    fontWeight: '600',
  },
  permError: {
    paddingBottom: spacing.xs,
  },
});

export default memo(ChatInput);
