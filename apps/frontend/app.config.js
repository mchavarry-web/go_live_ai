// Load environment variables from .env file for local development
// EAS builds will inject env vars directly from eas.json
if (process.env.EAS_BUILD !== 'true') {
  require('dotenv').config({ override: true });
}

export default {
  expo: {
    name: 'Go Live',
    slug: 'go-live',
    version: '1.0.0',
    orientation: 'portrait',
    userInterfaceStyle: 'dark',
    // First-class platform support: iOS, Android, and web.
    platforms: ['ios', 'android', 'web'],
    // Top-level icon is the iOS source-of-truth (and Android fallback when
    // adaptive-icon is not configured). 1024×1024 PNG, no transparency —
    // EAS resizes for every platform target on build.
    icon: './assets/icon.png',
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'com.devtechperu.golive',
      icon: './assets/icon.png',
      infoPlist: {
        ITSAppUsesNonExemptEncryption: false,
        NSMicrophoneUsageDescription:
          'Tu avatar aprende de tus conversaciones cuando activas el entrenamiento por audio.',
      },
    },
    android: {
      package: 'com.devtechperu.golive',
      edgeToEdgeEnabled: true,
      softwareKeyboardLayoutMode: 'resize',
      permissions: ['RECORD_AUDIO'],
      // Adaptive icon: the foreground sits on top of `backgroundColor`.
      // We re-use the full square logo as the foreground; on launchers
      // that mask to circle/squircle the bleed is cropped.
      adaptiveIcon: {
        foregroundImage: './assets/adaptive-icon.png',
        backgroundColor: '#0A0A0F',
      },
    },
    plugins: [
      // expo-audio registers an iOS NSMicrophoneUsageDescription via its
      // config plugin and the corresponding Android permission entries.
      'expo-audio',
      // SDK 54 edge-to-edge bridge — required for android.edgeToEdgeEnabled
      // so react-native-safe-area-context picks up status / nav bar insets.
      // Without this, SafeAreaView under-pads at top and the tab bar
      // ignores the Android nav bar at bottom.
      'react-native-edge-to-edge',
      // Splash screen: image rendered centered on the dark background that
      // matches the app theme (#0A0A0F) so the brand-coloured logo pops.
      [
        'expo-splash-screen',
        {
          image: './assets/splash-icon.png',
          backgroundColor: '#0A0A0F',
          imageWidth: 240,
        },
      ],
    ],
    web: {
      bundler: 'metro',
      // SPA output — this project uses React Navigation, not expo-router.
      // 'static' / 'server' would require expo-router; 'single' ships a
      // classic single-page bundle that Rails (or any static host) can serve.
      output: 'single',
      favicon: './assets/favicon.png',
    },
    extra: {
      // Rails API endpoints (single source of truth — no more /mobile namespace).
      API_URL: process.env.API_URL || 'http://localhost:3000/api/v1',
      CABLE_URL: process.env.CABLE_URL || 'ws://localhost:3000/cable',
      NODE_ENV: process.env.NODE_ENV || 'development',
      API_TIMEOUT: process.env.API_TIMEOUT || '15000',
      DEBUG: process.env.DEBUG || 'true',
      // Social SDK wiring — set in env.* files; blank at build time is fine.
      GOOGLE_WEB_CLIENT_ID: process.env.GOOGLE_WEB_CLIENT_ID || '',
      GOOGLE_IOS_CLIENT_ID: process.env.GOOGLE_IOS_CLIENT_ID || '',
      FACEBOOK_APP_ID: process.env.FACEBOOK_APP_ID || '',
      eas: {
        projectId: '61396ed0-1dde-4553-9f30-d838dd68c28a',
      },
    },
  },
};
