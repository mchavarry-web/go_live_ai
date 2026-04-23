import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../contexts/AuthContext';
import ProfileDropdown from './ProfileDropdown';

export default function Header({ onMenuPress, title = 'GoLive' }) {
  const { logout } = useAuth();
  const [dropdownVisible, setDropdownVisible] = useState(false);

  const toggleDropdown = () => {
    setDropdownVisible(!dropdownVisible);
  };

  const handleLogout = () => {
    logout();
  };

  return (
    <View style={styles.header}>
      <TouchableOpacity onPress={onMenuPress} style={styles.menuButton}>
        <Ionicons name="menu" size={24} color="#333" />
      </TouchableOpacity>
      <Text style={styles.headerTitle}>{title}</Text>
      <TouchableOpacity onPress={toggleDropdown} style={styles.profileButton}>
        <Ionicons name="person-circle" size={28} color="#E65F00" />
      </TouchableOpacity>

      <ProfileDropdown
        visible={dropdownVisible}
        onClose={() => setDropdownVisible(false)}
        onLogout={handleLogout}
        position={{ top: 60, right: 10 }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 15,
    paddingVertical: 12,
    backgroundColor: 'white',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  menuButton: {
    padding: 5,
    width: 40,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#E65F00',
    flex: 1,
    textAlign: 'center',
  },
  profileButton: {
    padding: 5,
    width: 40,
    alignItems: 'flex-end',
  },
});
