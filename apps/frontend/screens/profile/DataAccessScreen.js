// 1:1 port of gln-mobile-app/src/screens/profile/DataAccessScreen.tsx,
// adapted to our Rails endpoints. Sections:
//   - Datos de Conversación (totals + first/last)
//   - Memorias del Avatar (insights by category)
//   - Datos de Redes Sociales (per-provider status)
//   - Conexión por proveedor (Spotify OAuth deep link, Instagram/Facebook
//     guides come later)
//   - Controles de privacidad (3 toggles, AsyncStorage-backed)
//   - Nota informativa
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
import * as WebBrowser from 'expo-web-browser';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useFocusEffect } from '@react-navigation/native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';

const PROVIDERS = [
  { id: 'instagram', name: 'Instagram', icon: 'logo-instagram', color: '#E4405F' },
  { id: 'facebook',  name: 'Facebook',  icon: 'logo-facebook',  color: '#1877F2' },
  { id: 'twitter',   name: 'Twitter/X', icon: 'logo-twitter',   color: '#1DA1F2' },
  { id: 'spotify',   name: 'Spotify',   icon: 'musical-notes',  color: '#1DB954' },
];

const CATEGORY_LABELS = {
  personal_history: 'Historia Personal',
  preference: 'Preferencias',
  relationship: 'Relaciones',
  goal: 'Metas',
  emotion: 'Emociones',
  health: 'Salud',
};

const PRIVACY_KEY = 'privacy_settings_v1';
const DEFAULT_PRIVACY = {
  share_health_data:   false,
  share_social_data:   false,
  anonymous_analytics: true,
};

function formatDate(dateStr) {
  if (!dateStr) return '—';
  const date = new Date(dateStr);
  return date.toLocaleDateString('es-ES', {
    day: 'numeric', month: 'short', year: 'numeric',
  });
}

// Relative "hace X" phrasing for sync timestamps; falls back to the
// absolute date after a week, and to "nunca" when there is no timestamp.
function formatRelative(dateStr) {
  if (!dateStr) return 'nunca';
  const diffMs = Date.now() - new Date(dateStr).getTime();
  if (Number.isNaN(diffMs)) return 'nunca';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'hace un momento';
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return days === 1 ? 'hace 1 día' : `hace ${days} días`;
  return formatDate(dateStr);
}

function DataRow({ label, value, icon }) {
  return (
    <View style={styles.dataRow}>
      <View style={styles.dataRowLeft}>
        {icon && (
          <Ionicons name={icon} size={16} color={colors.textTertiary} style={styles.dataRowIcon} />
        )}
        <Text variant="caption" color={colors.textTertiary}>{label}</Text>
      </View>
      <Text variant="body" color={colors.textPrimary}>{value}</Text>
    </View>
  );
}

function ToggleRow({ label, value, onChange, subtitle }) {
  return (
    <View style={styles.toggleRow}>
      <View style={styles.toggleTextContainer}>
        <Text variant="body" color={colors.textPrimary}>{label}</Text>
        {subtitle && <Text variant="caption" color={colors.textTertiary}>{subtitle}</Text>}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.border, true: colors.primary }}
        thumbColor={colors.textPrimary}
      />
    </View>
  );
}

