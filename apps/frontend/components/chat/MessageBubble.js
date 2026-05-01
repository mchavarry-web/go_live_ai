// 1:1 port of gln-mobile-app/src/components/chat/MessageBubble.tsx.
// Long-press copies the message; bubble briefly flashes a confirm color.
// User messages are right-aligned with primary fill; assistant messages
// are left-aligned with elevated fill. Both pass through MarkdownMessage.
//
// Tester mode (`isTester`): when the authenticated user has
// users.is_tester = true we render a small dot beside each bubble that
// opens TelemetryModal with the hop-by-hop roundtrip log. Hidden for
// regular users.
import React, { memo, useCallback, useState } from 'react';
import { Pressable, StyleSheet, View, Clipboard } from 'react-native';

import { colors, spacing, borders } from '../../theme';
import MarkdownMessage from './MarkdownMessage';
import TelemetryModal from './TelemetryModal';

function MessageBubble({ message, isTester = false }) {
  const isUser = message.role === 'user';
  const proactive = message.proactive_skill;
  const [copied, setCopied] = useState(false);
  const [telemetryOpen, setTelemetryOpen] = useState(false);

  const handleLongPress = useCallback(() => {
    Clipboard.setString(message.content || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [message.content]);

  // The dot is only meaningful when there's something to show. The user
  // message is stamped with client_sent_at + api_received_at; the
  // assistant message carries the full hop list. Either way, render the
  // dot if any telemetry exists.
  const telemetry = message?.metadata?.telemetry;
  const showDot = !!isTester && !!telemetry;

  return (
    <>
      <View
        style={[
          styles.container,
          isUser ? styles.userContainer : styles.assistantContainer,
        ]}
      >
        <View
          style={[
            styles.row,
            isUser ? styles.rowUser : styles.rowAssistant,
          ]}
        >
          {showDot && isUser ? (
            <Pressable
              onPress={() => setTelemetryOpen(true)}
              style={styles.dot}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              accessibilityLabel="Ver telemetría del mensaje"
            />
          ) : null}
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
          {showDot && !isUser ? (
            <Pressable
              onPress={() => setTelemetryOpen(true)}
              style={styles.dot}
              hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
              accessibilityLabel="Ver telemetría del mensaje"
            />
          ) : null}
        </View>
      </View>

      {showDot ? (
        <TelemetryModal
          visible={telemetryOpen}
          telemetry={telemetry}
          onClose={() => setTelemetryOpen(false)}
        />
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xxs,
  },
  userContainer: { alignItems: 'flex-end' },
  assistantContainer: { alignItems: 'flex-start' },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    maxWidth: '85%',
  },
  rowUser: { justifyContent: 'flex-end' },
  rowAssistant: { justifyContent: 'flex-start' },
  bubble: {
    flexShrink: 1,
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
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.primary,
  },
});

export default memo(MessageBubble);
