// 1:1 port of gln-mobile-app/src/components/avatar/AvatarFace.tsx.
// Reanimated-driven orb avatar with state animations:
//   idle      — slow glow pulse + occasional blink
//   thinking  — dual eye pulse, faster glow
//   talking   — animated mouth, peak glow
//   happy     — wider mouth, peak glow
//
// `appearance` shape from the Avatar model (Rails `avatar.appearance` jsonb)
// is mapped at the call site:
//   { color, eyes, glow }
// `state` is set by the parent based on chat/avatar context.
import React, { memo, useEffect, useMemo } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  withDelay,
  Easing,
  cancelAnimation,
  interpolate,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, RadialGradient, Stop } from 'react-native-svg';

import { colors } from '../../theme';

const AnimatedView = Animated.View;

const GLOW_MULTIPLIERS = {
  low: { base: 0.12, peak: 0.25 },
  medium: { base: 0.2, peak: 0.5 },
  high: { base: 0.35, peak: 0.7 },
};

function renderEyeShape(eyeStyle, eyeSize) {
  switch (eyeStyle) {
    case 'square':
      return { width: eyeSize, height: eyeSize, borderRadius: eyeSize * 0.25 };
    case 'line':
      return { width: eyeSize * 1.6, height: eyeSize * 0.4, borderRadius: eyeSize * 0.2 };
    case 'dots':
      return { width: eyeSize * 0.6, height: eyeSize * 0.6, borderRadius: eyeSize * 0.3 };
    case 'circle':
    default:
      return { width: eyeSize, height: eyeSize, borderRadius: eyeSize / 2 };
  }
}

