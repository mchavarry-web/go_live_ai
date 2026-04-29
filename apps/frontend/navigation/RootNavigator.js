import React from 'react';
import { View } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { useAuth } from '../contexts/AuthContext';
import { LoadingSpinner } from '../components/ui';
import AuthNavigator from './AuthNavigator';
import OnboardingNavigator from './OnboardingNavigator';
import MainTabs from './MainTabs';
import RecordingBar from '../components/audio/RecordingBar';
import { colors } from '../theme';

const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    background: colors.background,
    card: colors.surface,
    text: colors.textPrimary,
    border: colors.border,
    primary: colors.primary,
    notification: colors.primary,
  },
};

export default function RootNavigator() {
  const { isAuthenticated, loading, user } = useAuth();

  if (loading) return <LoadingSpinner fullscreen />;

  const onboardingDone = !!user?.onboarding_completed_at;

  // The RecordingBar floats above the tab navigator, so it must live
  // inside NavigationContainer (it calls useNavigation()). It only renders
  // for authenticated users that finished onboarding — i.e. when MainTabs
  // is the active stack.
  return (
    <NavigationContainer theme={navTheme}>
      <View style={{ flex: 1 }}>
        {!isAuthenticated ? (
          <AuthNavigator />
        ) : !onboardingDone ? (
          <OnboardingNavigator />
        ) : (
          <>
            <MainTabs />
            <RecordingBar />
          </>
        )}
      </View>
    </NavigationContainer>
  );
}