export default function DataAccessScreen({ route }) {
  const initialProvider = route?.params?.provider;
  const [stats, setStats] = useState({
    conversations: { total: 0, total_messages: 0, first: null, last: null },
    insights_by_category: {},
    total_insights: 0,
  });
  const [statuses, setStatuses] = useState({});
  const [loading, setLoading] = useState(true);
  const [privacy, setPrivacy] = useState(DEFAULT_PRIVACY);
  const [busyProvider, setBusyProvider] = useState(null);

  const loadAll = useCallback(async () => {
    const [insightsRes, conversationsRes, ...statusesRes] = await Promise.all([
      apiService.listInsights(),
      apiService.listConversations(),
      ...PROVIDERS.map((p) => apiService.socialStatus(p.id)),
    ]);

    // Insights aggregate
    const insights = insightsRes.success ? (insightsRes.data?.insights || insightsRes.data || []) : [];
    const insightsByCategory = {};
    insights.forEach((i) => {
      const c = i.category || 'preference';
      insightsByCategory[c] = (insightsByCategory[c] || 0) + 1;
    });

    // Conversations aggregate
    const convs = conversationsRes.success
      ? (conversationsRes.data?.conversations || conversationsRes.data || [])
      : [];
    let totalMessages = 0;
    let first = null;
    let last = null;
    convs.forEach((c) => {
      totalMessages += c.messages_count || 0;
      const created = c.created_at;
      const active = c.last_active_at || c.updated_at;
      if (!first || (created && new Date(created) < new Date(first))) first = created;
      if (!last || (active && new Date(active) > new Date(last))) last = active;
    });

    // Per-provider statuses
    const next = {};
    PROVIDERS.forEach((p, i) => {
      const r = statusesRes[i];
      next[p.id] = r?.success ? r.data : { connected: false };
    });

    setStats({
      conversations: {
        total: convs.length,
        total_messages: totalMessages,
        first,
        last,
      },
      insights_by_category: insightsByCategory,
      total_insights: insights.length,
    });
    setStatuses(next);

    const raw = await AsyncStorage.getItem(PRIVACY_KEY);
    if (raw) {
      try {
        setPrivacy({ ...DEFAULT_PRIVACY, ...JSON.parse(raw) });
      } catch {}
    }

    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { loadAll(); }, [loadAll]));

  const handlePrivacyToggle = (key, value) => {
    setPrivacy((prev) => {
      const next = { ...prev, [key]: value };
      AsyncStorage.setItem(PRIVACY_KEY, JSON.stringify(next)).catch(() => {});
      return next;
    });
  };

  const handleDisconnect = (providerId) => {
    Alert.alert(
      'Desconectar',
      `Se eliminarán los datos importados desde ${providerId}. ¿Continuar?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Desconectar',
          style: 'destructive',
          onPress: async () => {
            setBusyProvider(providerId);
            const { success } = await apiService.disconnectSocial(providerId);
            setBusyProvider(null);
            if (success) {
              loadAll();
            } else {
              Alert.alert('Error', 'No se pudo desconectar.');
            }
          },
        },
      ],
    );
  };

  const handleConnect = async (providerId) => {
    if (providerId === 'spotify') {
      setBusyProvider('spotify');
      const { success, data } = await apiService.spotifyAuthUrl();
      setBusyProvider(null);
      if (success && data?.url) {
        await WebBrowser.openAuthSessionAsync(data.url, undefined);
        loadAll();
      } else {
        Alert.alert('Error', 'No se pudo iniciar la conexión de Spotify.');
      }
      return;
    }
    Alert.alert(
      'Conexión manual',
      `Para conectar ${providerId}, seguí la guía de configuración. Próximamente desde la app.`,
    );
  };

  if (loading) return <LoadingSpinner fullscreen message="Cargando datos..." />;

  const totalCategoryInsights = Object.values(stats.insights_by_category).reduce(
    (a, b) => a + b,
    0,
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Datos de Conversación */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Datos de Conversación
          </Text>
          <Card variant="glass" padding="md">
            <DataRow
              label="Total de conversaciones"
              value={String(stats.conversations.total)}
              icon="chatbubbles-outline"
            />
            <View style={styles.divider} />
            <DataRow
              label="Total de mensajes"
              value={String(stats.conversations.total_messages)}
              icon="chatbox-outline"
            />
            <View style={styles.divider} />
            <DataRow
              label="Primera conversación"
              value={formatDate(stats.conversations.first)}
              icon="calendar-outline"
            />
            <View style={styles.divider} />
            <DataRow
              label="Última actividad"
              value={formatDate(stats.conversations.last)}
              icon="time-outline"
            />
          </Card>
        </View>

        {/* Memorias por Categoría */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Memorias del Avatar ({stats.total_insights} total)
          </Text>
          <Card variant="glass" padding="md">
            {Object.entries(stats.insights_by_category).length > 0 ? (
              Object.entries(stats.insights_by_category).map(([category, count], index) => (
                <View key={category}>
                  {index > 0 && <View style={styles.divider} />}
                  <View style={styles.categoryRow}>
                    <Text variant="body" color={colors.textPrimary}>
                      {CATEGORY_LABELS[category] || category}
                    </Text>
                    <View style={styles.categoryCountContainer}>
                      <View style={styles.miniBar}>
                        <View
                          style={[
                            styles.miniBarFill,
                            {
                              width: `${
                                totalCategoryInsights > 0
                                  ? (count / totalCategoryInsights) * 100
                                  : 0
                              }%`,
                            },
                          ]}
                        />
                      </View>
                      <Text variant="caption" color={colors.textTertiary}>{count}</Text>
                    </View>
                  </View>
                </View>
              ))
            ) : (
              <Text variant="body" color={colors.textTertiary}>
                Tu avatar aún no tiene memorias.
              </Text>
            )}
          </Card>
        </View>

        {/* Redes Sociales */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Datos de Redes Sociales
          </Text>
          <Card variant="glass" padding="md">
            {PROVIDERS.map((p, idx) => {
              const s = statuses[p.id] || {};
              const connected = !!s.connected;
              const isStale = !!(s.stale || s.metadata?.stale);
              const isBusy = busyProvider === p.id;
              return (
                <View key={p.id}>
                  {idx > 0 && <View style={styles.divider} />}
                  <View style={styles.socialRow}>
                    <View style={styles.socialRowLeft}>
                      <Ionicons name={p.icon} size={20} color={p.color} />
                      <View style={styles.socialInfo}>
                        <Text variant="body" color={colors.textPrimary}>{p.name}</Text>
                        {connected ? (
                          <>
                            <Text variant="caption" color={colors.success}>
                              Conectado
                            </Text>
                            <Text variant="caption" color={colors.textTertiary}>
                              {`${s.ingested_items_count ?? 0} elementos importados`}
                            </Text>
                            <Text variant="caption" color={colors.textTertiary}>
                              {`Última sincronización: ${formatRelative(s.last_ingested_at)}`}
                            </Text>
                            {s.insights_count != null && (
                              <Text variant="caption" color={colors.textTertiary}>
                                {`${s.insights_count} datos aprendidos`}
                              </Text>
                            )}
                            {isStale && (
                              <Text variant="caption" color={colors.warning}>
                                Vuelve a conectar tu cuenta
                              </Text>
                            )}
                          </>
                        ) : (
                          <Text variant="caption" color={colors.textTertiary}>
                            No conectado
                          </Text>
                        )}
                      </View>
                    </View>
                    {connected ? (
                      <TouchableOpacity
                        onPress={() => handleDisconnect(p.id)}
                        disabled={isBusy}
                        style={styles.disconnectBtn}
                      >
                        <Text variant="caption" color={colors.error}>
                          {isBusy ? 'Desconectando…' : 'Desconectar'}
                        </Text>
                      </TouchableOpacity>
                    ) : (
                      <TouchableOpacity
                        onPress={() => handleConnect(p.id)}
                        disabled={isBusy}
                        style={styles.connectBtn}
                      >
                        <Text variant="caption" color={colors.primary}>
                          {isBusy ? 'Conectando…' : 'Conectar'}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              );
            })}
          </Card>
        </View>

        {/* Controles de privacidad */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Control de Acceso a Datos
          </Text>
          <Card variant="glass" padding="md">
            <ToggleRow
              label="Compartir datos sociales"
              subtitle="Permite al avatar usar datos de redes sociales"
              value={privacy.share_social_data}
              onChange={(val) => handlePrivacyToggle('share_social_data', val)}
            />
            <View style={styles.divider} />
            <ToggleRow
              label="Compartir datos de salud"
              subtitle="Permite al avatar usar métricas de salud"
              value={privacy.share_health_data}
              onChange={(val) => handlePrivacyToggle('share_health_data', val)}
            />
            <View style={styles.divider} />
            <ToggleRow
              label="Analítica anónima"
              subtitle="Ayuda a mejorar la experiencia general"
              value={privacy.anonymous_analytics}
              onChange={(val) => handlePrivacyToggle('anonymous_analytics', val)}
            />
          </Card>
        </View>

        <View style={styles.section}>
          <View style={styles.infoBox}>
            <Ionicons name="information-circle" size={20} color={colors.secondary} />
            <Text variant="caption" color={colors.textSecondary} style={styles.infoText}>
              Tu avatar usa estos datos para personalizar las conversaciones. Puedes
              desactivar el acceso en cualquier momento. Los datos se pueden exportar
              o eliminar desde Ajustes &gt; Privacidad.
            </Text>
          </View>
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
  section: { marginTop: spacing.lg },
  sectionTitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.xs,
  },
  dataRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xxs,
  },
  dataRowLeft: { flexDirection: 'row', alignItems: 'center' },
  dataRowIcon: { marginRight: 6 },
  categoryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xxs,
  },
  categoryCountContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  miniBar: {
    width: 60,
    height: 4,
    backgroundColor: colors.border,
    borderRadius: 2,
    overflow: 'hidden',
  },
  miniBarFill: {
    height: 4,
    backgroundColor: colors.primary,
    borderRadius: 2,
  },
  socialRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  socialRowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: spacing.sm,
  },
  socialInfo: { flex: 1 },
  disconnectBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.error,
  },
  connectBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.primary,
  },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  toggleTextContainer: {
    flex: 1,
    marginRight: spacing.sm,
  },
  infoBox: {
    flexDirection: 'row',
    backgroundColor: colors.elevated,
    borderRadius: borders.radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  infoText: { flex: 1 },
});
