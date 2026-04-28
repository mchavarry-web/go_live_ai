// 1:1 port of gln-mobile-app/src/screens/settings/PrivacyScreen.tsx.
// Toggles for data sharing + management actions + danger zone (delete
// account). Backend routes for export/delete/privacy aren't exposed yet
// in Rails — we persist the toggles to AsyncStorage so the UI is
// functional, and the destructive actions log out the user with a clear
// "feature coming soon" Alert.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Linking,
  ScrollView,
  StyleSheet,
  Switch,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import { useAuth } from '../../contexts/AuthContext';

const STORAGE_KEY = 'privacy_settings_v1';
const DEFAULT_SETTINGS = {
  share_health_data:   false,
  share_social_data:   false,
  anonymous_analytics: true,
  allow_notifications: true,
};

function ToggleRow({ label, description, value, onValueChange, disabled }) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleTextContainer}>
        <Text
          variant="body"
          color={disabled ? colors.textTertiary : colors.textPrimary}
          style={styles.toggleLabel}
        >
          {label}
        </Text>
        {description && (
          <Text variant="caption" color={colors.textTertiary}>{description}</Text>
        )}
      </View>
      <Switch
        value={value}
        onValueChange={onValueChange}
        trackColor={{ false: colors.border, true: colors.primary }}
        thumbColor={value ? colors.primaryLight : colors.textSecondary}
        ios_backgroundColor={colors.border}
        accessibilityLabel={label}
        disabled={disabled}
      />
    </View>
  );
}

function RowDivider() {
  return <View style={styles.divider} />;
}

function ActionRow({ label, icon, onPress, color, isLoading }) {
  return (
    <TouchableOpacity
      style={styles.actionRow}
      onPress={onPress}
      disabled={isLoading}
      activeOpacity={0.7}
    >
      <View style={styles.actionRowLeft}>
        <Ionicons name={icon} size={20} color={color || colors.textSecondary} />
        <Text variant="body" color={color || colors.textPrimary} style={styles.actionLabel}>
          {label}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
    </TouchableOpacity>
  );
}

export default function PrivacyScreen() {
  const { logout } = useAuth();
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) setSettings({ ...DEFAULT_SETTINGS, ...JSON.parse(raw) });
    } catch {
      // Use defaults
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const updateSetting = useCallback(async (key, value) => {
    setSettings((prev) => {
      const next = { ...prev, [key]: value };
      AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  }, []);

  const handleExportData = useCallback(() => {
    Alert.alert(
      'Exportar mis datos',
      'La exportación de datos estará disponible próximamente. Mientras tanto, puedes solicitar tus datos por email a soporte@golive.app.',
    );
  }, []);

  const handleDeleteAccount = useCallback(() => {
    Alert.alert(
      'Eliminar cuenta',
      'Esta acción es IRREVERSIBLE. Se eliminarán permanentemente:\n\n' +
        '- Tu perfil y avatar\n' +
        '- Todas las conversaciones\n' +
        '- Conexiones sociales\n' +
        '- Todos tus datos\n\n' +
        '¿Estás seguro?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar permanentemente',
          style: 'destructive',
          onPress: async () => {
            Alert.alert(
              'En desarrollo',
              'La eliminación automática de cuentas estará disponible próximamente. Por ahora, escribinos a soporte@golive.app y vamos a procesar tu pedido en 24h.',
              [{ text: 'OK', onPress: () => logout() }],
            );
          },
        },
      ],
    );
  }, [logout]);

  const handlePrivacyPolicy = useCallback(() => {
    Linking.openURL('https://golive.devtechperu.net/privacy-policy').catch(() => {});
  }, []);

  if (loading) return <LoadingSpinner fullscreen />;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Text variant="heading" color={colors.textPrimary} style={styles.title}>
          Privacidad
        </Text>

        <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
          Datos compartidos con el avatar
        </Text>
        <Card variant="default" padding="sm">
          <ToggleRow
            label="Compartir datos de salud"
            description="Pasos, sueño y actividad física"
            value={settings.share_health_data}
            onValueChange={(val) => updateSetting('share_health_data', val)}
          />
          <RowDivider />
          <ToggleRow
            label="Compartir datos sociales"
            description="Intereses y likes de redes sociales"
            value={settings.share_social_data}
            onValueChange={(val) => updateSetting('share_social_data', val)}
          />
          <RowDivider />
          <ToggleRow
            label="Analytics anónimos"
            description="Ayuda a mejorar la app"
            value={settings.anonymous_analytics}
            onValueChange={(val) => updateSetting('anonymous_analytics', val)}
          />
          <RowDivider />
          <ToggleRow
            label="Notificaciones push"
            description="Recibir recordatorios del avatar"
            value={settings.allow_notifications}
            onValueChange={(val) => updateSetting('allow_notifications', val)}
          />
        </Card>

        <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
          Gestión de datos
        </Text>
        <Card variant="default" padding="sm">
          <ActionRow
            label="Exportar mis datos"
            icon="download-outline"
            onPress={handleExportData}
          />
          <RowDivider />
          <ActionRow
            label="Política de privacidad"
            icon="document-text-outline"
            onPress={handlePrivacyPolicy}
          />
        </Card>

        <Text variant="label" color={colors.error} style={styles.sectionTitle}>
          Zona de peligro
        </Text>
        <Card variant="default" padding="sm">
          <ActionRow
            label="Eliminar mi cuenta"
            icon="trash-outline"
            onPress={handleDeleteAccount}
            color={colors.error}
          />
        </Card>

        <View style={styles.noteContainer}>
          <Text variant="caption" color={colors.textTertiary} align="center">
            Tus datos están encriptados y seguros. Cumplimos con GDPR y
            regulaciones de privacidad. Puedes cambiar estas configuraciones
            o eliminar tus datos en cualquier momento.
          </Text>
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
  title: {
    marginTop: spacing.lg,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    minHeight: 56,
  },
  toggleTextContainer: {
    flex: 1,
    marginRight: spacing.sm,
  },
  toggleLabel: { marginBottom: 2 },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginHorizontal: spacing.xs,
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    minHeight: 52,
  },
  actionRowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  actionLabel: { marginLeft: spacing.sm },
  noteContainer: {
    marginTop: spacing.xl,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.xl,
  },
});
