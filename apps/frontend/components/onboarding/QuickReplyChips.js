// 1:1 port of gln-mobile-app/src/components/onboarding/QuickReplyChips.tsx.
// Wrapping grid of pill chips. `singleSelect` mode is used by the
// onboarding flow when the next step should fire as soon as the user
// taps an option (age range, country) — the parent's onToggle decides.
import React, { memo } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';

import Text from '../ui/Text';
import { colors, spacing, borders } from '../../theme';

function QuickReplyChips({
  options,
  selected,
  onToggle,
  singleSelect = false,
  delay = 0,
}) {
  const handlePress = (option) => {
    onToggle(option);
  };

  return (
    <Animated.View
      entering={FadeInUp.duration(400).delay(delay).springify()}
      style={styles.container}
    >
      <View style={styles.grid}>
        {options.map((option) => {
          const isSelected = selected.includes(option);
          return (
            <Pressable
              key={option}
              onPress={() => handlePress(option)}
              style={({ pressed }) => [
                styles.chip,
                isSelected && styles.chipSelected,
                pressed && styles.chipPressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={option}
              accessibilityState={{ selected: isSelected }}
            >
              <Text
                variant="label"
                color={isSelected ? colors.textInverse : colors.textPrimary}
                style={styles.chipText}
              >
                {option}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  chip: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: borders.radius.xl,
    backgroundColor: colors.surface,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
  },
  chipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipPressed: { opacity: 0.7 },
  chipText: { textAlign: 'center' },
});

export default memo(QuickReplyChips);
