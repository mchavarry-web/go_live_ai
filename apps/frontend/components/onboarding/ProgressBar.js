// 1:1 port of gln-mobile-app/src/components/onboarding/ProgressBar.tsx.
// Accepts either:
//   - `progress` 0..1 (preferred — matches original API), or
//   - `step` + `total` (legacy — older callers in the port still use this).
import React, { memo } from 'react';
import { View, StyleSheet } from 'react-native';

import { colors, borders } from '../../theme';

function ProgressBar({ progress, step, total, height = 4, style }) {
  const computed =
    typeof progress === 'number'
      ? progress
      : typeof step === 'number' && typeof total === 'number' && total > 0
        ? step / total
        : 0;
  const clamped = Math.min(1, Math.max(0, computed));

  return (
    <View
      style={[styles.track, { height }, style]}
      accessibilityRole="progressbar"
      accessibilityValue={{
        min: 0,
        max: 100,
        now: Math.round(clamped * 100),
      }}
    >
      <View
        style={[styles.fill, { width: `${clamped * 100}%`, height }]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    width: '100%',
    backgroundColor: colors.border,
    borderRadius: borders.radius.full,
    overflow: 'hidden',
  },
  fill: {
    backgroundColor: colors.primary,
    borderRadius: borders.radius.full,
  },
});

export default memo(ProgressBar);
