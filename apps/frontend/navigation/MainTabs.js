// 1:1 port of the original tab order in gln-mobile-app, plus a center
// "Grabar" tab that hosts the audio-training control:
//   Inicio | Chat | Grabar | Perfil | Ajustes
//
// "Grabar" is not a real screen — its tabBarButton overrides press to
// dispatch an action against AudioRecordingContext (navigate to voice
// enrollment when idle, start when ready, stop when recording). Its
// icon morphs to reflect the current status. This replaces the old
// floating RecordingBar that overlapped the chat input.
import React from 'react';
import { Pressable, View, StyleSheet } from 'react-native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';

import { colors, borders, spacing } from '../theme';
import HomeScreen from '../screens/HomeScreen';
import ChatStack from './ChatStack';
import ProfileStack from './ProfileStack';
import SettingsStack from './SettingsStack';
import { useAudioRecording } from '../contexts/AudioRecordingContext';
import Text from '../components/ui/Text';

const Tab = createBottomTabNavigator();

const ICONS = {
  HomeTab:     { active: 'home',           inactive: 'home-outline' },
  ChatTab:     { active: 'chatbubbles',    inactive: 'chatbubbles-outline' },
  ProfileTab:  { active: 'person',         inactive: 'person-outline' },
  SettingsTab: { active: 'settings-sharp', inactive: 'settings-outline' },
};

// Placeholder component for the "Grabar" tab. The tab never actually
// navigates here because AudioTabButton intercepts the press, but
// React Navigation requires a component for every Tab.Screen.
const AudioPlaceholder = () => null;

function AudioTabIcon({ size, color }) {
  const { status, pendingUploads } = useAudioRecording();

  const iconName =
    status === 'recording' ? 'stop-circle' :
    status === 'paused'    ? 'pause-circle' :
    status === 'ready'     ? 'mic' :
                             'mic-outline';
  const iconColor =
    status === 'recording' ? colors.error :
    status === 'paused'    ? colors.warning :
    status === 'ready'     ? colors.primary :
                             color;

  return (
    <View>
      <Ionicons name={iconName} size={size} color={iconColor} />
      {pendingUploads > 0 ? (
        <View style={styles.badge}>
          <Text variant="caption" color={colors.textInverse} style={styles.badgeText}>
            {pendingUploads > 9 ? '9+' : String(pendingUploads)}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function AudioTabButton(props) {
  const { status, start, stop } = useAudioRecording();
  const navigation = useNavigation();

  const handlePress = () => {
    if (status === 'recording' || status === 'paused') {
      stop();
      return;
    }
    if (status === 'ready') {
      start();
      return;
    }
    // idle (or anything unexpected): route to enrollment so the user can
    // grant permissions / record start+stop phrases.
    navigation.navigate('ProfileTab', { screen: 'VoiceEnrollment' });
  };

  // We deliberately drop props.onPress (which would dispatch navigation
  // to AudioTab's placeholder screen) and never report selected=true so
  // the previously focused tab stays visually active.
  return (
    <Pressable
      style={props.style}
      onPress={handlePress}
      accessibilityRole="button"
      accessibilityLabel="Grabar entrenamiento por audio"
      accessibilityState={{ selected: false }}
    >
      {props.children}
    </Pressable>
  );
}

export default function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: borders.width.thin,
          height: 85,
          paddingBottom: 28,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        tabBarIcon: ({ color, size, focused }) => {
          const set = ICONS[route.name];
          if (!set) return null;
          const name = focused ? set.active : set.inactive;
          return <Ionicons name={name} size={size} color={color} />;
        },
      })}
    >
      <Tab.Screen name="HomeTab"     component={HomeScreen}    options={{ title: 'Inicio'  }} />
      <Tab.Screen name="ChatTab"     component={ChatStack}     options={{ title: 'Chat'    }} />
      <Tab.Screen
        name="AudioTab"
        component={AudioPlaceholder}
        options={{
          title: 'Grabar',
          tabBarIcon: AudioTabIcon,
          tabBarButton: AudioTabButton,
        }}
      />
      <Tab.Screen name="ProfileTab"  component={ProfileStack}  options={{ title: 'Perfil'  }} />
      <Tab.Screen name="SettingsTab" component={SettingsStack} options={{ title: 'Ajustes' }} />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  badge: {
    position: 'absolute',
    top: -4,
    right: -8,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    paddingHorizontal: 4,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: { fontSize: 10, fontWeight: '700' },
});
