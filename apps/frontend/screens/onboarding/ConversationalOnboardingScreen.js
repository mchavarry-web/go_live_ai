// 1:1 port of gln-mobile-app/src/screens/onboarding/ConversationalOnboardingScreen.tsx.
// Conversational wizard with 7 steps:
//   0 — avatar name (text input)
//   1 — age range (single-select)
//   2 — interests (multi-select, min 3)
//   3 — personality (two dot sliders)
//   4 — values (multi-select, min 2)
//   5 — country (single-select w/ flag)
//   6 — connect Twitter / skip
//
// Each user pick adds a chat bubble + an avatar reply. The flow ends by
// persisting the avatar name (via PATCH /avatar — name + behavior jsonb)
// and country/timezone (via POST /onboarding/complete), then triggers a
// user refresh that flips RootNavigator from onboarding → main.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, { FadeInUp } from 'react-native-reanimated';

import Text from '../../components/ui/Text';
import Button from '../../components/ui/Button';
import ChatBubble from '../../components/onboarding/ChatBubble';
import QuickReplyChips from '../../components/onboarding/QuickReplyChips';
import ProgressBar from '../../components/onboarding/ProgressBar';
import AvatarFace from '../../components/avatar/AvatarFace';
import { colors, spacing, borders, typography } from '../../theme';
import apiService from '../../services/apiService';
import { useAuth } from '../../contexts/AuthContext';

const TOTAL_STEPS = 7;

const AGE_RANGES = [
  { label: '18 - 24', value: '18_24' },
  { label: '25 - 34', value: '25_34' },
  { label: '35 - 44', value: '35_44' },
  { label: '45 - 54', value: '45_54' },
  { label: '55+', value: '55_plus' },
];

const INTERESTS = [
  'Tecnología',
  'Ciencia',
  'Arte',
  'Música',
  'Deportes',
  'Cocina',
  'Viajes',
  'Lectura',
  'Naturaleza',
  'Meditación',
  'Negocios',
  'Gaming',
];

const VALUES = [
  'Honestidad',
  'Creatividad',
  'Ambición',
  'Empatía',
  'Libertad',
  'Familia',
  'Salud',
  'Conocimiento',
];

const COUNTRIES = [
  { label: 'Argentina',     value: 'ar', flag: '🇦🇷', timezone: 'America/Argentina/Buenos_Aires' },
  { label: 'México',        value: 'mx', flag: '🇲🇽', timezone: 'America/Mexico_City' },
  { label: 'Perú',          value: 'pe', flag: '🇵🇪', timezone: 'America/Lima' },
  { label: 'Colombia',      value: 'co', flag: '🇨🇴', timezone: 'America/Bogota' },
  { label: 'Chile',         value: 'cl', flag: '🇨🇱', timezone: 'America/Santiago' },
  { label: 'España',        value: 'es', flag: '🇪🇸', timezone: 'Europe/Madrid' },
  { label: 'Uruguay',       value: 'uy', flag: '🇺🇾', timezone: 'America/Montevideo' },
  { label: 'Ecuador',       value: 'ec', flag: '🇪🇨', timezone: 'America/Guayaquil' },
  { label: 'Venezuela',     value: 've', flag: '🇻🇪', timezone: 'America/Caracas' },
  { label: 'USA (English)', value: 'us', flag: '🇺🇸', timezone: 'America/New_York' },
  { label: 'UK (English)',  value: 'gb', flag: '🇬🇧', timezone: 'Europe/London' },
];

const SLIDER_STEPS = [0, 0.25, 0.5, 0.75, 1.0];

