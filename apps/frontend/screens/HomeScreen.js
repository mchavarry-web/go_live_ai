// 1:1 port of gln-mobile-app/src/screens/home/HomeScreen.tsx.
// Placeholder for the "Inicio" tab — a future "social feed where avatars
// interact with each other". The original ships this as a glow + icon +
// "Próximamente" + subtitle + accent divider + hint copy.
import React from 'react';
import { StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import Text from '../components/ui/Text';
import { colors, spacing } from '../theme';

export default function HomeScreen() {
  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.iconContainer}>
          <View style={styles.iconGlow} />
          <View style={styles.iconCircle}>
            <Ionicons name="people-circle" size={64} color={colors.primary} />
          </View>
        </View>

        <Text variant="heading" align="center" color={colors.textPrimary} style={styles.title}>
          Próximamente
        </Text>

        <Text
          variant="body"
          align="center"
          color={colors.textSecondary}
          style={styles.subtitle}
        >
          Red social para que otros avatares interactúen
        </Text>

        <View style={styles.divider} />

        <Text
          variant="caption"
          align="center"
          color={colors.textTertiary}
          style={styles.hint}
        >
          Estamos trabajando en algo increíble. Pronto vas a poder conectar tu
          avatar con los de otras personas y crear interacciones únicas.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: spacing.xl,
  },
  iconContainer: {
    position: 'relative',
    marginBottom: spacing.lg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconGlow: {
    position: 'absolute',
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: colors.primary,
    opacity: 0.08,
  },
  iconCircle: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: colors.elevated,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { marginBottom: spacing.sm },
  subtitle: {
    lineHeight: 24,
    maxWidth: 280,
    marginBottom: spacing.lg,
  },
  divider: {
    width: 40,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.primary,
    opacity: 0.4,
    marginBottom: spacing.lg,
  },
  hint: {
    lineHeight: 18,
    maxWidth: 300,
  },
});
