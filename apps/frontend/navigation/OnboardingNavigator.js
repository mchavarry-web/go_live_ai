// Conversational onboarding is the primary flow: it walks the user through
// avatar name → age → interests → personality → values → country → Twitter,
// then routes to the AvatarCreated celebration screen which refreshes the
// user (flipping onboarding_completed_at) and the RootNavigator picks up
// MainTabs on its next render.
//
// QuestionsScreen is the alternate card-based wizard, kept for parity.
import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import ConversationalOnboardingScreen from '../screens/onboarding/ConversationalOnboardingScreen';
import QuestionsScreen from '../screens/onboarding/QuestionsScreen';
import AvatarCreatedScreen from '../screens/onboarding/AvatarCreatedScreen';

const Stack = createNativeStackNavigator();

export default function OnboardingNavigator() {
  return (
    <Stack.Navigator
      screenOptions={{ headerShown: false, animation: 'fade' }}
      initialRouteName="ConversationalOnboarding"
    >
      <Stack.Screen
        name="ConversationalOnboarding"
        component={ConversationalOnboardingScreen}
      />
      <Stack.Screen name="Questions" component={QuestionsScreen} />
      <Stack.Screen name="AvatarCreated" component={AvatarCreatedScreen} />
    </Stack.Navigator>
  );
}
