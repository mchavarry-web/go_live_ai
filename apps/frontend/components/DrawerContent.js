import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';
import { useAuth } from '../contexts/AuthContext';

export default function DrawerContent({ onClose }) {
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    if (onClose) onClose();
  };

  const appVersion = Constants.expoConfig?.version || '1.0.0';

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <View style={styles.userInfo}>
          <Ionicons name="person-circle" size={48} color="#E65F00" />
          <Text style={styles.userName}>{user?.first_name || user?.email}</Text>
          {user?.roles && user.roles.length > 0 && (
            <Text style={styles.userRole}>{user.roles.join(', ')}</Text>
          )}
        </View>
      </View>

      <View style={styles.menu}>
        <View style={styles.divider} />

        <TouchableOpacity
          style={styles.menuItem}
          onPress={handleLogout}
        >
          <Ionicons name="log-out" size={24} color="#FF6B6B" />
          <Text style={[styles.menuText, styles.logoutText]}>Cerrar Sesión</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.footer}>
        <Text style={styles.appName}>GoLive</Text>
        <Text style={styles.version}>v{appVersion}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: 'white',
  },
  header: {
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  userInfo: {
    alignItems: 'center',
  },
  userName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
    marginTop: 10,
  },
  userRole: {
    fontSize: 14,
    color: '#666',
    marginTop: 2,
  },
  menu: {
    flex: 1,
    paddingTop: 20,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 15,
  },
  menuText: {
    fontSize: 16,
    color: '#333',
    marginLeft: 15,
  },
  logoutText: {
    color: '#FF6B6B',
  },
  divider: {
    height: 1,
    backgroundColor: '#e0e0e0',
    marginVertical: 20,
    marginHorizontal: 20,
  },
  footer: {
    padding: 20,
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#e0e0e0',
  },
  appName: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#E65F00',
  },
  version: {
    fontSize: 12,
    color: '#666',
    marginTop: 5,
  },
});
