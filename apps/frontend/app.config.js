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
    userInterfaceStyle: 'light',
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
    },
    extra: {
      BASE_URL: process.env.BASE_URL || 'http://localhost:3000/api/v1/mobile',
      WS_URL: process.env.WS_URL || 'ws://localhost:3000/cable',
      NODE_ENV: process.env.NODE_ENV || 'development',
      API_TIMEOUT: process.env.API_TIMEOUT || '15000',
      DEBUG: process.env.DEBUG || 'true',
      eas: {
        projectId: "3c3384ce-957f-481a-a63d-a56e68e76dc1"
      }
    },
  },
};
