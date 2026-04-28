import React from 'react';
import { View, StyleSheet } from 'react-native';
import { colors, spacing, borders } from '../../theme';

export default function Card({
  variant = 'default',
  padding = 'md',
  style,
  children,
}) {
  const bg = variant === 'glass' ? colors.glassBg : colors.card;
  const pad = spacing[padding] ?? spacing.md;
  return (
    <View style={[styles.base, { backgroundColor: bg, padding: pad }, style]}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: borders.radius.lg,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
  },
});
