// 1:1 port of gln-mobile-app/src/components/chat/MessageBubble.tsx.
// Long-press copies the message; bubble briefly flashes a confirm color.
// User messages are right-aligned with primary fill; assistant messages
// are left-aligned with elevated fill. Both pass through MarkdownMessage.
import React, { memo, useCallback, useState } from 'react';
import { Pressable, StyleSheet, View, Clipboard } from 'react-native';

import { colors, spacing, borders } from '../../theme';
import MarkdownMessage from './MarkdownMessage';

function MessageBubble({ message }) {
  const isUser = message.role === 'user';
  const proactive = message.proactive_skill;
  const [copied, setCopied] = useState(false);

  const handleLongPress = useCallback(() => {
    Clipboard.setString(message.content || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [message.content]);

  return (
    <View
      style={[
        styles.container,
        isUser ? styles.userContainer : styles.assistantContainer,
      ]}
    >
      <Pressable
        onLongPress={handleLongPress}
        delayLongPress={400}
        style={({ pressed }) => [
          styles.bubble,
          isUser ? styles.userBubble : styles.assistantBubble,
          proactive && styles.bubbleProactive,
          pressed && styles.bubblePressed,
          copied && (isUser ? styles.bubbleCopiedUser : styles.bubbleCopiedAssistant),
        ]}
        accessibilityRole="text"
        accessibilityLabel={`${message.role}: ${message.content}`}
        accessibilityHint="Mantén presionado para copiar"
      >
        <MarkdownMessage content={message.content || ''} isUser={isUser} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xxs,
  },
  userContainer: { alignItems: 'flex-end' },
  assistantContainer: { alignItems: 'flex-start' },
  bubble: {
    maxWidth: '80%',
    padding: spacing.sm,
    borderRadius: borders.radius.lg,
  },
  bubblePressed: { opacity: 0.75 },
  userBubble: {
    backgroundColor: colors.primary,
    borderBottomRightRadius: borders.radius.sm,
  },
  assistantBubble: {
    backgroundColor: colors.elevated,
    borderBottomLeftRadius: borders.radius.sm,
  },
  bubbleProactive: {
    borderWidth: borders.width.thin,
    borderColor: colors.primary,
  },
  bubbleCopiedUser: { backgroundColor: colors.primaryLight },
  bubbleCopiedAssistant: { backgroundColor: colors.borderLight },
});

export default memo(MessageBubble);
