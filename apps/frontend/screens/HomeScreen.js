import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import Header from '../components/Header';
import CustomDrawer from '../components/CustomDrawer';
import DrawerContent from '../components/DrawerContent';

export default function HomeScreen() {
  const { user } = useAuth();
  const [drawerVisible, setDrawerVisible] = useState(false);

  const openDrawer = () => setDrawerVisible(true);
  const closeDrawer = () => setDrawerVisible(false);

  return (
    <SafeAreaView style={styles.safeArea}>
      <Header onMenuPress={openDrawer} title="Inicio" />
      <View style={styles.container}>
      <Text style={styles.title}>Bienvenido a GoLive</Text>
      <Text style={styles.subtitle}>¡Hola, {user?.first_name || user?.email}!</Text>

      <View style={styles.infoContainer}>
        <Text style={styles.label}>Email:</Text>
        <Text style={styles.value}>{user?.email}</Text>

        <Text style={styles.label}>Nombre:</Text>
        <Text style={styles.value}>{user?.first_name} {user?.last_name}</Text>

        {user?.roles && user.roles.length > 0 && (
          <>
            <Text style={styles.label}>Roles:</Text>
            <Text style={styles.value}>{user.roles.join(', ')}</Text>
          </>
        )}
      </View>
      </View>

      <CustomDrawer visible={drawerVisible} onClose={closeDrawer}>
        <DrawerContent onClose={closeDrawer} />
      </CustomDrawer>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: 'white',
  },
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
    padding: 20,
    justifyContent: 'center',
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    textAlign: 'center',
    marginBottom: 10,
    color: '#E65F00',
  },
  subtitle: {
    fontSize: 18,
    textAlign: 'center',
    marginBottom: 30,
    color: '#666',
  },
  infoContainer: {
    backgroundColor: 'white',
    borderRadius: 10,
    padding: 20,
    marginBottom: 30,
    shadowColor: '#000',
    shadowOffset: {
      width: 0,
      height: 2,
    },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#666',
    marginTop: 10,
  },
  value: {
    fontSize: 16,
    color: '#333',
    marginBottom: 5,
  },
});
