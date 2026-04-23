import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Single source of truth for Rails API + ActionCable URLs.
// Android emulator: localhost → 10.0.2.2 (host-loopback).
// Web (Expo web target): localhost just works.
const config = Constants.expoConfig?.extra || {};

const adjustForPlatform = (url, fallback) => {
  const value = url || fallback;
  if (Platform.OS === 'android' && value.includes('localhost')) {
    return value.replace('localhost', '10.0.2.2');
  }
  return value;
};

const getApiUrl = () =>
  adjustForPlatform(config.API_URL, 'http://localhost:3000/api/v1');

// Back-compat alias for existing callers that imported getBaseUrl.
const getBaseUrl = getApiUrl;

const getCableUrl = () =>
  adjustForPlatform(config.CABLE_URL, 'ws://localhost:3000/cable');

// Back-compat alias.
const getWsUrl = getCableUrl;

export default {
  getApiUrl,
  getBaseUrl,
  getCableUrl,
  getWsUrl,
};
