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
import { colors, spacing, borders } from '../../theme';

const MODE_LABELS = {
  professional: 'Profesional',
  friends:      'Amigos',
  dating:       'Citas',
};

function AvatarHeader({
  avatarName = 'Avatar',
  avatar,
  isOnline = true,
  avatarState = 'idle',
  onBack,
  leftAction,
  rightActions,
  onModeChipPress,
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
  const modeLabel = MODE_LABELS[avatar?.active_mode] || null;

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

      {modeLabel ? (
        <Pressable
          onPress={onModeChipPress}
          style={styles.modeChip}
          hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          accessibilityRole="button"
          accessibilityLabel={`Modo activo: ${modeLabel}. Tocar para cambiar.`}
        >
          <Text variant="caption" color={colors.primary} style={styles.modeChipText}>
            {modeLabel}
          </Text>
        </Pressable>
      ) : null}

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
  modeChip: {
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: borders.radius.full,
    borderWidth: borders.width.thin,
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
  },
  modeChipText: { fontWeight: '600', fontSize: 11 },
});

export default memo(AvatarHeader);