function DotSlider({ label, leftLabel, rightLabel, value, onChange }) {
  return (
    <View style={sliderStyles.container} accessibilityLabel={label}>
      <Text variant="label" style={sliderStyles.label}>
        {label}
      </Text>
      <View style={sliderStyles.labelsRow}>
        <Text variant="caption" color={colors.textSecondary}>
          {leftLabel}
        </Text>
        <Text variant="caption" color={colors.textSecondary}>
          {rightLabel}
        </Text>
      </View>
      <View style={sliderStyles.dotsRow}>
        <View style={sliderStyles.track} />
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
              style={sliderStyles.dotTouchable}
            >
              <View style={[sliderStyles.dot, isActive && sliderStyles.dotActive]} />
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const sliderStyles = StyleSheet.create({
  container: { marginBottom: spacing.md },
  label: { marginBottom: spacing.xxs },
  labelsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.xxs,
  },
  dotsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    height: 40,
    position: 'relative',
  },
  track: {
    position: 'absolute',
    left: 12,
    right: 12,
    height: 2,
    backgroundColor: colors.border,
    borderRadius: 9999,
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
    borderWidth: 1.5,
    borderColor: colors.borderLight,
  },
  dotActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryLight,
    width: 26,
    height: 26,
    borderRadius: 13,
  },
});

