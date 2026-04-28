// 1:1 port of gln-mobile-app/src/screens/onboarding/QuestionsScreen.tsx.
// 4-step card-based wizard (the simpler counterpart to the conversational
// flow). Kept around so callers that prefer this layout can route to it,
// but the active OnboardingNavigator entry is the conversational one.
import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';

import Text from '../../components/ui/Text';
import Button from '../../components/ui/Button';
import Input from '../../components/ui/Input';
import ProgressBar from '../../components/onboarding/ProgressBar';
import QuestionCard from '../../components/onboarding/QuestionCard';
import { colors, spacing, borders } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const TOTAL_STEPS = 4;

const AGE_RANGES = [
  { label: '18 - 24', value: '18_24' },
  { label: '25 - 34', value: '25_34' },
  { label: '35 - 44', value: '35_44' },
  { label: '45 - 54', value: '45_54' },
  { label: '55+', value: '55_plus' },
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

function DotSlider({ label, leftLabel, rightLabel, value, onChange }) {
  return (
    <View style={styles.sliderContainer} accessibilityLabel={label}>
      <Text variant="label" style={styles.sliderLabel}>
        {label}
      </Text>
      <View style={styles.sliderLabelsRow}>
        <Text variant="caption" color={colors.textSecondary}>
          {leftLabel}
        </Text>
        <Text variant="caption" color={colors.textSecondary}>
          {rightLabel}
        </Text>
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
              accessibilityLabel={`${label} ${Math.round(step * 100)}%`}
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

function StepAgeRange({ selected, onSelect }) {
  return (
    <QuestionCard
      title="¿Cuál es tu rango de edad?"
      subtitle="Esto nos ayuda a personalizar tu experiencia."
    >
      <View style={styles.chipGrid}>
        {AGE_RANGES.map((age) => (
          <Chip
            key={age.value}
            label={age.label}
            selected={selected === age.value}
            onPress={() => onSelect(age.value)}
          />
        ))}
      </View>
    </QuestionCard>
  );
}

function StepInterests({ selected, onToggle }) {
  return (
    <QuestionCard
      title="¿Qué te interesa?"
      subtitle="Selecciona al menos 3 intereses."
    >
      <View style={styles.chipGrid}>
        {INTERESTS.map((interest) => (
          <Chip
            key={interest}
            label={interest}
            selected={selected.includes(interest)}
            onPress={() => onToggle(interest)}
          />
        ))}
      </View>
    </QuestionCard>
  );
}

function StepPersonality({
  introvertExtrovert,
  rationalEmotional,
  onIntrovertExtrovertChange,
  onRationalEmotionalChange,
}) {
  return (
    <QuestionCard
      title="Tu personalidad"
      subtitle="Desliza para indicar dónde te ubicas."
    >
      <DotSlider
        label="Sociabilidad"
        leftLabel="Introvertido"
        rightLabel="Extrovertido"
        value={introvertExtrovert}
        onChange={onIntrovertExtrovertChange}
      />
      <DotSlider
        label="Pensamiento"
        leftLabel="Racional"
        rightLabel="Emocional"
        value={rationalEmotional}
        onChange={onRationalEmotionalChange}
      />
    </QuestionCard>
  );
}

function StepAvatar({ name, onNameChange, selectedValues, onToggleValue }) {
  return (
    <QuestionCard
      title="Crea tu avatar"
      subtitle="Dale un nombre y elige sus valores (mín. 2)."
    >
      <Input
        label="Nombre del avatar"
        placeholder="Ej: Atlas, Luna, Nova..."
        value={name}
        onChangeText={onNameChange}
        maxLength={30}
        autoCapitalize="words"
        accessibilityLabel="Nombre del avatar"
      />
      <View style={styles.valuesSection}>
        <Text
          variant="label"
          color={colors.textSecondary}
          style={styles.valuesSectionLabel}
        >
          Valores
        </Text>
        <View style={styles.chipGrid}>
          {VALUES.map((val) => (
            <Chip
              key={val}
              label={val}
              selected={selectedValues.includes(val)}
              onPress={() => onToggleValue(val)}
            />
          ))}
        </View>
      </View>
    </QuestionCard>
  );
}

export default function QuestionsScreen({ navigation }) {
  const { refreshUserData } = useAuth();

  const [step, setStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [ageRange, setAgeRange] = useState('');
  const [interests, setInterests] = useState([]);
  const [introvertExtrovert, setIntrovertExtrovert] = useState(0.5);
  const [rationalEmotional, setRationalEmotional] = useState(0.5);
  const [avatarName, setAvatarName] = useState('');
  const [values, setValues] = useState([]);

  const canAdvance = useMemo(() => {
    switch (step) {
      case 0: return ageRange.length > 0;
      case 1: return interests.length >= 3;
      case 2: return true;
      case 3: return avatarName.trim().length > 0 && values.length >= 2;
      default: return false;
    }
  }, [step, ageRange, interests, avatarName, values]);

  const isLastStep = step === TOTAL_STEPS - 1;

  const toggleInterest = useCallback((interest) => {
    setInterests((prev) =>
      prev.includes(interest) ? prev.filter((i) => i !== interest) : [...prev, interest],
    );
  }, []);

  const toggleValue = useCallback((value) => {
    setValues((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  }, []);

  const handleBack = useCallback(() => {
    if (step > 0) setStep((prev) => prev - 1);
  }, [step]);

  const handleNext = useCallback(async () => {
    if (!canAdvance) return;
    if (!isLastStep) {
      setStep((prev) => prev + 1);
      return;
    }
    setIsSubmitting(true);
    try {
      const behavior = {
        age_range: ageRange,
        interests,
        values,
        introvert_extrovert: introvertExtrovert,
        rational_emotional: rationalEmotional,
      };
      const r1 = await apiService.updateAvatar({ name: avatarName.trim(), behavior });
      if (!r1.success) throw new Error(r1.error || 'No se pudo guardar el avatar');
      const r2 = await apiService.completeOnboarding({ formalityLevel: 0.5 });
      if (!r2.success) throw new Error(r2.error || 'No se pudo completar el onboarding');
      await refreshUserData();
      navigation.navigate('AvatarCreated');
    } catch (error) {
      Alert.alert('Error', `No se pudo completar el onboarding. ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  }, [canAdvance, isLastStep, avatarName, ageRange, interests, introvertExtrovert, rationalEmotional, values, navigation, refreshUserData]);

  const renderStep = () => {
    switch (step) {
      case 0:
        return <StepAgeRange selected={ageRange} onSelect={setAgeRange} />;
      case 1:
        return <StepInterests selected={interests} onToggle={toggleInterest} />;
      case 2:
        return (
          <StepPersonality
            introvertExtrovert={introvertExtrovert}
            rationalEmotional={rationalEmotional}
            onIntrovertExtrovertChange={setIntrovertExtrovert}
            onRationalEmotionalChange={setRationalEmotional}
          />
        );
      case 3:
        return (
          <StepAvatar
            name={avatarName}
            onNameChange={setAvatarName}
            selectedValues={values}
            onToggleValue={toggleValue}
          />
        );
      default:
        return <View />;
    }
  };

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <ProgressBar progress={(step + 1) / TOTAL_STEPS} style={styles.progressBar} />
        <View style={styles.headerRow}>
          {step > 0 ? (
            <Pressable
              onPress={handleBack}
              hitSlop={12}
              accessibilityRole="button"
              accessibilityLabel="Atrás"
              style={({ pressed }) => [styles.backButton, pressed && styles.backButtonPressed]}
            >
              <Text variant="label" color={colors.primary}>
                ← Atrás
              </Text>
            </Pressable>
          ) : (
            <View />
          )}
          <Text variant="caption" color={colors.textTertiary}>
            {step + 1} / {TOTAL_STEPS}
          </Text>
        </View>
      </View>

      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Animated.View key={step} entering={FadeIn.duration(300)} exiting={FadeOut.duration(150)}>
          {renderStep()}
        </Animated.View>
      </ScrollView>

      <View style={styles.footer}>
        <Button
          title={isLastStep ? 'Crear Avatar' : 'Siguiente'}
          onPress={handleNext}
          disabled={!canAdvance}
          loading={isSubmitting}
          fullWidth
          size="lg"
          accessibilityLabel={isLastStep ? 'Crear Avatar' : 'Siguiente paso'}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  header: {
    paddingTop: spacing.xxl,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  progressBar: { marginBottom: spacing.sm },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  backButton: {
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.xs,
    borderRadius: borders.radius.sm,
  },
  backButtonPressed: { opacity: 0.6 },
  scrollView: { flex: 1 },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xl,
  },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: borders.width.thin,
    borderTopColor: colors.border,
  },
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
  sliderContainer: { marginBottom: spacing.lg },
  sliderLabel: { marginBottom: spacing.xs },
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
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.elevated,
    borderWidth: borders.width.medium,
    borderColor: colors.borderLight,
  },
  dotActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryLight,
    width: 26,
    height: 26,
    borderRadius: 13,
  },
  valuesSection: { marginTop: spacing.lg },
  valuesSectionLabel: { marginBottom: spacing.xs },
});
