// 1:1 port of gln-mobile-app/src/screens/onboarding/AvatarCreatedScreen.tsx.
// Animated checkmark + heading + glass card with the avatar's name.
// The CTA refreshes the user via AuthContext, which flips
// onboarding_completed_at on the user object and makes RootNavigator
// switch from the onboarding stack to MainTabs.
import React, { useCallback } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { BounceIn, FadeInDown, FadeInUp } from 'react-native-reanimated';

import Text from '../../components/ui/Text';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';
import { useAuth } from '../../contexts/AuthContext';
import { colors, spacing, borders, typography } from '../../theme';

function CheckmarkIcon() {
  return (
    <View style={iconStyles.circle} accessibilityLabel="Éxito">
      <Text variant="heading" color={colors.textInverse} style={iconStyles.check}>
        ✓
      </Text>
    </View>
  );
}

const ICON_SIZE = 100;

const iconStyles = StyleSheet.create({
  circle: {
    width: ICON_SIZE,
    height: ICON_SIZE,
    borderRadius: ICON_SIZE / 2,
    backgroundColor: colors.primary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  check: {
    fontSize: typography.sizes.xxxl + 8,
    fontWeight: typography.weights.extrabold,
    lineHeight: typography.sizes.xxxl + 16,
    textAlign: 'center',
  },
});

export default function AvatarCreatedScreen() {
  const { user, refreshUserData } = useAuth();
  const avatarDisplayName = user?.avatar?.name || user?.first_name || 'Tu avatar';

  const handleStart = useCallback(async () => {
    // Refreshing the user marks onboarding_completed_at so RootNavigator
    // swaps to MainTabs on its next render.
    await refreshUserData();
  }, [refreshUserData]);

  return (
    <View style={styles.screen}>
      <View style={styles.content}>
        <Animated.View entering={BounceIn.duration(800).delay(200)} style={styles.iconWrapper}>
          <CheckmarkIcon />
        </Animated.View>

        <Animated.View entering={FadeInUp.duration(500).delay(600)}>
          <Text variant="heading" align="center" style={styles.heading}>
            ¡Tu avatar ha sido creado!
          </Text>
        </Animated.View>

        <Animated.View entering={FadeInUp.duration(500).delay(800)}>
          <Card variant="glass" padding="md" style={styles.nameCard}>
            <Text variant="subheading" color={colors.primary} align="center">
              {avatarDisplayName}
            </Text>
          </Card>
        </Animated.View>

        <Animated.View entering={FadeInUp.duration(500).delay(1000)}>
          <Text
            variant="body"
            color={colors.textSecondary}
            align="center"
            style={styles.subtitle}
          >
            Tu compañero digital está listo para conocerte
          </Text>
        </Animated.View>
      </View>

      <Animated.View entering={FadeInDown.duration(500).delay(1200)} style={styles.footer}>
        <Button
          title="Comenzar"
          onPress={handleStart}
          fullWidth
          size="lg"
          accessibilityLabel="Comenzar a usar la app"
        />
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
  },
  iconWrapper: { marginBottom: spacing.xl },
  heading: { marginBottom: spacing.md },
  nameCard: {
    marginBottom: spacing.lg,
    alignSelf: 'center',
    minWidth: 180,
    borderRadius: borders.radius.xl,
  },
  subtitle: { maxWidth: 280 },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
  },
});
