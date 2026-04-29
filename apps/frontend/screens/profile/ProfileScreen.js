// 1:1 port of the *Perfil* tab as it ships in the latest gln-mobile-app
// build (see screenshots in this PR). The OG layout is simpler than
// ProfileHub.tsx — no AvatarFace orb at the top, no "Mi Huella Digital"
// data-source breakdown, no recent-insight tag chips. Just:
//
//   - "Avatar de {firstName}" caption + KnowledgeBar
//   - Personalidad card with full-width progress-bar sliders + Valores
//   - Lo que tu avatar sabe de ti — categories list with counts
//   - Redes sociales — per-provider status row (kept from the port)
//   - Configuración menu — Avatar Customize, Memorias, Data Access,
//     Behavior, Stats, Teach (kept from the port; the OG has equivalents
//     scattered across other tabs)
//   - Cerrar sesión button
//
// Backend wiring stays the same as before:
//   - user.avatar  (from AuthContext)              avatar.behavior, knowledge_level
//   - listInsights → derive insightsByCategory      counts per category
//   - per-provider socialStatus                     connection state
import React, { useCallback, useState } from 'react';
import {
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import AvatarFace from '../../components/avatar/AvatarFace';
import ModeSwitcher from '../../components/avatar/ModeSwitcher';
import { colors, spacing, borders, typography } from '../../theme';
import { useAuth } from '../../contexts/AuthContext';
import apiService from '../../services/apiService';

const CATEGORY_CONFIG = {
  personal_history: { icon: 'person',  label: 'Historia personal' },
  preference:       { icon: 'heart',   label: 'Preferencias' },
  relationship:     { icon: 'people',  label: 'Relaciones' },
  goal:             { icon: 'flag',    label: 'Metas' },
  emotion:          { icon: 'happy',   label: 'Emociones' },
  health:           { icon: 'fitness', label: 'Salud' },
};

// Origins of an insight — Mi Huella Digital groups insights by source so the
// user can see how much each data stream contributes to the avatar's
// knowledge. Unknown sources fall through to a neutral icon + raw key.
//
// Audio insights use namespaced sources like ``audio:<session_id>`` so we
// can wipe a single session's contribution without scanning content. The
// lookup below falls through to the prefix (the part before ":") so all
// audio sessions roll up under one entry in the grid.
const SOURCE_CONFIG = {
  conversation: { icon: 'chatbubble',     label: 'Conversaciones', color: '#A78BFA' },
  twitter:      { icon: 'logo-twitter',   label: 'Twitter/X',      color: '#1DA1F2' },
  instagram:    { icon: 'logo-instagram', label: 'Instagram',      color: '#E4405F' },
  facebook:     { icon: 'logo-facebook',  label: 'Facebook',       color: '#1877F2' },
  spotify:      { icon: 'musical-notes',  label: 'Spotify',        color: '#1DB954' },
  manual:       { icon: 'create',         label: 'Manual',         color: '#34D399' },
  onboarding:   { icon: 'rocket',         label: 'Onboarding',     color: '#FFB800' },
  audio:        { icon: 'mic',            label: 'Audio',          color: '#FF6B9D' },
};

function resolveSourceConfig(source) {
  if (SOURCE_CONFIG[source]) return SOURCE_CONFIG[source];
  // Allow ``namespace:detail`` keys (e.g. ``audio:abc-123``) to resolve to
  // their prefix entry without inflating the table for every variant.
  const prefix = typeof source === 'string' ? source.split(':')[0] : null;
  if (prefix && SOURCE_CONFIG[prefix]) return SOURCE_CONFIG[prefix];
  return null;
}

function sourceBucketKey(source) {
  if (typeof source !== 'string') return source;
  const prefix = source.split(':')[0];
  // If the prefix has its own row, group everything under it; otherwise
  // keep the original key (preserves backwards-compat for plain sources).
  return SOURCE_CONFIG[prefix] ? prefix : source;
}

const PROVIDERS = [
  { id: 'instagram', label: 'Instagram', icon: 'logo-instagram', color: colors.instagram },
  { id: 'facebook',  label: 'Facebook',  icon: 'logo-facebook',  color: colors.facebook },
  { id: 'twitter',   label: 'Twitter',   icon: 'logo-twitter',   color: colors.twitter },
  { id: 'spotify',   label: 'Spotify',   icon: 'musical-notes',  color: colors.spotify },
];

function getKnowledgeLevelLabel(level) {
  if (level <= 2) return 'Principiante';
  if (level <= 4) return 'Aprendiz';
  if (level <= 6) return 'Intermedio';
  if (level <= 8) return 'Avanzado';
  return 'Experto';
}

function getPersonalityLabel(value, lowLabel, highLabel) {
  if (value < 0.3) return `Muy ${lowLabel}`;
  if (value < 0.5) return `Algo ${lowLabel}`;
  if (value > 0.7) return `Muy ${highLabel}`;
  if (value > 0.5) return `Algo ${highLabel}`;
  return 'Equilibrado';
}

function MenuItem({ icon, label, subtitle, onPress, badge, accentColor = colors.primary }) {
  return (
    <TouchableOpacity
      style={styles.menuItem}
      onPress={onPress}
      activeOpacity={0.7}
      accessibilityLabel={label}
    >
      <View style={[styles.menuIconContainer, { backgroundColor: `${accentColor}15` }]}>
        <Ionicons name={icon} size={22} color={accentColor} />
      </View>
      <View style={styles.menuTextContainer}>
        <Text variant="body" color={colors.textPrimary}>{label}</Text>
        <Text variant="caption" color={colors.textTertiary}>{subtitle}</Text>
      </View>
      <View style={styles.menuRight}>
        {typeof badge === 'number' && badge > 0 && (
          <View style={styles.badge}>
            <Text variant="caption" color={colors.textInverse} style={styles.badgeText}>
              {badge > 99 ? '99+' : String(badge)}
            </Text>
          </View>
        )}
        <Ionicons name="chevron-forward" size={18} color={colors.textTertiary} />
      </View>
    </TouchableOpacity>
  );
}

function KnowledgeBar({ level }) {
  const maxLevel = 10;
  const progress = Math.min(level / maxLevel, 1);
  const label = getKnowledgeLevelLabel(level);
  return (
    <View style={styles.knowledgeBar}>
      <View style={styles.knowledgeHeader}>
        <View style={styles.knowledgeLabelRow}>
          <Ionicons name="flash" size={14} color={colors.primary} />
          <Text variant="caption" color={colors.primary} style={styles.knowledgeLabelText}>
            {label}
          </Text>
        </View>
        <Text variant="caption" color={colors.textTertiary}>
          Nivel {level}/{maxLevel}
        </Text>
      </View>
      <View style={styles.knowledgeTrack}>
        <View style={[styles.knowledgeFill, { width: `${progress * 100}%` }]} />
      </View>
    </View>
  );
}

// Full-width track with a colored fill and a circular indicator on top.
// Replaces the OG's "single dot on track" so the slider is more readable
// at a glance, matching the latest mobile build.
function PersonalityProgressBar({ leftLabel, rightLabel, value }) {
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <View style={styles.personalityContainer}>
      <View style={styles.personalityLabels}>
        <Text variant="caption" color={colors.textSecondary}>{leftLabel}</Text>
        <Text variant="caption" color={colors.textSecondary}>{rightLabel}</Text>
      </View>
      <View style={styles.personalityTrack}>
        <View style={[styles.personalityFill, { width: `${clamped * 100}%` }]} />
        <View style={[styles.personalityIndicator, { left: `${clamped * 100}%` }]} />
      </View>
      <Text
        variant="caption"
        color={colors.primary}
        align="center"
        style={styles.personalitySummary}
      >
        {getPersonalityLabel(clamped, leftLabel.toLowerCase(), rightLabel.toLowerCase())}
      </Text>
    </View>
  );
}

