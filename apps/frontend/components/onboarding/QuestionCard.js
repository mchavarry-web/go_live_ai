// 1:1 port of gln-mobile-app/src/components/onboarding/QuestionCard.tsx.
// Glass-card with a title, optional subtitle, and a children slot for
// the step's interactive controls (chips/sliders/inputs).
import React, { memo } from 'react';
import { StyleSheet, View } from 'react-native';

import Text from '../ui/Text';
import Card from '../ui/Card';
import { colors, spacing } from '../../theme';

function QuestionCard({ title, subtitle, children }) {
  return (
    <Card variant="glass" padding="lg" accessibilityLabel={title}>
      <View style={styles.content}>
        <Text variant="subheading" style={styles.title}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="body" color={colors.textSecondary} style={styles.subtitle}>
            {subtitle}
          </Text>
        ) : null}
        <View style={styles.children}>{children}</View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingVertical: spacing.xs,
  },
  title: {
    marginBottom: spacing.xxs,
  },
  subtitle: {
    marginBottom: spacing.md,
  },
  children: {
    marginTop: spacing.md,
  },
});

export default memo(QuestionCard);
