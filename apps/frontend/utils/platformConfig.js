import { Platform } from 'react-native';
import Constants from 'expo-constants';

const getBaseUrl = () => {
  const config = Constants.expoConfig?.extra || {};
  const baseUrl = config.BASE_URL;

  if (!baseUrl) {
    console.warn('BASE_URL not found in config, using fallback');
    return 'http://localhost:3000/api/v1/mobile'; // development fallback
  }

  // Only replace localhost for Android emulator in development
  if (Platform.OS === 'android' && baseUrl.includes('localhost')) {
    return baseUrl.replace('localhost', '10.0.2.2');
  }

  return baseUrl;
};

const getWsUrl = () => {
  const config = Constants.expoConfig?.extra || {};
  const wsUrl = config.WS_URL;

  if (!wsUrl) {
    console.warn('WS_URL not found in config, using fallback');
    return 'ws://localhost:3000/cable'; // development fallback
  }

  // Only replace localhost for Android emulator in development
  if (Platform.OS === 'android' && wsUrl.includes('localhost')) {
    return wsUrl.replace('localhost', '10.0.2.2');
  }

  return wsUrl;
};

export default {
  getBaseUrl,
  getWsUrl,
};