export default function ConversationalOnboardingScreen({ navigation }) {
  const { refreshUserData } = useAuth();

  const [step, setStep] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [avatarName, setAvatarName] = useState('');
  const [ageRange, setAgeRange] = useState('');
  const [interests, setInterests] = useState([]);
  const [introvertExtrovert, setIntrovertExtrovert] = useState(0.5);
  const [rationalEmotional, setRationalEmotional] = useState(0.5);
  const [values, setValues] = useState([]);
  const [country, setCountry] = useState('');
  const [twitterUsername, setTwitterUsername] = useState('');
  const [showTwitterInput, setShowTwitterInput] = useState(false);

  const [messages, setMessages] = useState([
    {
      id: 'welcome-1',
      sender: 'avatar',
      text: '¡Hola! Soy tu futuro avatar digital. Vamos a conocernos para que pueda ser el mejor compañero para ti.',
    },
    {
      id: 'welcome-2',
      sender: 'avatar',
      text: 'Primero, ¿cómo te gustaría que me llame? Escribe un nombre para mí.',
    },
  ]);

  const flatListRef = useRef(null);
  const nameInputRef = useRef(null);
  const twitterInputRef = useRef(null);

  const addMessages = useCallback((...newMsgs) => {
    setMessages((prev) => [
      ...prev,
      ...newMsgs.map((m, i) => ({ ...m, id: `msg-${Date.now()}-${i}` })),
    ]);
  }, []);

  useEffect(() => {
    if (messages.length > 0) {
      const timer = setTimeout(() => {
        flatListRef.current?.scrollToEnd({ animated: true });
      }, 150);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [messages.length, step]);

  const canAdvance = useMemo(() => {
    switch (step) {
      case 0: return avatarName.trim().length > 0;
      case 1: return ageRange.length > 0;
      case 2: return interests.length >= 3;
      case 3: return true;
      case 4: return values.length >= 2;
      case 5: return country.length > 0;
      case 6: return true;
      default: return false;
    }
  }, [step, avatarName, ageRange, interests, values, country]);

  const handleNameSubmit = useCallback(() => {
    if (!avatarName.trim()) return;
    const name = avatarName.trim();
    addMessages(
      { sender: 'user', text: name },
      {
        sender: 'avatar',
        text: `¡${name}! Me encanta ese nombre. Ahora cuéntame, ¿en qué rango de edad estás?`,
      },
    );
    setStep(1);
  }, [avatarName, addMessages]);

  const handleAgeSelect = useCallback(
    (value) => {
      const label = AGE_RANGES.find((a) => a.value === value)?.label ?? value;
      setAgeRange(value);
      addMessages(
        { sender: 'user', text: label },
        {
          sender: 'avatar',
          text: '¡Genial! Y cuéntame, ¿qué te apasiona? Selecciona al menos 3 intereses.',
        },
      );
      setStep(2);
    },
    [addMessages],
  );

  const handleInterestsToggle = useCallback((interest) => {
    setInterests((prev) =>
      prev.includes(interest) ? prev.filter((i) => i !== interest) : [...prev, interest],
    );
  }, []);

  const handleInterestsConfirm = useCallback(() => {
    if (interests.length < 3) return;
    addMessages(
      { sender: 'user', text: interests.join(', ') },
      {
        sender: 'avatar',
        text: '¡Qué interesante! Ahora hablemos de tu personalidad. Desliza los puntos para indicar dónde te ubicas.',
      },
    );
    setStep(3);
  }, [interests, addMessages]);

  const handlePersonalityConfirm = useCallback(() => {
    const introLabel =
      introvertExtrovert <= 0.25
        ? 'Introvertido'
        : introvertExtrovert >= 0.75
          ? 'Extrovertido'
          : 'Equilibrado';
    const rationalLabel =
      rationalEmotional <= 0.25
        ? 'Racional'
        : rationalEmotional >= 0.75
          ? 'Emocional'
          : 'Equilibrado';

    addMessages(
      { sender: 'user', text: `${introLabel} y ${rationalLabel}` },
      {
        sender: 'avatar',
        text: '¡Casi terminamos! ¿Qué valores te definen? Selecciona al menos 2.',
      },
    );
    setStep(4);
  }, [introvertExtrovert, rationalEmotional, addMessages]);

  const handleValuesToggle = useCallback((value) => {
    setValues((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value],
    );
  }, []);

  const handleValuesSubmit = useCallback(() => {
    if (values.length < 2) return;
    addMessages(
      { sender: 'user', text: values.join(', ') },
      {
        sender: 'avatar',
        text: '¿De qué país eres? Así adapto mi forma de hablar a tu estilo.',
      },
    );
    setStep(5);
  }, [values, addMessages]);

  const handleCountrySelect = useCallback(
    (value) => {
      const selected = COUNTRIES.find((c) => c.value === value);
      if (!selected) return;
      setCountry(value);
      addMessages(
        { sender: 'user', text: `${selected.flag} ${selected.label}` },
        {
          sender: 'avatar',
          text: '¡Genial! Una última cosa: ¿quieres conectar tu cuenta de X (Twitter)? Así puedo conocerte aún mejor analizando tus publicaciones.',
        },
      );
      setStep(6);
    },
    [addMessages],
  );

  const handleFinalSubmit = useCallback(async () => {
    setIsSubmitting(true);
    try {
      const selectedCountry = COUNTRIES.find((c) => c.value === country);
      const behavior = {
        age_range: ageRange,
        interests,
        values,
        introvert_extrovert: introvertExtrovert,
        rational_emotional: rationalEmotional,
      };
      // Persist avatar name + behavior bag
      const r1 = await apiService.updateAvatar({ name: avatarName.trim(), behavior });
      if (!r1.success) throw new Error(r1.error || 'No se pudo guardar el avatar');
      // Persist country + timezone (formality default = 0.5 → "neutral")
      const r2 = await apiService.completeOnboarding({
        country: country || undefined,
        timezone: selectedCountry?.timezone,
        formalityLevel: 0.5,
      });
      if (!r2.success) throw new Error(r2.error || 'No se pudo completar el onboarding');
      // Reload user so RootNavigator switches to MainTabs
      await refreshUserData();
      navigation.navigate('AvatarCreated');
    } catch (error) {
      Alert.alert('Error', `No se pudo completar el onboarding. ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  }, [avatarName, ageRange, interests, introvertExtrovert, rationalEmotional, values, country, refreshUserData, navigation]);

  const handleTwitterConnect = useCallback(() => {
    setShowTwitterInput(true);
    addMessages(
      { sender: 'user', text: 'Sí, conectar' },
      { sender: 'avatar', text: '¿Cuál es tu usuario de X? (sin el @)' },
    );
  }, [addMessages]);

  const handleTwitterSkip = useCallback(() => {
    addMessages(
      { sender: 'user', text: 'Omitir' },
      { sender: 'avatar', text: '¡Sin problema! Estoy creando tu avatar...' },
    );
    handleFinalSubmit();
  }, [addMessages, handleFinalSubmit]);

  const handleTwitterUsernameSubmit = useCallback(() => {
    const username = twitterUsername.trim().replace(/^@/, '');
    if (!username) return;
    addMessages(
      { sender: 'user', text: `@${username}` },
      {
        sender: 'avatar',
        text: '¡Perfecto! Voy a analizar tu cuenta de X en segundo plano mientras creamos tu avatar...',
      },
    );
    // Fire-and-forget — failures don't block onboarding
    apiService.ingestSocial('twitter', { username }).catch(() => {});
    handleFinalSubmit();
  }, [twitterUsername, addMessages, handleFinalSubmit]);

  const renderMessage = useCallback(
    ({ item, index }) => {
      const showAvatar =
        item.sender === 'avatar' &&
        (index === 0 || messages[index - 1]?.sender !== 'avatar');
      return (
        <ChatBubble text={item.text} sender={item.sender} showAvatar={showAvatar} delay={0} />
      );
    },
    [messages],
  );

  const renderStepControls = () => {
    switch (step) {
      case 0:
        return (
          <Animated.View entering={FadeInUp.duration(300).springify()} style={styles.inputArea}>
            <View style={styles.nameInputRow}>
              <TextInput
                ref={nameInputRef}
                style={styles.nameInput}
                placeholder="Ej: Atlas, Luna, Nova..."
                placeholderTextColor={colors.textTertiary}
                value={avatarName}
                onChangeText={setAvatarName}
                maxLength={30}
                autoCapitalize="words"
                selectionColor={colors.primary}
                onSubmitEditing={handleNameSubmit}
                returnKeyType="send"
                accessibilityLabel="Nombre del avatar"
              />
              <Pressable
                onPress={handleNameSubmit}
                disabled={!avatarName.trim()}
                style={({ pressed }) => [
                  styles.sendButton,
                  !avatarName.trim() && styles.sendButtonDisabled,
                  pressed && styles.sendButtonPressed,
                ]}
                accessibilityRole="button"
                accessibilityLabel="Enviar nombre"
              >
                <Text variant="label" color={avatarName.trim() ? colors.textInverse : colors.textTertiary}>
                  →
                </Text>
              </Pressable>
            </View>
          </Animated.View>
        );

      case 1:
        return (
          <QuickReplyChips
            options={AGE_RANGES.map((a) => a.label)}
            selected={ageRange ? [AGE_RANGES.find((a) => a.value === ageRange)?.label ?? ''] : []}
            onToggle={(label) => {
              const found = AGE_RANGES.find((a) => a.label === label);
              if (found) handleAgeSelect(found.value);
            }}
            singleSelect
            delay={200}
          />
        );

      case 2:
        return (
          <View>
            <QuickReplyChips
              options={INTERESTS}
              selected={interests}
              onToggle={handleInterestsToggle}
              delay={200}
            />
            {interests.length >= 3 && (
              <Animated.View entering={FadeInUp.duration(300)} style={styles.confirmContainer}>
                <Button
                  title={`Continuar (${interests.length} seleccionados)`}
                  onPress={handleInterestsConfirm}
                  fullWidth
                  size="md"
                />
              </Animated.View>
            )}
          </View>
        );

      case 3:
        return (
          <Animated.View entering={FadeInUp.duration(400).delay(200)} style={styles.slidersContainer}>
            <DotSlider
              label="Sociabilidad"
              leftLabel="Introvertido"
              rightLabel="Extrovertido"
              value={introvertExtrovert}
              onChange={setIntrovertExtrovert}
            />
            <DotSlider
              label="Pensamiento"
              leftLabel="Racional"
              rightLabel="Emocional"
              value={rationalEmotional}
              onChange={setRationalEmotional}
            />
            <Button title="Continuar" onPress={handlePersonalityConfirm} fullWidth size="md" />
          </Animated.View>
        );

      case 4:
        return (
          <View>
            <QuickReplyChips
              options={VALUES}
              selected={values}
              onToggle={handleValuesToggle}
              delay={200}
            />
            {values.length >= 2 && (
              <Animated.View entering={FadeInUp.duration(300)} style={styles.confirmContainer}>
                <Button title="Continuar" onPress={handleValuesSubmit} fullWidth size="md" />
              </Animated.View>
            )}
          </View>
        );

      case 5:
        return (
          <QuickReplyChips
            options={COUNTRIES.map((c) => `${c.flag} ${c.label}`)}
            selected={
              country
                ? [
                    `${COUNTRIES.find((c) => c.value === country)?.flag ?? ''} ${COUNTRIES.find((c) => c.value === country)?.label ?? ''}`,
                  ]
                : []
            }
            onToggle={(label) => {
              const found = COUNTRIES.find((c) => `${c.flag} ${c.label}` === label);
              if (found) handleCountrySelect(found.value);
            }}
            singleSelect
            delay={200}
          />
        );

      case 6:
        if (showTwitterInput) {
          return (
            <Animated.View entering={FadeInUp.duration(300).springify()} style={styles.inputArea}>
              <View style={styles.nameInputRow}>
                <TextInput
                  ref={twitterInputRef}
                  style={styles.nameInput}
                  placeholder="Ej: usuario123"
                  placeholderTextColor={colors.textTertiary}
                  value={twitterUsername}
                  onChangeText={setTwitterUsername}
                  maxLength={50}
                  autoCapitalize="none"
                  autoCorrect={false}
                  selectionColor={colors.primary}
                  onSubmitEditing={handleTwitterUsernameSubmit}
                  returnKeyType="send"
                  editable={!isSubmitting}
                  accessibilityLabel="Usuario de X"
                />
                <Pressable
                  onPress={handleTwitterUsernameSubmit}
                  disabled={!twitterUsername.trim() || isSubmitting}
                  style={({ pressed }) => [
                    styles.sendButton,
                    (!twitterUsername.trim() || isSubmitting) && styles.sendButtonDisabled,
                    pressed && styles.sendButtonPressed,
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel="Conectar cuenta de X"
                >
                  <Text
                    variant="label"
                    color={twitterUsername.trim() ? colors.textInverse : colors.textTertiary}
                  >
                    →
                  </Text>
                </Pressable>
              </View>
            </Animated.View>
          );
        }

        return (
          <Animated.View entering={FadeInUp.duration(300)} style={styles.twitterChoiceContainer}>
            <Button
              title="Conectar mi cuenta de X"
              onPress={handleTwitterConnect}
              fullWidth
              size="md"
            />
            <Pressable
              onPress={handleTwitterSkip}
              style={styles.skipButton}
              accessibilityRole="button"
              accessibilityLabel="Omitir conexión de X"
            >
              <Text variant="body" color={colors.textTertiary}>
                Omitir por ahora
              </Text>
            </Pressable>
          </Animated.View>
        );

      default:
        return null;
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 20 : 0}
    >
      <View style={styles.header}>
        <ProgressBar progress={(step + 1) / TOTAL_STEPS} style={styles.progressBar} />
        <View style={styles.headerRow}>
          <View style={styles.headerAvatarRow}>
            <AvatarFace size={24} state={isSubmitting ? 'thinking' : 'idle'} />
            <Text variant="label" color={colors.textPrimary} style={styles.headerTitle}>
              {avatarName.trim() || 'Tu avatar'}
            </Text>
          </View>
          <Text variant="caption" color={colors.textTertiary}>
            {step + 1} / {TOTAL_STEPS}
          </Text>
        </View>
      </View>

      <FlatList
        ref={flatListRef}
        data={messages}
        renderItem={renderMessage}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.messagesList}
        showsVerticalScrollIndicator={false}
        onContentSizeChange={() => {
          flatListRef.current?.scrollToEnd({ animated: true });
        }}
      />

      <View style={styles.controlsArea}>{renderStepControls()}</View>
    </KeyboardAvoidingView>
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
  headerAvatarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  headerTitle: { marginLeft: spacing.xxs },
  messagesList: { paddingVertical: spacing.sm },
  controlsArea: {
    borderTopWidth: borders.width.thin,
    borderTopColor: colors.border,
    paddingVertical: spacing.md,
    paddingBottom: spacing.lg,
  },
  inputArea: { paddingHorizontal: spacing.md },
  nameInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  nameInput: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: borders.radius.md,
    borderWidth: borders.width.thin,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    fontSize: typography.sizes.md,
    fontFamily: typography.fontFamilies.body,
    color: colors.textPrimary,
    minHeight: 48,
  },
  sendButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: { backgroundColor: colors.elevated },
  sendButtonPressed: { opacity: 0.8 },
  confirmContainer: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  slidersContainer: { paddingHorizontal: spacing.md },
  twitterChoiceContainer: {
    paddingHorizontal: spacing.md,
    gap: spacing.sm,
  },
  skipButton: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
});
