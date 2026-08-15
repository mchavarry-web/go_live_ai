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
import { createBottomTabNavigator, BottomTabBar } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { useNavigation } from '@react-navigation/native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

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

// Wraps React Navigation's default BottomTabBar in a native SafeAreaView
// that owns the bottom inset (DEV-96). Previously we baked
// `Math.max(insets.bottom, 24)` from the JS `useSafeAreaInsets()` hook into
// tabBarStyle's height/paddingBottom. That value is delivered
// asynchronously over the bridge and on some Androids (Samsung, esp. after
// the keyboard resizes the window in `softwareKeyboardLayoutMode:
// 'resize'`) it reads 0/stale, so a 3-button nav bar (~48dp) overlapped
// the bottom 24dp of the bar — exactly where the labels sit. SafeAreaView
// applies the inset as padding synchronously on the native side, so the
// bar always clears the system nav regardless of what the JS hook reports.
// The inner BottomTabBar gets `insets.bottom: 0` so the inset is counted
// exactly once (SafeAreaView pads; the bar itself must not).
function InsetAwareTabBar(props) {
  return (
    <SafeAreaView edges={['bottom']} style={styles.tabBarSafeArea}>
      <BottomTabBar {...props} insets={{ ...props.insets, bottom: 0 }} />
    </SafeAreaView>
  );
}

export default function MainTabs() {
  // Aesthetic floor only: on devices whose bottom inset is < 24dp (Android
  // gesture nav with the hint bar hidden, older devices reporting 0, web)
  // top the bar's own paddingBottom up so labels keep the same breathing
  // room they had with the old `max(insets.bottom, 24)` floor. When the
  // inset is >= 24 (iOS home indicator ~34, Android 3-button ~48, gesture
  // hint ~24) this is 0 and the SafeAreaView wrapper provides all the
  // clearance — identical total height to the previous code, so iOS
  // rendering is unchanged. If the JS inset briefly reads 0 while native
  // knows better, the worst case is transient extra padding — never
  // clipped labels.
  const insets = useSafeAreaInsets();
  const floorTopUp = Math.max(24 - insets.bottom, 0);

  return (
    <Tab.Navigator
      tabBar={(props) => <InsetAwareTabBar {...props} />}
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          borderTopWidth: borders.width.thin,
          height: 56 + floorTopUp,
          paddingBottom: floorTopUp,
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
  // Must match tabBarStyle.backgroundColor so the safe-area padding band
  // below the bar reads as part of the bar, not a stray strip.
  tabBarSafeArea: {
    backgroundColor: colors.surface,
  },
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
