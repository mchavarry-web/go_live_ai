// Lets the user revise everything captured during onboarding:
// age range, interests, personality sliders, avatar name, values.
// Persists via PATCH /api/v1/avatar with deep-merged `behavior`.
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';

import Text from '../../components/ui/Text';
import Card from '../../components/ui/Card';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import LoadingSpinner from '../../components/ui/LoadingSpinner';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const AGE_RANGES = [
  { label: '18 - 24', value: '18_24' },
  { label: '25 - 34', value: '25_34' },
  { label: '35 - 44', value: '35_44' },
  { label: '45 - 54', value: '45_54' },
  { label: '55+',     value: '55_plus' },
];

const INTERESTS = [
  'Tecnología', 'Ciencia', 'Arte', 'Música', 'Deportes', 'Cocina',
  'Viajes', 'Lectura', 'Naturaleza', 'Meditación', 'Negocios', 'Gaming',
];

const VALUES = [
  'Honestidad', 'Creatividad', 'Ambición', 'Empatía',
  'Libertad', 'Familia', 'Salud', 'Conocimiento',
];

const SLIDER_STEPS = [0, 0.25, 0.5, 0.75, 1.0];

function Chip({ label, selected, onPress }) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        selected && styles.chipSelected,
        pressed && styles.chipPressed,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected }}
    >
      <Text
        variant="label"
        color={selected ? colors.textInverse : colors.textPrimary}
        style={styles.chipText}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function DotSlider({ leftLabel, rightLabel, value, onChange }) {
  return (
    <View style={styles.sliderContainer}>
      <View style={styles.sliderLabelsRow}>
        <Text variant="caption" color={colors.textSecondary}>{leftLabel}</Text>
        <Text variant="caption" color={colors.textSecondary}>{rightLabel}</Text>
      </View>
      <View style={styles.dotsRow}>
        <View style={styles.sliderTrack} />
        {SLIDER_STEPS.map((step) => {
          const isActive = step === value;
          return (
            <Pressable
              key={step}
              onPress={() => onChange(step)}
              hitSlop={12}
              accessibilityRole="adjustable"
              accessibilityLabel={`${leftLabel}-${rightLabel} ${Math.round(step * 100)}%`}
              accessibilityState={{ selected: isActive }}
              style={styles.dotTouchable}
            >
              <View style={[styles.dot, isActive && styles.dotActive]} />
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export default function EditPersonalityScreen({ navigation }) {
  const { refreshUserData } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [avatarName, setAvatarName] = useState('');
  const [ageRange, setAgeRange] = useState('');
  const [interests, setInterests] = useState([]);
  const [values, setValues] = useState([]);
  const [introvertExtrovert, setIntrovertExtrovert] = useState(0.5);
  const [rationalEmotional, setRationalEmotional] = useState(0.5);
  const [original, setOriginal] = useState(null);

  const fetchAvatar = useCallback(async () => {
    setLoading(true);
    const { success, data } = await apiService.getAvatar();
    if (success) {
      const avatar = data.avatar || {};
      const behavior = avatar.behavior || {};
      const snapshot = {
        avatarName: avatar.name || '',
        ageRange: behavior.age_range || '',
        interests: Array.isArray(behavior.interests) ? behavior.interests : [],
        values: Array.isArray(behavior.values) ? behavior.values : [],
        introvertExtrovert: typeof behavior.introvert_extrovert === 'number'
          ? behavior.introvert_extrovert
          : 0.5,
        rationalEmotional: typeof behavior.rational_emotional === 'number'
          ? behavior.rational_emotional
          : 0.5,
      };
      setAvatarName(snapshot.avatarName);
      setAgeRange(snapshot.ageRange);
      setInterests(snapshot.interests);
      setValues(snapshot.values);
      setIntrovertExtrovert(snapshot.introvertExtrovert);
      setRationalEmotional(snapshot.rationalEmotional);
      setOriginal(snapshot);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchAvatar(); }, [fetchAvatar]);

  const toggleInterest = (interest) => {
    setInterests((prev) =>
      prev.includes(interest) ? prev.filter((i) => i !== interest) : [...prev, interest],
    );
  };

  const toggleValue = (value) => {
    setValues((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  };

  const hasChanges = original ? (
    avatarName !== original.avatarName ||
    ageRange !== original.ageRange ||
    JSON.stringify(interests) !== JSON.stringify(original.interests) ||
    JSON.stringify(values) !== JSON.stringify(original.values) ||
    introvertExtrovert !== original.introvertExtrovert ||
    rationalEmotional !== original.rationalEmotional
  ) : false;

  const canSave = hasChanges &&
    avatarName.trim().length > 0 &&
    values.length >= 2 &&
    interests.length >= 3 &&
    ageRange.length > 0;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    const behavior = {
      age_range: ageRange,
      interests,
      values,
      introvert_extrovert: introvertExtrovert,
      rational_emotional: rationalEmotional,
    };
    const { success, error } = await apiService.updateAvatar({
      name: avatarName.trim(),
      behavior,
    });
    setSaving(false);
    if (success) {
      await refreshUserData();
      navigation.goBack();
    } else {
      Alert.alert('Error', error || 'No se pudieron guardar los cambios.');
    }
  };

  if (loading) return <LoadingSpinner fullscreen message="Cargando..." />;

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Avatar
          </Text>
          <Card variant="glass" padding="md">
            <Input
              label="Nombre del avatar"
              placeholder="Ej: Atlas, Luna, Nova..."
              value={avatarName}
              onChangeText={setAvatarName}
              maxLength={30}
              autoCapitalize="words"
            />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Rango de edad
          </Text>
          <Card variant="glass" padding="md">
            <View style={styles.chipGrid}>
              {AGE_RANGES.map((age) => (
                <Chip
                  key={age.value}
                  label={age.label}
                  selected={ageRange === age.value}
                  onPress={() => setAgeRange(age.value)}
                />
              ))}
            </View>
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Intereses
          </Text>
          <Text variant="caption" color={colors.textTertiary} style={styles.sectionSubtitle}>
            Selecciona al menos 3.
          </Text>
          <Card variant="glass" padding="md">
            <View style={styles.chipGrid}>
              {INTERESTS.map((interest) => (
                <Chip
                  key={interest}
                  label={interest}
                  selected={interests.includes(interest)}
                  onPress={() => toggleInterest(interest)}
                />
              ))}
            </View>
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Personalidad
          </Text>
          <Card variant="glass" padding="md">
            <DotSlider
              leftLabel="Introvertido"
              rightLabel="Extrovertido"
              value={introvertExtrovert}
              onChange={setIntrovertExtrovert}
            />
            <View style={styles.sliderDivider} />
            <DotSlider
              leftLabel="Racional"
              rightLabel="Emocional"
              value={rationalEmotional}
              onChange={setRationalEmotional}
            />
          </Card>
        </View>

        <View style={styles.section}>
          <Text variant="label" color={colors.textSecondary} style={styles.sectionTitle}>
            Valores
          </Text>
          <Text variant="caption" color={colors.textTertiary} style={styles.sectionSubtitle}>
            Selecciona al menos 2.
          </Text>
          <Card variant="glass" padding="md">
            <View style={styles.chipGrid}>
              {VALUES.map((val) => (
                <Chip
                  key={val}
                  label={val}
                  selected={values.includes(val)}
                  onPress={() => toggleValue(val)}
                />
              ))}
            </View>
          </Card>
        </View>
      </ScrollView>

      <View style={styles.footer}>
        <Button
          title={saving ? 'Guardando...' : 'Guardar cambios'}
          onPress={handleSave}
          disabled={!canSave || saving}
          loading={saving}
          fullWidth
          size="lg"
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  scrollView: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xl,
  },
  section: { marginTop: spacing.lg },
  sectionTitle: { marginBottom: spacing.xxs, marginLeft: spacing.xxs },
  sectionSubtitle: { marginBottom: spacing.xs, marginLeft: spacing.xxs },
  chipGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  chip: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: borders.radius.xl,
    backgroundColor: colors.surface,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
  },
  chipSelected: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipPressed: { opacity: 0.7 },
  chipText: { textAlign: 'center' },

  sliderContainer: { paddingVertical: spacing.xs },
  sliderLabelsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
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
  sliderDivider: { height: spacing.md },

  footer: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderTopWidth: borders.width.thin,
    borderTopColor: colors.border,
    backgroundColor: colors.background,
  },
});
