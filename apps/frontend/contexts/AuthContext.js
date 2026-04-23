import React, { createContext, useState, useContext, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import apiService from '../services/apiService';

// Rails JWT shape: { access_token, refresh_token, expires_at, user }.
// Tokens live in AsyncStorage under 'access_token' + 'refresh_token'.
const AuthContext = createContext({});

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiService.setLogoutCallback(() => {
      console.log('[AuthContext] Auto-logout triggered by invalid token');
      logout();
    });
    loadStoredAuth();
  }, []);

  const loadStoredAuth = async () => {
    try {
      const storedToken = await AsyncStorage.getItem('access_token');
      const storedUser = await AsyncStorage.getItem('user');
      if (storedToken && storedUser) {
        setAccessToken(storedToken);
        setUser(JSON.parse(storedUser));
      }
    } catch (error) {
      console.error('Error loading stored auth:', error);
    } finally {
      setLoading(false);
    }
  };

  const persistAuth = async ({ access_token, refresh_token, user: userData }) => {
    await AsyncStorage.setItem('access_token', access_token);
    if (refresh_token) await AsyncStorage.setItem('refresh_token', refresh_token);
    await AsyncStorage.setItem('user', JSON.stringify(userData));
    setAccessToken(access_token);
    setUser(userData);
  };

  const login = async (email, password) => {
    const { success, data, error } = await apiService.signIn(email.trim(), password);
    if (success) {
      await persistAuth(data);
      return { success: true };
    }
    return { success: false, error: error || 'Error al iniciar sesión' };
  };

  const register = async ({ email, password, firstName, lastName }) => {
    const { success, data, error } = await apiService.signUp({
      email: email.trim(),
      password,
      firstName,
      lastName,
    });
    if (success) {
      await persistAuth(data);
      return { success: true };
    }
    return { success: false, error: error || 'Error al registrar usuario' };
  };

  // Native provider SDKs (client-side) → Rails verifies the token and issues a JWT.
  const loginWithProvider = async (provider, providerToken) => {
    let res;
    if (provider === 'google') res = await apiService.signInWithGoogle(providerToken);
    else if (provider === 'apple') res = await apiService.signInWithApple(providerToken);
    else if (provider === 'facebook') res = await apiService.signInWithFacebook(providerToken);
    else return { success: false, error: `unknown provider: ${provider}` };

    if (res.success) {
      await persistAuth(res.data);
      return { success: true };
    }
    return { success: false, error: res.error };
  };

  const logout = async () => {
    try {
      await AsyncStorage.multiRemove(['access_token', 'refresh_token', 'user']);
      setAccessToken(null);
      setUser(null);
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const refreshUserData = async () => {
    const { success, data } = await apiService.me();
    if (success) {
      const updatedUser = data.user || data;
      await AsyncStorage.setItem('user', JSON.stringify(updatedUser));
      setUser(updatedUser);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        token: accessToken, // legacy alias
        loading,
        login,
        register,
        loginWithProvider,
        logout,
        refreshUserData,
        isAuthenticated: !!user && !!accessToken,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
