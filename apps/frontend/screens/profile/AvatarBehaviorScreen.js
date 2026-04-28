// 1:1 port of gln-mobile-app/src/screens/profile/AvatarBehaviorScreen.tsx.
// Three tone sliders (formality / humor / verbosity), a language picker,
// and two tag-input lists (preferred / restricted topics). Persists via
// PATCH /api/v1/avatar with the `behavior` jsonb bag.
//
// Note: the original used a Reanimated/Gesture-Handler custom slider; we
// keep the same five-stop dot slider used elsewhere in onboarding for
// stability across web / iOS / Android.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders, typography } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const DEFAULT_BEHAVIOR = {
  tone_formality: 0.5,
  tone_humor: 0.5,
  tone_verbosity: 0.5,
  language: 'es',
  preferred_topics: [],
  restricted_topics: [],
};

const LANGUAGES = [
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'English' },
  { value: 'pt', label: 'Português' },
];

const SLIDER_STEPS = [0, 0.25, 0.5, 0.75, 1.0];

function ToneSlider({ label, leftLabel, rightLabel, value, onValueChange }) {
  return (
    <View style={styles.sliderContainer}>
      <Text variant="label" color={colors.textSecondary} style={styles.sliderLabel}>
        {label}
      </Text>
      <View style={styles.dotsRow}>
        <View style={styles.sliderTrack} />
        {SLIDER_STEPS.map((step) => {
          const isActive = step === value;
          return (
            <Pressable
              key={step}
              onPress={() => onValueChange(step)}
              hitSlop={12}
              accessibilityRole="adjustable"
              accessibilityLabel={`${label} ${Math.round(step * 100)}%`}
              accessibilityState={{ selected: isActive }}
              style={styles.dotTouchable}
            >
              <View style={[styles.dot, isActive && styles.dotActive]} />
            </Pressable>
          );
        })}
      </View>
      <View style={styles.sliderLabels}>
        <Text variant="caption" color={colors.textTertiary}>{leftLabel}</Text>
        <Text variant="caption" color={colors.primary}>{Math.round(value * 100)}%</Text>
        <Text variant="caption" color={colors.textTertiary}>{rightLabel}</Text>
      </View>
    </View>
  );
}

