// 1:1 port of gln-mobile-app/src/components/ui/Button.tsx.
// Three variants:
//   primary   — solid teal fill, dark text
//   secondary — transparent bg, teal border, teal text (this is the
//               *prominent* outlined button used on Welcome / forms)
//   ghost     — transparent, no border, primary text colour
//
// Accepts either a `title` string (original API) or `children` (convenience
// for callers that want JSX content). `accessibilityLabel` is honoured.
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet } from 'react-native';
import { colors, spacing, borders, typography } from '../../theme';
import Text from './Text';

const SIZE_STYLES = {
  sm: { paddingVertical: spacing.xs, paddingHorizontal: spacing.md, fontSize: typography.sizes.sm },
  md: { paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, fontSize: typography.sizes.md },
  lg: { paddingVertical: spacing.md, paddingHorizontal: spacing.xl, fontSize: typography.sizes.lg },
};

export default function Button({
  title,
  children,
  onPress,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  fullWidth = false,
  accessibilityLabel,
  style,
}) {
  const isDisabled = disabled || loading;
  const sizeStyle = SIZE_STYLES[size] || SIZE_STYLES.md;
  const label = title ?? children;

  // Three canonical variants from the original (primary / secondary / ghost),
  // plus `danger` (solid red — logout, destructive actions) and `outline`
  // (alias of secondary; kept so older callers don't break).
  const variantContainer = (() => {
    if (variant === 'primary')   return styles.primary;
    if (variant === 'secondary' || variant === 'outline') return styles.secondary;
    if (variant === 'ghost')     return styles.ghost;
    if (variant === 'danger')    return styles.danger;
    return styles.primary;
  })();

  const textColor = (() => {
    if (variant === 'primary' || variant === 'danger') return colors.textInverse;
    if (variant === 'secondary' || variant === 'outline') return colors.primary;
    if (variant === 'ghost') return colors.textPrimary;
    return colors.textInverse;
  })();

  const spinnerColor =
    variant === 'primary' || variant === 'danger' ? colors.textInverse : colors.primary;

  return (
    <Pressable
      onPress={isDisabled ? undefined : onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.base,
        variantContainer,
        {
          paddingVertical: sizeStyle.paddingVertical,
          paddingHorizontal: sizeStyle.paddingHorizontal,
          opacity: isDisabled ? 0.5 : pressed ? 0.8 : 1,
          width: fullWidth ? '100%' : undefined,
        },
        style,
      ]}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? (typeof label === 'string' ? label : undefined)}
      accessibilityState={{ disabled: isDisabled, busy: loading }}
    >
      {loading ? (
        <ActivityIndicator size="small" color={spinnerColor} style={styles.spinner} />
      ) : null}
      <Text
        variant="label"
        color={textColor}
        style={{ fontSize: sizeStyle.fontSize, fontWeight: typography.weights.semibold }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderRadius: borders.radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
  },
  primary: {
    backgroundColor: colors.primary,
  },
  secondary: {
    backgroundColor: 'transparent',
    borderWidth: borders.width.medium,
    borderColor: colors.primary,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  danger: {
    backgroundColor: colors.error,
  },
  spinner: { marginRight: spacing.xs },
});
