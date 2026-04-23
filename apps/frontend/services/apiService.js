import AsyncStorage from '@react-native-async-storage/async-storage';
import Constants from 'expo-constants';
import platformConfig from '../utils/platformConfig';

// Get configuration from app.config.js
const config = Constants.expoConfig?.extra || {};
const BASE_URL = platformConfig.getBaseUrl();
const API_TIMEOUT = parseInt(config.API_TIMEOUT) || 10000;
const DEBUG = config.DEBUG === 'true' || config.DEBUG === true;

class ApiService {
  constructor() {
    this.logoutCallback = null;
  }

  setLogoutCallback(callback) {
    this.logoutCallback = callback;
  }

  async getAuthHeaders(isMultipart = false) {
    const token = await AsyncStorage.getItem('token');
    const headers = {
      'Authorization': token ? `Bearer ${token}` : '',
    };

    if (!isMultipart) {
      headers['Content-Type'] = 'application/json';
    }

    return headers;
  }

  async request(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    const isMultipart = options.body instanceof FormData;
    const headers = await this.getAuthHeaders(isMultipart);

    const config = {
      headers,
      ...options,
    };

    // Add timeout to the request
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

    config.signal = controller.signal;

    try {
      if (DEBUG) {
        console.log(`[API] ${options.method || 'GET'} ${url}`);
      }

      const response = await fetch(url, config);
      clearTimeout(timeoutId);

      const data = await response.json();

      if (!response.ok) {
        // Check for authentication errors (401 or invalid token message)
        if (response.status === 401 ||
            (data.error && typeof data.error === 'string' &&
             (data.error.toLowerCase().includes('invalid token') ||
              data.error.toLowerCase().includes('unauthorized')))) {
          console.log('[API] Authentication error detected, triggering logout');

          // Trigger logout callback if set
          if (this.logoutCallback) {
            this.logoutCallback();
          }

          throw new Error('Token inválido. Por favor, inicie sesión nuevamente.');
        }

        throw new Error(data.error || `HTTP error! status: ${response.status}`);
      }

      if (DEBUG) {
        console.log(`[API] Success: ${endpoint}`);
      }

      return { success: true, data };
    } catch (error) {
      clearTimeout(timeoutId);

      if (error.name === 'AbortError') {
        console.error(`API request timeout for ${endpoint} (${API_TIMEOUT}ms)`);
        return { success: false, error: 'Request timeout' };
      }

      console.error(`API request failed for ${endpoint}:`, error);
      return { success: false, error: error.message };
    }
  }

  // User endpoints
  async getCurrentUser() {
    return this.request('/user');
  }
}

export default new ApiService();
