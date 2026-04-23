import Constants from 'expo-constants';

/**
 * Environment utility for accessing configuration values
 */
class Environment {
  constructor() {
    this.config = Constants.expoConfig?.extra || {};
  }

  /**
   * Get the base URL for API requests
   */
  getBaseUrl() {
    return this.config.BASE_URL || 'http://localhost:3000/api/v1/mobile';
  }

  /**
   * Get the WebSocket URL
   */
  getWsUrl() {
    return this.config.WS_URL || 'ws://localhost:3000/cable';
  }

  /**
   * Get the current environment name
   */
  getEnvironment() {
    return this.config.NODE_ENV || 'development';
  }

  /**
   * Get API timeout in milliseconds
   */
  getApiTimeout() {
    return parseInt(this.config.API_TIMEOUT) || 10000;
  }

  /**
   * Check if debug mode is enabled
   */
  isDebugEnabled() {
    return this.config.DEBUG === 'true' || this.config.DEBUG === true;
  }

  /**
   * Check if we're in development environment
   */
  isDevelopment() {
    return this.getEnvironment() === 'development';
  }

  /**
   * Check if we're in staging environment
   */
  isStaging() {
    return this.getEnvironment() === 'staging';
  }

  /**
   * Check if we're in production environment
   */
  isProduction() {
    return this.getEnvironment() === 'production';
  }

  /**
   * Get all configuration values
   */
  getAllConfig() {
    return {
      baseUrl: this.getBaseUrl(),
      wsUrl: this.getWsUrl(),
      environment: this.getEnvironment(),
      apiTimeout: this.getApiTimeout(),
      debug: this.isDebugEnabled(),
    };
  }

  /**
   * Log current environment configuration (only in debug mode)
   */
  logConfig() {
    if (this.isDebugEnabled()) {
      console.log('[Environment] Current configuration:', this.getAllConfig());
    }
  }
}

export default new Environment();
