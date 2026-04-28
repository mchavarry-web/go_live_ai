// 1:1 port of gln-mobile-app/src/screens/settings/SettingsScreen.tsx.
// Card-style account/app/about/dev sections + a logout button at the
// bottom. The "Re-hacer Onboarding" entry hits /api/v1/onboarding/reset
// and refreshes the auth context so RootNavigator falls back into the
// onboarding flow naturally.
import React, { useCallback, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import { colors, spacing, borders } from '../../theme';
import { useAuth } from '../../contexts/AuthContext';
import apiService from '../../services/apiService';

const APP_VERSION = '1.0.0';

function SettingsRow({ label, value, onPress, showChevron = false }) {
  const content = (
    <View style={styles.settingsRow}>
      <Text variant="body" color={colors.textPrimary}>{label}</Text>
      <View style={styles.rowRight}>
        {value ? (
          <Text variant="body" color={colors.textSecondary}>{value}</Text>
        ) : null}
        {showChevron ? (
          <Text variant="body" color={colors.textTertiary} style={styles.chevron}>›</Text>
        ) : null}
      </View>
    </View>
  );

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [pressed && styles.rowPressed]}
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        {content}
      </Pressable>
    );
  }
  return content;
}

function SectionHeader({ title }) {
  return (
    <Text variant="label" color={colors.textSecondary} style={styles.sectionHeader}>
      {title}
    </Text>
  );
}

function RowDivider() {
  return <View style={styles.divider} />;
}

export default function SettingsScreen({ navigation }) {
  const { user, logout, refreshUserData } = useAuth();
  const [isResettingOnboarding, setIsResettingOnboarding] = useState(false);

  const displayName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') ||
    user?.email ||
    '—';

  const handleLogout = useCallback(() => {
    Alert.alert(
      'Cerrar sesión',
      '¿Estás seguro de que quieres cerrar sesión?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Cerrar sesión', style: 'destructive', onPress: () => logout() },
      ],
    );
  }, [logout]);

  const handlePrivacy = useCallback(() => {
    navigation.navigate('Privacy');
  }, [navigation]);

  const handleNotifications = useCallback(() => {
    Alert.alert(
      'Notificaciones',
      'La configuración de notificaciones estará disponible próximamente.',
    );
  }, []);

  const handleResetOnboarding = useCallback(() => {
    Alert.alert(
      'Re-hacer Onboarding',
      'Esto reseteará tu perfil y avatar. Tendrás que completar el onboarding de nuevo. ¿Continuar?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Resetear',
          style: 'destructive',
          onPress: async () => {
            setIsResettingOnboarding(true);
            const { success } = await apiService.resetOnboarding();
            if (success) {
              await refreshUserData();
            } else {
              Alert.alert('Error', 'No se pudo resetear el onboarding. Intentá de nuevo.');
            }
            setIsResettingOnboarding(false);
          },
        },
      ],
    );
  }, [refreshUserData]);

  const handleCreateNewUser = useCallback(() => {
    Alert.alert(
      'Crear nuevo usuario',
      'Esto cerrará tu sesión actual y podrás registrar una cuenta nueva. ¿Continuar?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Continuar', style: 'destructive', onPress: () => logout() },
      ],
    );
  }, [logout]);

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <SectionHeader title="Cuenta" />
        <Card variant="default" padding="sm">
          <SettingsRow label="Nombre" value={displayName} />
          <RowDivider />
          <SettingsRow label="Email" value={user?.email || '—'} />
        </Card>

        <SectionHeader title="Aplicación" />
        <Card variant="default" padding="sm">
          <SettingsRow label="Privacidad" onPress={handlePrivacy} showChevron />
          <RowDivider />
          <SettingsRow label="Notificaciones" onPress={handleNotifications} showChevron />
        </Card>

        <SectionHeader title="Acerca de" />
        <Card variant="default" padding="sm">
          <SettingsRow label="Versión" value={APP_VERSION} />
        </Card>

        <SectionHeader title="Desarrollo" />
        <Card variant="default" padding="sm">
          <SettingsRow
            label="Re-hacer Onboarding"
            onPress={isResettingOnboarding ? undefined : handleResetOnboarding}
            showChevron={!isResettingOnboarding}
            value={isResettingOnboarding ? 'Reseteando...' : undefined}
          />
          <RowDivider />
          <SettingsRow
            label="Crear nuevo usuario (test)"
            onPress={handleCreateNewUser}
            showChevron
          />
        </Card>

        <View style={styles.dangerZone}>
          <Button title="Cerrar sesión" onPress={handleLogout} variant="ghost" fullWidth />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollView: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xxl,
  },
  sectionHeader: {
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  settingsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    minHeight: 48,
  },
  rowRight: {
    flexDirection: 'row',
    alignItems: 'center',
    flexShrink: 1,
  },
  chevron: {
    fontSize: 22,
    marginLeft: spacing.xs,
  },
  rowPressed: {
    opacity: 0.6,
    borderRadius: borders.radius.sm,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginHorizontal: spacing.xs,
  },
  dangerZone: {
    marginTop: spacing.xl,
    alignItems: 'center',
  },
});
