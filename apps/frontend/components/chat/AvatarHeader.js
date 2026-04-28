// 1:1 port of gln-mobile-app/src/components/chat/AvatarHeader.tsx, with two
// optional extras for the new app:
//   - back button (used when chat is reached from a non-drawer entry)
//   - rightActions slot (used to host the conversations menu / new chat)
// The original mobile app put those controls outside the header; we keep
// them here because the rest of the screen layout is simpler this way.
import React, { memo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import AvatarFace from '../avatar/AvatarFace';
import Text from '../ui/Text';
import { colors, spacing } from '../../theme';

function AvatarHeader({
  avatarName = 'Avatar',
  avatar,
  isOnline = true,
  avatarState = 'idle',
  onBack,
  leftAction,
  rightActions,
}) {
  const statusText =
    avatarState === 'thinking'
      ? 'Pensando...'
      : avatarState === 'talking'
        ? 'Escribiendo...'
        : isOnline
          ? 'En línea'
          : 'Desconectado';

  const appearance = avatar?.appearance || {};

  return (
    <View style={styles.container} accessibilityRole="header">
      {leftAction ? (
        <View style={styles.leftAction}>{leftAction}</View>
      ) : onBack ? (
        <Pressable
          onPress={onBack}
          style={styles.backButton}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          accessibilityRole="button"
          accessibilityLabel="Volver"
        >
          <Ionicons name="chevron-back" size={22} color={colors.textPrimary} />
        </Pressable>
      ) : null}

      <View style={styles.avatarWrapper}>
        <AvatarFace
          size={AVATAR_SIZE}
          state={avatarState}
          color={appearance.color}
          eyes={appearance.eyes}
          glow={appearance.glow}
        />
      </View>

      <View style={styles.textContainer}>
        <Text variant="label" color={colors.textPrimary}>
          {avatarName}
        </Text>
        <Text variant="caption" color={colors.textTertiary}>
          {statusText}
        </Text>
      </View>

      {rightActions ? <View style={styles.actions}>{rightActions}</View> : null}
    </View>
  );
}

const AVATAR_SIZE = 36;

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
    backgroundColor: colors.background,
  },
  leftAction: {},
  backButton: {
    padding: spacing.xxs,
  },
  avatarWrapper: {},
  textContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
});

export default memo(AvatarHeader);
