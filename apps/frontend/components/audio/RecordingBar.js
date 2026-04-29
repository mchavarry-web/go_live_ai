// Persistent bottom bar that floats above the tab navigator. When idle
// it offers a tappable "Activar entrenamiento por audio" strip; while
// recording it shows the live state + a stop button. Pending uploads
// from the offline queue surface as a small badge.
import React, { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import Text from '../ui/Text';
import { colors, spacing, borders } from '../../theme';
import { useAudioRecording } from '../../contexts/AudioRecordingContext';
import RecordingStateIndicator from './RecordingStateIndicator';

// Bottom-tab bar reserves ~85pt; we float just above it.
const TAB_BAR_HEIGHT = 85;

export default function RecordingBar() {
  const navigation = useNavigation();
  const { status, session, pendingUploads, stop, start } = useAudioRecording();
  const [seconds, setSeconds] = useState(0);
  const startedAtRef = useRef(null);

  useEffect(() => {
    if (status === 'recording') {
      startedAtRef.current = startedAtRef.current || Date.now();
      const t = setInterval(() => {
        setSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }, 500);
      return () => clearInterval(t);
    }
    startedAtRef.current = null;
    setSeconds(0);
    return undefined;
  }, [status]);

  // The bar is mounted at the root (alongside MainTabs), but the audio
  // screens live inside ProfileTab → ProfileStack. Targeting a nested
  // screen from root requires the {screen, params} payload form so React
  // Navigation can walk into the right child navigator.
  const goToVoiceEnrollment = () =>
    navigation.navigate('ProfileTab', { screen: 'VoiceEnrollment' });

  // ── Idle: collapsed strip prompting the user to enable the feature ──
  if (status === 'idle') {
    return (
      <Pressable
        style={styles.idleBar}
        onPress={goToVoiceEnrollment}
        accessibilityLabel="Activar entrenamiento por audio"
      >
        <Ionicons name="mic-off" size={16} color={colors.textSecondary} />
        <Text variant="caption" color={colors.textSecondary} style={styles.idleText}>
          Activar entrenamiento por audio
        </Text>
        <Ionicons name="chevron-forward" size={14} color={colors.textTertiary} />
      </Pressable>
    );
  }

  // ── Ready: a quick "start" tap with pending-upload tail ──
  if (status === 'ready') {
    return (
      <View style={styles.bar}>
        <Pressable
          style={styles.leftAction}
          onPress={() => start()}
          accessibilityLabel="Iniciar grabación"
        >
          <Ionicons name="mic" size={18} color={colors.primary} />
          <Text variant="caption" color={colors.textPrimary} style={styles.leftLabel}>
            Iniciar entrenamiento
          </Text>
        </Pressable>
        {pendingUploads > 0 && (
          <View style={styles.badge}>
            <Ionicons name="cloud-upload-outline" size={12} color={colors.textInverse} />
            <Text variant="caption" color={colors.textInverse} style={styles.badgeText}>
              {pendingUploads}
            </Text>
          </View>
        )}
      </View>
    );
  }

  // ── Recording / paused: live state + stop ──
  return (
    <View style={styles.bar}>
      <RecordingStateIndicator status={status} durationSeconds={seconds} />
      <View style={styles.rightSide}>
        {pendingUploads > 0 && (
          <Text variant="caption" color={colors.textTertiary} style={styles.pendingText}>
            {pendingUploads} pendiente{pendingUploads === 1 ? '' : 's'}
          </Text>
        )}
        <Pressable
          style={styles.stopButton}
          onPress={() => stop()}
          accessibilityLabel="Detener grabación"
        >
          <Ionicons name="stop" size={14} color={colors.textInverse} />
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  idleBar: {
    position: 'absolute',
    left: spacing.md,
    right: spacing.md,
    bottom: TAB_BAR_HEIGHT + spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: borders.radius.full,
    backgroundColor: colors.surface,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.xs,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  idleText: { flex: 1, marginLeft: spacing.xs },

  bar: {
    position: 'absolute',
    left: spacing.md,
    right: spacing.md,
    bottom: TAB_BAR_HEIGHT + spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: borders.radius.lg,
    backgroundColor: colors.elevated,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },
  leftAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  leftLabel: { marginLeft: spacing.xs },
  rightSide: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  pendingText: { fontVariant: ['tabular-nums'] },
  stopButton: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.error,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: colors.primary,
    borderRadius: borders.radius.full,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
  },
  badgeText: { fontWeight: '700' },
});
