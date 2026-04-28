import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing } from '../../theme';
import Text from './Text';

export default function EmptyState({
  icon = 'sparkles-outline',
  title,
  message,
  action,
}) {
  return (
    <View style={styles.wrap}>
      <Ionicons name={icon} size={56} color={colors.textTertiary} style={styles.icon} />
      {title ? (
        <Text variant="title" color="textPrimary" align="center" style={styles.title}>
          {title}
        </Text>
      ) : null}
      {message ? (
        <Text variant="body" color="textSecondary" align="center" style={styles.message}>
          {message}
        </Text>
      ) : null}
      {action ? <View style={styles.action}>{action}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  icon: { marginBottom: spacing.md },
  title: { marginBottom: spacing.xs },
  message: { marginBottom: spacing.md },
  action: { marginTop: spacing.md },
});
