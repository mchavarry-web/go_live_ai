// Three-pill segmented control for the avatar's active behavior mode.
// Mounted right under the avatar header in Perfil so it's the most
// reachable control on the screen.
//
// Switching is seamless on the backend (no conversation forking, no
// migration) — the only side effects are the avatar's next reply tone
// and a UI indicator. ``pending`` gives the pill an immediate visual
// toggle while the PATCH is in flight; ``onChange`` only fires once
// the server has confirmed the new mode so callers that re-fetch
// (e.g. /auth/me) see the updated value.
import React, { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import Text from '../ui/Text';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';

const MODES = [
  { key: 'professional', label: 'Profesional', icon: 'briefcase-outline' },
  { key: 'friends',      label: 'Amigos',      icon: 'happy-outline' },
  { key: 'dating',       label: 'Citas',       icon: 'heart-outline' },
];

export default function ModeSwitcher({ activeMode, onChange }) {
  const [pending, setPending] = useState(null);

  const select = async (next) => {
    if (!next || next === activeMode || pending) return;
    // ``pending`` is the visual optimistic toggle. We do NOT fire onChange
    // until the PATCH succeeds — otherwise a caller that calls /auth/me
    // would race the in-flight write and read the previous mode.
    setPending(next);
    const res = await apiService.updateAvatar({ active_mode: next });
    setPending(null);
    if (res.success) {
      onChange?.(next);
    }
    // On failure: keep the existing activeMode. Pending was visual-only,
    // so clearing it returns the pill to the prior state without needing
    // to call onChange.
  };

  return (
    <View style={styles.row}>
      {MODES.map((m) => {
        const isActive = (pending || activeMode) === m.key;
        return (
          <Pressable
            key={m.key}
            style={[styles.pill, isActive && styles.pillActive]}
            onPress={() => select(m.key)}
            accessibilityLabel={m.label}
            accessibilityState={{ selected: isActive }}
          >
            <Ionicons
              name={m.icon}
              size={14}
              color={isActive ? colors.primary : colors.textSecondary}
            />
            <Text
              variant="caption"
              color={isActive ? colors.primary : colors.textSecondary}
              style={styles.pillLabel}
            >
              {m.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    gap: spacing.xs,
    width: '100%',
    marginTop: spacing.sm,
  },
  pill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.xs,
    borderRadius: borders.radius.full,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  pillActive: {
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.1)',
  },
  pillLabel: { fontWeight: '600' },
});
