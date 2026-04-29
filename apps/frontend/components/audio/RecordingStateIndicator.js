// Tiny ●REC pulse + duration label. Used inside RecordingBar.
import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import Text from '../ui/Text';
import { colors, spacing } from '../../theme';

function formatDuration(totalSeconds) {
  const s = Math.max(0, Math.floor(totalSeconds || 0));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

export default function RecordingStateIndicator({ status, durationSeconds = 0 }) {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (status !== 'recording') return undefined;
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.4, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1.0, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [status, pulse]);

  const dotColor =
    status === 'recording' ? colors.error :
    status === 'paused'    ? colors.warning :
                             colors.textTertiary;
  const label =
    status === 'recording' ? 'REC' :
    status === 'paused'    ? 'EN PAUSA' :
    status === 'ready'     ? 'LISTO' :
                             'INACTIVO';

  return (
    <View style={styles.row}>
      <Animated.View
        style={[styles.dot, { backgroundColor: dotColor, opacity: pulse }]}
      />
      <Text variant="caption" color={colors.textPrimary} style={styles.label}>
        {label}
      </Text>
      {status === 'recording' || status === 'paused' ? (
        <Text variant="caption" color={colors.textSecondary} style={styles.duration}>
          {formatDuration(durationSeconds)}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  label: { letterSpacing: 1 },
  duration: { marginLeft: spacing.xs, fontVariant: ['tabular-nums'] },
});
