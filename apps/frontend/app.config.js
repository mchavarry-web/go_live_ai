// Load environment variables from .env file for local development
// EAS builds will inject env vars directly from eas.json
if (process.env.EAS_BUILD !== 'true') {
  require('dotenv').config({ override: true });
}

export default {
  expo: {
    name: 'GoLive',
    slug: 'go-live',
    version: '1.0.0',
    orientation: 'portrait',
    userInterfaceStyle: 'dark',
    // First-class platform support: iOS, Android, and web.
    platforms: ['ios', 'android', 'web'],
    ios: {
      supportsTablet: true,
      bundleIdentifier: 'com.golive.app',
    },
    android: {
      package: 'com.golive.app',
      edgeToEdgeEnabled: true,
      softwareKeyboardLayoutMode: 'resize',
    },
    web: {
      bundler: 'metro',
      // Static (SPA) output — Rails serves it as public/web/ on deploy if
      // we ever want a unified host; otherwise ship as a separate Expo web build.
      output: 'static',
      favicon: './assets/favicon.png',
    },
    extra: {
      // Rails API endpoints (single source of truth — no more /mobile namespace).
      API_URL: process.env.API_URL || 'http://localhost:3000/api/v1',
      CABLE_URL: process.env.CABLE_URL || 'ws://localhost:3000/cable',
      NODE_ENV: process.env.NODE_ENV || 'development',
      API_TIMEOUT: process.env.API_TIMEOUT || '15000',
      DEBUG: process.env.DEBUG || 'true',
      eas: {
        projectId: '3c3384ce-957f-481a-a63d-a56e68e76dc1',
      },
    },
  },
};
