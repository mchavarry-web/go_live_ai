import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, borders } from '../../theme';
import Text from './Text';

export default function ErrorMessage({ message, style }) {
  if (!message) return null;
  return (
    <View style={[styles.wrap, style]}>
      <Ionicons name="alert-circle-outline" size={18} color={colors.error} />
      <Text variant="caption" color="error" style={styles.txt}>
        {message}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,71,87,0.08)',
    borderRadius: borders.radius.sm,
    borderWidth: borders.width.thin,
    borderColor: 'rgba(255,71,87,0.4)',
    padding: spacing.sm,
    gap: spacing.xs,
  },
  txt: { flex: 1 },
});
