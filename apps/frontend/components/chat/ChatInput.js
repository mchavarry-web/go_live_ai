// 1:1 port of gln-mobile-app/src/components/chat/ChatInput.tsx.
// Pill-shaped input with a circular send button (↑). Send button stays
// disabled (elevated fill) until there's trimmed text and !disabled, then
// it fills primary. The up-arrow glyph is faithful to the original — we
// don't substitute Ionicons here because the original uses a Text glyph.
import React, { memo, useCallback, useRef, useState } from 'react';
import {
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { colors, spacing, borders, typography } from '../../theme';
import Text from '../ui/Text';

function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Escribe un mensaje...',
}) {
  const [text, setText] = useState('');
  const inputRef = useRef(null);
  const canSend = text.trim().length > 0 && !disabled;

  const handleSend = useCallback(() => {
    if (!canSend) return;
    const message = text.trim();
    setText('');
    onSend(message);
    // Refocus so the user can keep typing without tapping the field again.
    inputRef.current?.focus();
  }, [canSend, text, onSend]);

  return (
    <View style={styles.container}>
      <View style={styles.inputRow}>
        <TextInput
          ref={inputRef}
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder={placeholder}
          placeholderTextColor={colors.textTertiary}
          multiline
          maxLength={10000}
          editable={!disabled}
          returnKeyType="default"
          blurOnSubmit={false}
          accessibilityLabel="Mensaje"
          accessibilityHint="Escribe un mensaje para tu avatar"
          selectionColor={colors.primary}
        />
        <Pressable
          onPress={handleSend}
          disabled={!canSend}
          style={({ pressed }) => [
            styles.sendButton,
            canSend && styles.sendButtonActive,
            pressed && canSend && styles.sendButtonPressed,
          ]}
          accessibilityRole="button"
          accessibilityLabel="Enviar mensaje"
          accessibilityState={{ disabled: !canSend }}
        >
          <Text
            variant="label"
            color={canSend ? colors.textInverse : colors.textTertiary}
            style={styles.sendIcon}
          >
            ↑
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.background,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    paddingBottom: Platform.OS === 'ios' ? spacing.md : spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    backgroundColor: colors.surface,
    borderRadius: borders.radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    paddingLeft: spacing.md,
    paddingRight: spacing.xxs,
    paddingVertical: Platform.OS === 'ios' ? spacing.xs : 0,
  },
  input: {
    flex: 1,
    fontSize: typography.sizes.md,
    color: colors.textPrimary,
    maxHeight: 120,
    paddingVertical: spacing.xs,
    lineHeight: 22,
  },
  sendButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.elevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
    marginLeft: spacing.xs,
  },
  sendButtonActive: {
    backgroundColor: colors.primary,
  },
  sendButtonPressed: {
    opacity: 0.8,
  },
  sendIcon: {
    fontSize: typography.sizes.lg,
    fontWeight: '700',
  },
});

export default memo(ChatInput);
