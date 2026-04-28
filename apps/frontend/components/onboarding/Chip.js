import React from 'react';
import { TouchableOpacity, StyleSheet } from 'react-native';
import { colors, spacing, borders } from '../../theme';
import { Text } from '../ui';

export default function Chip({ label, selected = false, onPress }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      activeOpacity={0.7}
      style={[styles.chip, selected && styles.chipSelected]}
    >
      <Text
        variant="label"
        color={selected ? 'textInverse' : 'textPrimary'}
      >
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  chip: {
    borderRadius: borders.radius.full,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    backgroundColor: colors.elevated,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  chipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
});
