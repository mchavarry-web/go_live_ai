// Dark-only palette ported 1:1 from gln-mobile-app/src/theme/colors.ts.
// Avoid hardcoding any of these values in screens/components — always import.
const colors = {
  // Backgrounds
  background: '#0A0A0F',
  surface: '#12121A',
  elevated: '#1A1A2E',
  card: '#16162A',

  // Brand / semantic
  primary: '#00D4AA',
  primaryLight: '#00E8BE',
  primaryDark: '#00A88A',
  secondary: '#00B4D8',
  warning: '#FFB800',
  error: '#FF4757',
  success: '#00D4AA',

  // Text
  textPrimary: '#E8E8ED',
  textSecondary: '#A0A0B0',
  textTertiary: '#6B6B80',
  textInverse: '#0A0A0F',

  // Lines & overlays
  border: '#2A2A3E',
  borderLight: '#3A3A4E',
  overlay: 'rgba(0, 0, 0, 0.6)',
  glassBg: 'rgba(26, 26, 46, 0.8)',

  // Per-provider tints (used by social status cards)
  facebook: '#1877F2',
  instagram: '#E4405F',
  twitter: '#1DA1F2',
  spotify: '#1DB954',
};

export default colors;
