// 1:1 port of gln-mobile-app/src/components/chat/MarkdownMessage.tsx.
// Switches text/code/link colors based on whether the bubble is the user's
// (primary fill, light text) or the assistant's (elevated fill, light text).
// Uses react-native-markdown-display which is the package the rest of the
// monorepo standardised on.
import React, { memo } from 'react';
import { Linking, Platform } from 'react-native';
import Markdown from 'react-native-markdown-display';

import { colors, spacing, typography } from '../../theme';

function MarkdownMessage({ content, isUser = false }) {
  const textColor = isUser ? colors.textInverse : colors.textPrimary;
  const linkColor = isUser ? colors.elevated : colors.primary;
  const codeBackground = isUser ? 'rgba(0,0,0,0.15)' : colors.surface;
  const blockquoteBorder = isUser ? 'rgba(0,0,0,0.3)' : colors.border;

  const markdownStyles = {
    body: {
      fontFamily: typography.fontFamilies.body,
      fontSize: typography.sizes.md,
      lineHeight: typography.lineHeights.md,
      color: textColor,
      margin: 0,
      padding: 0,
    },
    paragraph: {
      fontFamily: typography.fontFamilies.body,
      fontSize: typography.sizes.md,
      lineHeight: typography.lineHeights.md,
      color: textColor,
      marginTop: 0,
      marginBottom: spacing.xs,
    },
    heading1: {
      fontFamily: typography.fontFamilies.display,
      fontSize: typography.sizes.lg,
      lineHeight: typography.lineHeights.lg,
      fontWeight: typography.weights.bold,
      color: textColor,
      marginTop: spacing.xs,
      marginBottom: spacing.xxs,
    },
    heading2: {
      fontFamily: typography.fontFamilies.display,
      fontSize: typography.sizes.md,
      lineHeight: typography.lineHeights.md,
      fontWeight: typography.weights.semibold,
      color: textColor,
      marginTop: spacing.xs,
      marginBottom: spacing.xxs,
    },
    heading3: {
      fontFamily: typography.fontFamilies.display,
      fontSize: typography.sizes.sm,
      lineHeight: typography.lineHeights.sm,
      fontWeight: typography.weights.semibold,
      color: textColor,
      marginTop: spacing.xs,
      marginBottom: spacing.xxs,
    },
    strong: { fontWeight: typography.weights.bold, color: textColor },
    em: { fontStyle: 'italic', color: textColor },
    link: {
      color: linkColor,
      textDecorationLine: 'underline',
      fontWeight: typography.weights.medium,
    },
    blocklink: { color: linkColor },
    list_item: {
      fontFamily: typography.fontFamilies.body,
      fontSize: typography.sizes.md,
      lineHeight: typography.lineHeights.md,
      color: textColor,
      marginBottom: spacing.xxs,
    },
    bullet_list: { marginTop: 0, marginBottom: spacing.xxs },
    ordered_list: { marginTop: 0, marginBottom: spacing.xxs },
    bullet_list_icon: {
      color: isUser ? colors.textInverse : colors.primary,
      fontSize: typography.sizes.md,
      lineHeight: typography.lineHeights.md,
      marginRight: spacing.xxs,
    },
    ordered_list_icon: {
      color: isUser ? colors.textInverse : colors.primary,
      fontSize: typography.sizes.sm,
      fontWeight: typography.weights.semibold,
      lineHeight: typography.lineHeights.md,
      marginRight: spacing.xxs,
    },
    code_inline: {
      fontFamily: Platform.select({
        ios: 'Courier New',
        android: 'monospace',
        default: 'monospace',
      }),
      fontSize: typography.sizes.sm,
      color: isUser ? colors.textInverse : colors.primaryLight,
      backgroundColor: codeBackground,
      paddingHorizontal: 4,
      paddingVertical: 1,
      borderRadius: 4,
    },
    code_block: {
      fontFamily: Platform.select({
        ios: 'Courier New',
        android: 'monospace',
        default: 'monospace',
      }),
      fontSize: typography.sizes.sm,
      lineHeight: typography.lineHeights.sm,
      color: isUser ? colors.textInverse : colors.textPrimary,
      backgroundColor: codeBackground,
      padding: spacing.sm,
      borderRadius: 8,
      marginVertical: spacing.xxs,
    },
    fence: {
      fontFamily: Platform.select({
        ios: 'Courier New',
        android: 'monospace',
        default: 'monospace',
      }),
      fontSize: typography.sizes.sm,
      lineHeight: typography.lineHeights.sm,
      color: isUser ? colors.textInverse : colors.textPrimary,
      backgroundColor: codeBackground,
      padding: spacing.sm,
      borderRadius: 8,
      marginVertical: spacing.xxs,
    },
    blockquote: {
      borderLeftWidth: 3,
      borderLeftColor: blockquoteBorder,
      paddingLeft: spacing.sm,
      marginLeft: 0,
      marginVertical: spacing.xxs,
      opacity: 0.85,
    },
    hr: {
      backgroundColor: isUser ? 'rgba(0,0,0,0.2)' : colors.border,
      height: 1,
      marginVertical: spacing.xs,
    },
  };

  const handleLinkPress = (url) => {
    Linking.openURL(url).catch(() => {});
    return true;
  };

  return (
    <Markdown style={markdownStyles} onLinkPress={handleLinkPress} mergeStyle>
      {content}
    </Markdown>
  );
}

export default memo(MarkdownMessage);
