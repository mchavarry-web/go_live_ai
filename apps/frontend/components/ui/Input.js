// 1:1 port of gln-mobile-app/src/components/ui/Input.tsx.
import React, { forwardRef, useCallback, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { colors, spacing, borders, typography } from '../../theme';
import Text from './Text';

const Input = forwardRef(function Input(
  { label, error, leftIcon, rightIcon, containerStyle, style, onFocus, onBlur, ...rest },
  ref
) {
  const [isFocused, setIsFocused] = useState(false);

  const handleFocus = useCallback(
    (e) => {
      setIsFocused(true);
      onFocus?.(e);
    },
    [onFocus]
  );

  const handleBlur = useCallback(
    (e) => {
      setIsFocused(false);
      onBlur?.(e);
    },
    [onBlur]
  );

  return (
    <View style={[styles.container, containerStyle, style]}>
      {label ? (
        <Text variant="label" color={colors.textSecondary} style={styles.label}>
          {label}
        </Text>
      ) : null}

      <View
        style={[
          styles.inputContainer,
          isFocused && styles.inputContainerFocused,
          !!error && styles.inputContainerError,
        ]}
      >
        {leftIcon ? <View style={styles.iconLeft}>{leftIcon}</View> : null}

        <TextInput
          ref={ref}
          style={[
            styles.input,
            leftIcon ? styles.inputWithLeftIcon : null,
            rightIcon ? styles.inputWithRightIcon : null,
          ]}
          placeholderTextColor={colors.textTertiary}
          selectionColor={colors.primary}
          onFocus={handleFocus}
          onBlur={handleBlur}
          accessibilityLabel={label}
          {...rest}
        />

        {rightIcon ? <View style={styles.iconRight}>{rightIcon}</View> : null}
      </View>

      {error ? (
        <Text variant="caption" color={colors.error} style={styles.error}>
          {error}
        </Text>
      ) : null}
    </View>
  );
});

export default Input;

const styles = StyleSheet.create({
  container: { width: '100%' },
  label: { marginBottom: spacing.xxs },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: borders.radius.md,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    minHeight: 48,
  },
  inputContainerFocused: { borderColor: colors.primary },
  inputContainerError:   { borderColor: colors.error },
  input: {
    flex: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: typography.sizes.md,
    fontFamily: typography.fontFamilies.body,
    color: colors.textPrimary,
  },
  inputWithLeftIcon:  { paddingLeft: spacing.xs },
  inputWithRightIcon: { paddingRight: spacing.xs },
  iconLeft:  { paddingLeft: spacing.sm },
  iconRight: { paddingRight: spacing.sm },
  error: { marginTop: spacing.xxs },
});
