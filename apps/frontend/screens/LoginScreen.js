import React, { useState } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TextInput,
  TouchableOpacity,
  Alert,
  Platform,
  ActivityIndicator
} from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { useAuth } from '../contexts/AuthContext';
import Constants from 'expo-constants';

export default function LoginScreen() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();

  const handleLogin = async () => {
    if (!email || !password) {
      Alert.alert('Error', 'Por favor ingrese email y contraseña');
      return;
    }

    setLoading(true);

    const result = await login(email, password);

    if (result.success) {
      console.log('Login successful');
    } else {
      Alert.alert('Error', result.error);
    }

    setLoading(false);
  };

  return (
    <KeyboardAwareScrollView
      style={styles.container}
      contentContainerStyle={styles.scrollContainer}
      bottomOffset={62}
    >
      <View style={styles.loginContainer}>
          <Text style={styles.title}>GoLive</Text>
          <Text style={styles.subtitle}>Panel Administrativo</Text>

          <View style={styles.inputContainer}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="usuario@ejemplo.com"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              editable={!loading}
            />
          </View>

          <View style={styles.inputContainer}>
            <Text style={styles.label}>Contraseña</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              editable={!loading}
            />
          </View>

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleLogin}
            disabled={loading}
          >
            {loading ? (
              <ActivityIndicator color="white" size="small" />
            ) : (
              <Text style={styles.buttonText}>Iniciar Sesión</Text>
            )}
          </TouchableOpacity>

          <View style={styles.debugInfo}>
            <Text style={styles.debugTitle}>Environment:</Text>
            <Text style={styles.debugText}>BASE_URL: {Constants.expoConfig?.extra?.BASE_URL || 'Not set'}</Text>
            <Text style={styles.debugText}>WS_URL: {Constants.expoConfig?.extra?.WS_URL || 'Not set'}</Text>
            <Text style={styles.debugText}>NODE_ENV: {Constants.expoConfig?.extra?.NODE_ENV || 'Not set'}</Text>
            <Text style={styles.debugText}>API_TIMEOUT: {Constants.expoConfig?.extra?.API_TIMEOUT || 'Not set'}</Text>
            <Text style={styles.debugText}>DEBUG: {Constants.expoConfig?.extra?.DEBUG?.toString() || 'Not set'}</Text>
          </View>
      </View>
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  scrollContainer: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 20,
  },
  loginContainer: {
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 30,
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 5,
    color: '#E65F00',
  },
  subtitle: {
    fontSize: 16,
    textAlign: 'center',
    marginBottom: 30,
    color: '#666',
  },
  inputContainer: {
    marginBottom: 20,
  },
  label: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 5,
    color: '#333',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 15,
    fontSize: 16,
    backgroundColor: '#f9f9f9',
  },
  button: {
    backgroundColor: '#E65F00',
    borderRadius: 8,
    padding: 15,
    alignItems: 'center',
    marginTop: 10,
    minHeight: 48,
    justifyContent: 'center',
  },
  buttonDisabled: {
    backgroundColor: '#ccc',
  },
  buttonText: {
    color: 'white',
    fontSize: 16,
    fontWeight: '600',
  },
  debugInfo: {
    marginTop: 30,
    padding: 15,
    backgroundColor: '#fff4e6',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ffd4a3',
  },
  debugTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
    color: '#E65F00',
  },
  debugText: {
    fontSize: 11,
    color: '#8b4000',
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    marginBottom: 3,
  },
});