export default function ProfileScreen({ navigation }) {
  const { user, logout, refreshUserData } = useAuth();
  const [insights, setInsights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [statuses, setStatuses] = useState({});

  const fetchAll = useCallback(async () => {
    const [insightsRes, ...statusesRes] = await Promise.all([
      apiService.listInsights(),
      ...PROVIDERS.map((p) => apiService.socialStatus(p.id)),
    ]);
    setInsights(insightsRes.success ? (insightsRes.data?.insights || insightsRes.data || []) : []);
    const next = {};
    PROVIDERS.forEach((p, i) => {
      const r = statusesRes[i];
      next[p.id] = r?.success ? r.data : { connected: false };
    });
    setStatuses(next);
    setLoading(false);
    setRefreshing(false);
  }, []);

  useFocusEffect(useCallback(() => {
    refreshUserData();
    fetchAll();
  }, [fetchAll]));

  const onRefresh = () => {
    setRefreshing(true);
    refreshUserData();
    fetchAll();
  };

  const handleLogout = () => {
    Alert.alert('Cerrar sesión', '¿Estás seguro de que quieres cerrar sesión?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Cerrar sesión', style: 'destructive', onPress: () => logout() },
    ]);
  };

  if (loading) return <LoadingSpinner fullscreen message="Cargando perfil..." />;

  const avatar = user?.avatar;
  const knowledgeLevel = avatar?.knowledge_level ?? 1;
  const avatarName = avatar?.name || 'Tu avatar';
  const appearance = avatar?.appearance || {};
  const behavior = avatar?.behavior || {};
  const introvertExtrovert = behavior.introvert_extrovert ?? null;
  const rationalEmotional = behavior.rational_emotional ?? null;
  const valuesList = behavior.values || [];

  // Aggregate insights → category counts (the OG's "Lo que tu avatar sabe
  // de ti" breakdown). We don't render the raw chips here; the user can
  // open MemoryManager for the full list.
  const insightsByCategory = {};
  const insightsBySource = {};
  insights.forEach((it) => {
    const cat = it.category || 'preference';
    insightsByCategory[cat] = (insightsByCategory[cat] || 0) + 1;
    const src = sourceBucketKey(it.source || 'conversation');
    insightsBySource[src] = (insightsBySource[src] || 0) + 1;
  });
  const totalInsights = insights.length;
  const hasPersonality = introvertExtrovert !== null || rationalEmotional !== null;
  const hasValues = valuesList.length > 0;
  const hasCategories = Object.keys(insightsByCategory).length > 0;
  const hasSources = Object.keys(insightsBySource).length > 0;
  const ownerName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') || user?.email;

  return (
    <View style={styles.safeArea}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.primary}
          />
        }
      >
        {/* Avatar header — orb + name + owner caption + knowledge bar.
            No in-screen "Perfil" heading: the native nav bar already shows
            it (set in ProfileStack), and the OG doesn't double up. */}
        <View style={styles.avatarSection}>
          <View style={styles.avatarFaceWrapper}>
            <AvatarFace
              size={100}
              state="idle"
              color={appearance.color}
              eyes={appearance.eyes}
              glow={appearance.glow ?? 'high'}
            />
          </View>
          <Text variant="heading" color={colors.textPrimary} align="center" style={styles.avatarNameText}>
            {avatarName}
          </Text>
          <Text variant="body" color={colors.textSecondary} align="center">
            Avatar de {ownerName}
          </Text>
          <KnowledgeBar level={knowledgeLevel} />
          <ModeSwitcher
            activeMode={avatar?.active_mode || 'friends'}
            onChange={() => refreshUserData()}
          />
        </View>

        {/* Mi Huella Digital — insights grouped by source */}
        {hasSources && (
          <View style={styles.section}>
            <View style={styles.huellaHeader}>
              <Text variant="label" color={colors.textSecondary}>
                Mi Huella Digital
              </Text>
              <Text variant="caption" color={colors.primary}>
                {totalInsights} insights
              </Text>
            </View>
            <Card variant="glass" padding="md">
              {Object.entries(insightsBySource).map(([source, count]) => {
                const config = resolveSourceConfig(source) || {
                  icon: 'ellipse',
                  label: source,
                  color: colors.textSecondary,
                };
                const percentage = totalInsights > 0
                  ? Math.round((count / totalInsights) * 100)
                  : 0;
                // Tapping a source row drills into the surface that
                // owns that data. Audio → AudioHistory; everything else
                // currently routes to MemoryManager which lists the
                // raw insights (filterable by category there).
                const target = source === 'audio' ? 'AudioHistory' : 'MemoryManager';
                return (
                  <TouchableOpacity
                    key={source}
                    style={styles.sourceRow}
                    onPress={() => navigation.navigate(target)}
                    activeOpacity={0.7}
                  >
                    <View
                      style={[
                        styles.sourceIconBg,
                        { backgroundColor: `${config.color}20` },
                      ]}
                    >
                      <Ionicons name={config.icon} size={18} color={config.color} />
                    </View>
                    <View style={styles.sourceInfo}>
                      <Text variant="caption" color={colors.textPrimary}>
                        {config.label}
                      </Text>
                      <Text variant="caption" color={colors.textTertiary}>
                        {count} insights · {percentage}%
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={14} color={colors.textTertiary} />
                  </TouchableOpacity>
                );
              })}
            </Card>
          </View>
        )}

        {/* Personalidad — tap card to edit onboarding answers */}
        <View style={styles.section}>
          <View style={styles.personalityHeader}>
            <Text variant="label" color={colors.textSecondary}>
              Personalidad
            </Text>
            <TouchableOpacity
              onPress={() => navigation.navigate('EditPersonality')}
              activeOpacity={0.7}
              accessibilityLabel="Editar personalidad"
              hitSlop={8}
            >
              <Text variant="caption" color={colors.primary}>Editar</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            activeOpacity={0.85}
            onPress={() => navigation.navigate('EditPersonality')}
          >
            <Card variant="glass" padding="md">
              {hasPersonality || hasValues ? (
                <>
                  {introvertExtrovert !== null && (
                    <PersonalityProgressBar
                      leftLabel="Introvertido"
                      rightLabel="Extrovertido"
                      value={introvertExtrovert}
                    />
                  )}
                  {rationalEmotional !== null && (
                    <>
                      {introvertExtrovert !== null && <View style={styles.personalitySpacer} />}
                      <PersonalityProgressBar
                        leftLabel="Racional"
                        rightLabel="Emocional"
                        value={rationalEmotional}
                      />
                    </>
                  )}
                  {hasValues && (
                    <>
                      <View style={styles.divider} />
                      <Text
                        variant="caption"
                        color={colors.textTertiary}
                        style={styles.valuesLabel}
                      >
                        Valores
                      </Text>
                      <View style={styles.valuesContainer}>
                        {valuesList.map((value) => (
                          <View key={value} style={styles.valueChip}>
                            <Text variant="caption" color={colors.primary}>{value}</Text>
                          </View>
                        ))}
                      </View>
                    </>
                  )}
                </>
              ) : (
                <Text variant="body" color={colors.textTertiary} align="center">
                  Toca para configurar tu personalidad
                </Text>
              )}
            </Card>
          </TouchableOpacity>
        </View>

        {/* Lo que tu avatar sabe de ti — category counts */}
        {hasCategories && (
          <View style={styles.section}>
            <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
              Lo que tu avatar sabe de ti
            </Text>
            <Card variant="glass" padding="sm">
              {Object.entries(insightsByCategory).map(([category, count], idx, arr) => {
                const config = CATEGORY_CONFIG[category];
                if (!config) return null;
                const isLast = idx === arr.length - 1;
                return (
                  <View key={category}>
                    <View style={styles.categoryRow}>
                      <Ionicons name={config.icon} size={18} color={colors.textSecondary} />
                      <Text variant="body" color={colors.textPrimary} style={styles.categoryLabel}>
                        {config.label}
                      </Text>
                      <View style={styles.categoryCountPill}>
                        <Text variant="caption" color={colors.primary} style={styles.categoryCountText}>
                          {count}
                        </Text>
                      </View>
                    </View>
                    {!isLast && <View style={styles.categoryDivider} />}
                  </View>
                );
              })}
            </Card>
          </View>
        )}

        {/* Insights recientes — chip badges with the most recent insight strings */}
        {insights.length > 0 && (
          <View style={styles.section}>
            <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
              Insights recientes
            </Text>
            <View style={styles.insightChips}>
              {insights.slice(0, 6).map((it) => {
                const text = it.content || it.text || it.summary;
                if (!text) return null;
                return (
                  <View key={it.id || text} style={styles.insightChip}>
                    <Text variant="caption" color={colors.primary}>{text}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        )}

        {/* Redes sociales */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Redes sociales
          </Text>
          <Card variant="glass" padding="sm">
            {PROVIDERS.map((p, i) => {
              const s = statuses[p.id] || {};
              const connected = !!s.connected;
              const isLast = i === PROVIDERS.length - 1;
              return (
                <View key={p.id}>
                  <TouchableOpacity
                    style={styles.socialButton}
                    onPress={() => navigation.navigate('DataAccess', { provider: p.id })}
                    activeOpacity={0.7}
                  >
                    <View style={styles.socialButtonLeft}>
                      <Ionicons
                        name={p.icon}
                        size={22}
                        color={connected ? p.color : colors.textTertiary}
                      />
                      <View style={styles.socialButtonInfo}>
                        <Text
                          variant="body"
                          color={connected ? colors.textPrimary : colors.textSecondary}
                        >
                          {p.label}
                        </Text>
                        {connected && s.insights_count > 0 && (
                          <Text variant="caption" color={colors.primary}>
                            {s.insights_count} insights importados
                          </Text>
                        )}
                      </View>
                    </View>
                    {connected ? (
                      <View style={styles.connectedBadge}>
                        <Ionicons name="checkmark-circle" size={16} color={colors.success} />
                        <Text variant="caption" color={colors.success}>Conectado</Text>
                      </View>
                    ) : (
                      <Text variant="caption" color={colors.primary}>Conectar</Text>
                    )}
                  </TouchableOpacity>
                  {!isLast && <View style={styles.socialDivider} />}
                </View>
              );
            })}
          </Card>
        </View>

        {/* Configuración menu */}
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Configuración
          </Text>
          <Card variant="glass" padding="sm">
            <MenuItem
              icon="color-palette"
              label="Personalizar Avatar"
              subtitle="Color, ojos, expresión y más"
              onPress={() => navigation.navigate('AvatarCustomize')}
              accentColor="#00D4AA"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="bulb"
              label="Mis Memorias"
              subtitle="Lo que tu avatar recuerda"
              onPress={() => navigation.navigate('MemoryManager')}
              badge={totalInsights}
              accentColor="#FFB800"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="shield-checkmark"
              label="Acceso a Datos"
              subtitle="Qué datos usa tu avatar"
              onPress={() => navigation.navigate('DataAccess')}
              accentColor="#00B4D8"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="options"
              label="Comportamiento del Avatar"
              subtitle="Tono, idioma y límites"
              onPress={() => navigation.navigate('AvatarBehavior')}
              accentColor="#A78BFA"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="stats-chart"
              label="Estadísticas"
              subtitle="Tu actividad y progreso"
              onPress={() => navigation.navigate('ConversationStats')}
              accentColor="#F472B6"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="school"
              label="Enseñar al Avatar"
              subtitle="Agrega información manualmente"
              onPress={() => navigation.navigate('TeachAvatar')}
              accentColor="#34D399"
            />
            <View style={styles.menuDivider} />
            <MenuItem
              icon="mic"
              label="Entrenamiento por audio"
              subtitle="Voz, frases y sesiones grabadas"
              onPress={() => navigation.navigate('AudioHistory')}
              accentColor="#FF6B9D"
            />
          </Card>
        </View>

        <View style={styles.logoutWrap}>
          <Button variant="danger" fullWidth onPress={handleLogout}>
            Cerrar sesión
          </Button>
        </View>
      </ScrollView>
    </View>
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
  avatarSection: {
    alignItems: 'center',
    paddingTop: spacing.xs,
    paddingBottom: spacing.lg,
    paddingHorizontal: spacing.lg,
    gap: spacing.xs,
  },
  avatarFaceWrapper: {
    width: 140,
    height: 140,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  avatarNameText: {
    fontSize: typography.sizes.xl,
    lineHeight: typography.lineHeights.xl,
  },
  knowledgeBar: { width: '100%', marginTop: spacing.xs },
  knowledgeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xxs,
  },
  knowledgeLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  knowledgeLabelText: { marginLeft: 2 },
  knowledgeTrack: {
    height: 8,
    backgroundColor: colors.border,
    borderRadius: 4,
    overflow: 'hidden',
  },
  knowledgeFill: {
    height: 8,
    backgroundColor: colors.primary,
    borderRadius: 4,
  },
  section: { marginTop: spacing.lg },
  sectionTitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },

  // Mi Huella Digital
  huellaHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },

  // Personalidad header (label + Editar action)
  personalityHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
    marginRight: spacing.xxs,
  },
  sourceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  sourceIconBg: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.sm,
  },
  sourceInfo: { flex: 1 },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.md,
  },

  // Personality progress bar
  personalityContainer: { paddingVertical: spacing.xs },
  personalityLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  personalityTrack: {
    height: 6,
    backgroundColor: colors.border,
    borderRadius: 3,
    position: 'relative',
    overflow: 'visible',
  },
  personalityFill: {
    height: 6,
    backgroundColor: colors.primary,
    borderRadius: 3,
  },
  personalityIndicator: {
    position: 'absolute',
    top: -4,
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: colors.primaryLight,
    marginLeft: -7,
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 4,
    elevation: 4,
  },
  personalitySummary: {
    marginTop: spacing.xs,
  },
  personalitySpacer: { height: spacing.md },

  valuesLabel: { marginBottom: spacing.xs },
  valuesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  valueChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.primary,
  },

  // Category list
  categoryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
    gap: spacing.sm,
  },
  categoryLabel: { flex: 1 },
  categoryCountPill: {
    minWidth: 32,
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
    borderRadius: borders.radius.full,
    backgroundColor: 'rgba(0, 212, 170, 0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  categoryCountText: { fontWeight: '700' },
  categoryDivider: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 26 + spacing.sm,
  },

  // Insights recientes chips
  insightChips: {
    gap: spacing.xs,
  },
  insightChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.06)',
    alignSelf: 'flex-start',
    maxWidth: '100%',
  },

  // Social
  socialButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  socialButtonLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  socialButtonInfo: { marginLeft: spacing.sm },
  connectedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  socialDivider: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 36,
  },

  // Configuración menu
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  menuIconContainer: {
    width: 40,
    height: 40,
    borderRadius: borders.radius.md,
    justifyContent: 'center',
    alignItems: 'center',
  },
  menuTextContainer: {
    flex: 1,
    marginLeft: spacing.sm,
  },
  menuRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  badge: {
    backgroundColor: colors.primary,
    borderRadius: borders.radius.full,
    paddingHorizontal: 8,
    paddingVertical: 2,
    minWidth: 24,
    alignItems: 'center',
  },
  badgeText: { fontSize: 10, fontWeight: '700' },
  menuDivider: {
    height: 1,
    backgroundColor: colors.border,
    marginLeft: 52,
  },

  logoutWrap: {
    paddingHorizontal: spacing.md,
    marginTop: spacing.xl,
  },
});
