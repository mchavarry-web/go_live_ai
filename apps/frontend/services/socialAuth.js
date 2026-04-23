import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Thin wrappers over the three native provider SDKs. Each returns
// `{ provider, token }` where `token` is exactly what Rails expects on the
// matching /api/v1/auth/<provider> endpoint:
//
//   google   → ID token (JWT) → verified via Google JWKS in Rails
//   apple    → identityToken (JWT) → verified via Apple JWKS
//   facebook → access token (opaque) → verified via Graph /me
//
// Web target: providers are typically wired via OmniAuth redirect flows on
// Rails (/users/auth/google_oauth2 etc.) so these helpers short-circuit
// with a redirect instruction instead of calling a native SDK.

// ── Google ─────────────────────────────────────────────────────────────
let googleConfigured = false;
const ensureGoogleConfigured = () => {
  if (googleConfigured) return;
  const { GoogleSignin } = require('@react-native-google-signin/google-signin');
  GoogleSignin.configure({
    webClientId: Constants.expoConfig?.extra?.GOOGLE_WEB_CLIENT_ID,
    iosClientId: Constants.expoConfig?.extra?.GOOGLE_IOS_CLIENT_ID,
    offlineAccess: false,
  });
  googleConfigured = true;
};

export const signInWithGoogle = async () => {
  if (Platform.OS === 'web') {
    // OmniAuth redirect — the caller should open /users/auth/google_oauth2
    // on the Rails host in a new tab and wait for the cookie session.
    return { provider: 'google', webRedirect: '/users/auth/google_oauth2' };
  }
  ensureGoogleConfigured();
  const { GoogleSignin } = require('@react-native-google-signin/google-signin');
  await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
  const userInfo = await GoogleSignin.signIn();
  const tokens = await GoogleSignin.getTokens();
  return { provider: 'google', token: userInfo?.data?.idToken || tokens.idToken };
};

// ── Apple ──────────────────────────────────────────────────────────────
export const signInWithApple = async () => {
  if (Platform.OS === 'web') {
    return { provider: 'apple', webRedirect: '/users/auth/apple' };
  }
  if (Platform.OS !== 'ios') {
    throw new Error('Apple Sign-In only supported on iOS and web');
  }
  const AppleAuthentication = require('expo-apple-authentication');
  const credential = await AppleAuthentication.signInAsync({
    requestedScopes: [
      AppleAuthentication.AppleAuthenticationScope.EMAIL,
      AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
    ],
  });
  return { provider: 'apple', token: credential.identityToken };
};

// ── Facebook ──────────────────────────────────────────────────────────
export const signInWithFacebook = async () => {
  if (Platform.OS === 'web') {
    return { provider: 'facebook', webRedirect: '/users/auth/facebook' };
  }
  const { LoginManager, AccessToken } = require('react-native-fbsdk-next');
  const result = await LoginManager.logInWithPermissions(['public_profile', 'email']);
  if (result.isCancelled) throw new Error('facebook sign-in cancelled');
  const data = await AccessToken.getCurrentAccessToken();
  if (!data) throw new Error('facebook access token missing');
  return { provider: 'facebook', token: data.accessToken };
};

export default { signInWithGoogle, signInWithApple, signInWithFacebook };