function AvatarFaceComponent({
  size = 36,
  state = 'idle',
  color,
  primaryColor,
  eyeStyle = 'circle',
  eyes,
  glowIntensity = 'medium',
  glow,
}) {
  // Accept both the original prop names (primaryColor/eyeStyle/glowIntensity)
  // and the legacy avatar-jsonb names used in the rest of the app
  // (color/eyes/glow), so callers don't have to translate.
  const avatarColor = primaryColor ?? color ?? colors.primary;
  const resolvedEyeStyle = eyes ?? eyeStyle;
  const resolvedGlowIntensity =
    glow === false
      ? 'low'
      : typeof glow === 'string'
        ? glow
        : (glowIntensity ?? 'medium');
  const glowMultiplier = GLOW_MULTIPLIERS[resolvedGlowIntensity] || GLOW_MULTIPLIERS.medium;

  const pulseAnim = useSharedValue(0);
  const blinkAnim = useSharedValue(1);
  const mouthAnim = useSharedValue(0);
  const glowAnim = useSharedValue(glowMultiplier.base);

  useEffect(() => {
    blinkAnim.value = withRepeat(
      withSequence(
        withDelay(2500, withTiming(0.1, { duration: 80, easing: Easing.ease })),
        withTiming(1, { duration: 100, easing: Easing.ease }),
      ),
      -1,
      false,
    );
    return () => {
      cancelAnimation(blinkAnim);
    };
  }, [blinkAnim]);

  useEffect(() => {
    cancelAnimation(pulseAnim);
    cancelAnimation(mouthAnim);
    cancelAnimation(glowAnim);

    const gBase = glowMultiplier.base;
    const gPeak = glowMultiplier.peak;

    switch (state) {
      case 'thinking':
        pulseAnim.value = withRepeat(
          withSequence(
            withTiming(1, { duration: 600, easing: Easing.inOut(Easing.ease) }),
            withTiming(0, { duration: 600, easing: Easing.inOut(Easing.ease) }),
          ),
          -1,
          false,
        );
        glowAnim.value = withRepeat(
          withSequence(
            withTiming(gPeak, { duration: 800, easing: Easing.inOut(Easing.ease) }),
            withTiming(gBase, { duration: 800, easing: Easing.inOut(Easing.ease) }),
          ),
          -1,
          false,
        );
        mouthAnim.value = withTiming(0.3, { duration: 300 });
        break;

      case 'talking':
        mouthAnim.value = withRepeat(
          withSequence(
            withTiming(1, { duration: 200, easing: Easing.inOut(Easing.ease) }),
            withTiming(0.3, { duration: 180, easing: Easing.inOut(Easing.ease) }),
          ),
          -1,
          false,
        );
        glowAnim.value = withTiming(gPeak * 0.8, { duration: 300 });
        pulseAnim.value = 0;
        break;

      case 'happy':
        mouthAnim.value = withTiming(0.8, { duration: 400 });
        glowAnim.value = withTiming(gPeak, { duration: 400 });
        pulseAnim.value = 0;
        break;

      case 'idle':
      default:
        pulseAnim.value = withTiming(0, { duration: 300 });
        mouthAnim.value = withTiming(0, { duration: 300 });
        glowAnim.value = withRepeat(
          withSequence(
            withTiming(gBase + 0.15, { duration: 2000, easing: Easing.inOut(Easing.ease) }),
            withTiming(gBase, { duration: 2000, easing: Easing.inOut(Easing.ease) }),
          ),
          -1,
          false,
        );
        break;
    }

    return () => {
      cancelAnimation(pulseAnim);
      cancelAnimation(mouthAnim);
      cancelAnimation(glowAnim);
    };
  }, [state, pulseAnim, mouthAnim, glowAnim, glowMultiplier]);

  const glowStyle = useAnimatedStyle(() => ({
    opacity: glowAnim.value,
    transform: [{ scale: interpolate(glowAnim.value, [0.1, 0.7], [1, 1.15]) }],
  }));

  const leftEyeStyle = useAnimatedStyle(() => ({
    transform: [
      { scaleY: blinkAnim.value },
      { scale: interpolate(pulseAnim.value, [0, 1], [1, 1.3]) },
    ],
    opacity: interpolate(pulseAnim.value, [0, 1], [1, 0.6]),
  }));

  const rightEyeStyle = useAnimatedStyle(() => ({
    transform: [
      { scaleY: blinkAnim.value },
      { scale: interpolate(pulseAnim.value, [0, 1], [1, 1.3]) },
    ],
    opacity: interpolate(pulseAnim.value, [0, 1], [1, 0.6]),
  }));

  const mouthStyle = useAnimatedStyle(() => ({
    transform: [{ scaleY: interpolate(mouthAnim.value, [0, 1], [0.6, 1.4]) }],
    opacity: interpolate(mouthAnim.value, [0, 0.3, 1], [0.5, 0.8, 1]),
  }));

  const eyeSize = Math.max(size * 0.1, 3);
  const eyeOffsetX = size * 0.18;
  const eyeOffsetY = size * 0.08;
  const mouthWidth = size * 0.22;
  const mouthHeight = size * 0.06;

  const eyeShapeStyle = useMemo(
    () => renderEyeShape(resolvedEyeStyle, eyeSize),
    [resolvedEyeStyle, eyeSize],
  );

  const isDots = resolvedEyeStyle === 'dots';
  const dotGap = eyeSize * 0.5;

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      <AnimatedView
        style={[
          styles.glow,
          {
            width: size * 1.4,
            height: size * 1.4,
            borderRadius: size * 0.7,
            backgroundColor: avatarColor,
          },
          glowStyle,
        ]}
      />

      <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <Defs>
          <RadialGradient id="orbGrad" cx="40%" cy="35%" r="60%">
            <Stop offset="0%" stopColor={colors.elevated} stopOpacity="1" />
            <Stop offset="70%" stopColor={colors.surface} stopOpacity="1" />
            <Stop offset="100%" stopColor={colors.background} stopOpacity="1" />
          </RadialGradient>
        </Defs>
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={size / 2 - 1}
          fill="url(#orbGrad)"
          stroke={avatarColor}
          strokeWidth={1.2}
          strokeOpacity={0.6}
        />
      </Svg>

      <AnimatedView
        style={[
          styles.eye,
          eyeShapeStyle,
          {
            backgroundColor: avatarColor,
            shadowColor: avatarColor,
            left: size / 2 - eyeOffsetX - eyeShapeStyle.width / 2,
            top: size / 2 - eyeOffsetY,
          },
          leftEyeStyle,
        ]}
      />
      {isDots && (
        <AnimatedView
          style={[
            styles.eye,
            eyeShapeStyle,
            {
              backgroundColor: avatarColor,
              shadowColor: avatarColor,
              left: size / 2 - eyeOffsetX - eyeShapeStyle.width / 2 - dotGap,
              top: size / 2 - eyeOffsetY - dotGap * 0.8,
              opacity: 0.5,
            },
            leftEyeStyle,
          ]}
        />
      )}

      <AnimatedView
        style={[
          styles.eye,
          eyeShapeStyle,
          {
            backgroundColor: avatarColor,
            shadowColor: avatarColor,
            left: size / 2 + eyeOffsetX - eyeShapeStyle.width / 2,
            top: size / 2 - eyeOffsetY,
          },
          rightEyeStyle,
        ]}
      />
      {isDots && (
        <AnimatedView
          style={[
            styles.eye,
            eyeShapeStyle,
            {
              backgroundColor: avatarColor,
              shadowColor: avatarColor,
              left: size / 2 + eyeOffsetX - eyeShapeStyle.width / 2 + dotGap,
              top: size / 2 - eyeOffsetY - dotGap * 0.8,
              opacity: 0.5,
            },
            rightEyeStyle,
          ]}
        />
      )}

      <AnimatedView
        style={[
          styles.mouth,
          {
            width: mouthWidth,
            height: mouthHeight,
            borderRadius: mouthHeight / 2,
            left: size / 2 - mouthWidth / 2,
            top: size / 2 + size * 0.15,
            backgroundColor: avatarColor,
            shadowColor: avatarColor,
          },
          mouthStyle,
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  glow: {
    position: 'absolute',
  },
  eye: {
    position: 'absolute',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 4,
    elevation: 4,
  },
  mouth: {
    position: 'absolute',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 3,
    elevation: 3,
  },
});

export default memo(AvatarFaceComponent);
export { AvatarFaceComponent };