function TagInput({ tags, onAddTag, onRemoveTag, placeholder }) {
  const [inputValue, setInputValue] = useState('');
  const handleAdd = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onAddTag(trimmed);
      setInputValue('');
    }
  };
  return (
    <View>
      <View style={styles.tagInputRow}>
        <TextInput
          style={styles.tagInput}
          value={inputValue}
          onChangeText={setInputValue}
          placeholder={placeholder}
          placeholderTextColor={colors.textTertiary}
          onSubmitEditing={handleAdd}
          returnKeyType="done"
          maxLength={100}
          selectionColor={colors.primary}
        />
        <TouchableOpacity
          style={styles.tagAddBtn}
          onPress={handleAdd}
          activeOpacity={0.7}
          disabled={!inputValue.trim()}
        >
          <Ionicons
            name="add-circle"
            size={28}
            color={inputValue.trim() ? colors.primary : colors.textTertiary}
          />
        </TouchableOpacity>
      </View>
      {tags.length > 0 && (
        <View style={styles.tagsWrap}>
          {tags.map((tag, index) => (
            <View key={`${tag}-${index}`} style={styles.tagChip}>
              <Text variant="caption" color={colors.primary}>{tag}</Text>
              <TouchableOpacity onPress={() => onRemoveTag(index)}>
                <Ionicons name="close-circle" size={16} color={colors.textTertiary} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

export default function AvatarBehaviorScreen() {
  const { refreshUserData } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState(DEFAULT_BEHAVIOR);
  const [originalSettings, setOriginalSettings] = useState(DEFAULT_BEHAVIOR);

  const fetchBehavior = useCallback(async () => {
    setLoading(true);
    const { success, data } = await apiService.getAvatar();
    if (success) {
      const behavior = data.avatar?.behavior || data.behavior || {};
      const parsed = {
        tone_formality:    behavior.tone_formality ?? 0.5,
        tone_humor:        behavior.tone_humor ?? 0.5,
        tone_verbosity:    behavior.tone_verbosity ?? 0.5,
        language:          behavior.language ?? 'es',
        preferred_topics:  behavior.preferred_topics ?? [],
        restricted_topics: behavior.restricted_topics ?? [],
      };
      setSettings(parsed);
      setOriginalSettings(parsed);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchBehavior(); }, [fetchBehavior]);

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(originalSettings);

  const handleSave = async () => {
    if (!hasChanges) return;
    setSaving(true);
    const { success, error } = await apiService.updateAvatar({ behavior: settings });
    setSaving(false);
    if (success) {
      setOriginalSettings({ ...settings });
      refreshUserData();
      Alert.alert('Listo', 'Configuración de comportamiento actualizada.');
    } else {
      Alert.alert('Error', error || 'No se pudieron guardar los cambios.');
    }
  };

  if (loading) return <LoadingSpinner fullscreen message="Cargando configuración..." />;

  return (
    <SafeAreaView style={styles.safeArea} edges={['bottom']}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Tono de Comunicación
          </Text>
          <Card variant="glass" padding="md">
            <ToneSlider
              label="Formalidad"
              leftLabel="Casual"
              rightLabel="Formal"
              value={settings.tone_formality}
              onValueChange={(val) => setSettings({ ...settings, tone_formality: val })}
            />
            <View style={styles.sliderDivider} />
            <ToneSlider
              label="Humor"
              leftLabel="Serio"
              rightLabel="Divertido"
              value={settings.tone_humor}
              onValueChange={(val) => setSettings({ ...settings, tone_humor: val })}
            />
            <View style={styles.sliderDivider} />
            <ToneSlider
              label="Extensión"
              leftLabel="Breve"
              rightLabel="Detallado"
              value={settings.tone_verbosity}
              onValueChange={(val) => setSettings({ ...settings, tone_verbosity: val })}
            />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Idioma Preferido
          </Text>
          <Card variant="glass" padding="md">
            <View style={styles.languageRow}>
              {LANGUAGES.map((lang) => (
                <TouchableOpacity
                  key={lang.value}
                  style={[
                    styles.languageBtn,
                    settings.language === lang.value && styles.languageBtnSelected,
                  ]}
                  onPress={() => setSettings({ ...settings, language: lang.value })}
                  activeOpacity={0.7}
                >
                  <Text
                    variant="body"
                    color={settings.language === lang.value ? colors.primary : colors.textSecondary}
                  >
                    {lang.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Temas de Interés
          </Text>
          <Text variant="caption" color={colors.textTertiary} style={styles.sectionSubtitle}>
            El avatar explorará más estos temas en las conversaciones
          </Text>
          <Card variant="glass" padding="md">
            <TagInput
              tags={settings.preferred_topics}
              onAddTag={(tag) =>
                setSettings({
                  ...settings,
                  preferred_topics: [...settings.preferred_topics, tag],
                })
              }
              onRemoveTag={(idx) =>
                setSettings({
                  ...settings,
                  preferred_topics: settings.preferred_topics.filter((_, i) => i !== idx),
                })
              }
              placeholder="Agregar tema (ej: tecnología, viajes...)"
            />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Temas Restringidos
          </Text>
          <Text variant="caption" color={colors.textTertiary} style={styles.sectionSubtitle}>
            El avatar evitará hablar sobre estos temas
          </Text>
          <Card variant="glass" padding="md">
            <TagInput
              tags={settings.restricted_topics}
              onAddTag={(tag) =>
                setSettings({
                  ...settings,
                  restricted_topics: [...settings.restricted_topics, tag],
                })
              }
              onRemoveTag={(idx) =>
                setSettings({
                  ...settings,
                  restricted_topics: settings.restricted_topics.filter((_, i) => i !== idx),
                })
              }
              placeholder="Agregar tema restringido..."
            />
          </Card>
        </View>

        <View style={styles.saveSection}>
          <Button
            title={saving ? 'Guardando...' : 'Guardar Cambios'}
            onPress={handleSave}
            disabled={!hasChanges || saving}
            loading={saving}
            fullWidth
          />
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
    marginBottom: spacing.xxs,
    marginLeft: spacing.xxs,
  },
  sectionSubtitle: {
    marginBottom: spacing.xs,
    marginLeft: spacing.xxs,
  },
  sliderContainer: { paddingVertical: spacing.xs },
  sliderLabel: { marginBottom: spacing.sm },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    height: 40,
    position: 'relative',
  },
  sliderTrack: {
    position: 'absolute',
    left: 12,
    right: 12,
    height: 2,
    backgroundColor: colors.border,
    borderRadius: borders.radius.full,
  },
  dotTouchable: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 1,
  },
  dot: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: colors.elevated,
    borderWidth: 1.5,
    borderColor: colors.borderLight,
  },
  dotActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryLight,
    width: 22,
    height: 22,
    borderRadius: 11,
  },
  sliderLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xxs,
  },
  sliderDivider: { height: spacing.xs },
  languageRow: { flexDirection: 'row', gap: spacing.xs },
  languageBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    borderRadius: borders.radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  languageBtnSelected: {
    borderColor: colors.primary,
    backgroundColor: 'rgba(0, 212, 170, 0.08)',
  },
  tagInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  tagInput: {
    flex: 1,
    backgroundColor: colors.elevated,
    borderRadius: borders.radius.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    fontSize: typography.sizes.sm,
    fontFamily: typography.fontFamilies.body,
    color: colors.textPrimary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tagAddBtn: { padding: spacing.xxs },
  tagsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.sm,
  },
  tagChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    backgroundColor: colors.elevated,
    borderRadius: borders.radius.full,
    borderWidth: 1,
    borderColor: colors.primary,
    gap: 4,
  },
  saveSection: {
    marginTop: spacing.xl,
    paddingHorizontal: spacing.md,
  },
});
