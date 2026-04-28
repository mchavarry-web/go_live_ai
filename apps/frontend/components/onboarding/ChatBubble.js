// 1:1 port of gln-mobile-app/src/components/onboarding/ChatBubble.tsx.
// Avatar messages slide in from the left, user messages from the right.
// When `showAvatar` is false (consecutive avatar messages), a width-matched
// placeholder keeps the bubbles aligned.
import React, { memo } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { FadeInLeft, FadeInRight } from 'react-native-reanimated';

import Text from '../ui/Text';
import AvatarFace from '../avatar/AvatarFace';
import { colors, spacing, borders } from '../../theme';

function ChatBubble({ text, sender, delay = 0, showAvatar = true }) {
  const isAvatar = sender === 'avatar';
  const entering = isAvatar
    ? FadeInLeft.duration(400).delay(delay).springify()
    : FadeInRight.duration(400).delay(delay).springify();

  return (
    <Animated.View
      entering={entering}
      style={[styles.row, isAvatar ? styles.rowLeft : styles.rowRight]}
    >
      {isAvatar && showAvatar && (
        <View style={styles.avatarContainer}>
          <AvatarFace size={28} state="idle" />
        </View>
      )}
      {isAvatar && !showAvatar && <View style={styles.avatarPlaceholder} />}

      <View style={[styles.bubble, isAvatar ? styles.bubbleAvatar : styles.bubbleUser]}>
        <Text
          variant="body"
          color={isAvatar ? colors.textPrimary : colors.textInverse}
          style={styles.text}
          selectable
        >
          {text}
        </Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    marginBottom: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  rowLeft: { justifyContent: 'flex-start' },
  rowRight: { justifyContent: 'flex-end' },
  avatarContainer: {
    marginRight: spacing.xs,
    alignSelf: 'flex-end',
    marginBottom: 2,
  },
  avatarPlaceholder: {
    width: 28,
    marginRight: spacing.xs,
  },
  bubble: {
    maxWidth: '78%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  bubbleAvatar: {
    backgroundColor: colors.elevated,
    borderRadius: borders.radius.lg,
    borderBottomLeftRadius: 4,
  },
  bubbleUser: {
    backgroundColor: colors.primary,
    borderRadius: borders.radius.lg,
    borderBottomRightRadius: 4,
  },
  text: { lineHeight: 22 },
});

export default memo(ChatBubble);
