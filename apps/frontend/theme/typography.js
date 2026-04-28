import { Platform } from 'react-native';

const fontFamilies = Platform.select({
  ios: { display: 'SF Pro Display', body: 'SF Pro Text' },
  android: { display: 'Roboto', body: 'Roboto' },
  default: { display: 'System', body: 'System' },
});

const sizes = { xxxl: 36, xxl: 30, xl: 24, lg: 20, md: 16, sm: 14, xs: 12, xxs: 10 };
const lineHeights = { xxxl: 44, xxl: 38, xl: 32, lg: 28, md: 24, sm: 20, xs: 16, xxs: 14 };
const weights = {
  regular: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
  extrabold: '800',
};

const variants = {
  heading: {
    fontFamily: fontFamilies.display,
    fontSize: sizes.xxl,
    lineHeight: lineHeights.xxl,
    fontWeight: weights.bold,
  },
  subheading: {
    fontFamily: fontFamilies.display,
    fontSize: sizes.xl,
    lineHeight: lineHeights.xl,
    fontWeight: weights.semibold,
  },
  title: {
    fontFamily: fontFamilies.display,
    fontSize: sizes.lg,
    lineHeight: lineHeights.lg,
    fontWeight: weights.semibold,
  },
  body: {
    fontFamily: fontFamilies.body,
    fontSize: sizes.md,
    lineHeight: lineHeights.md,
    fontWeight: weights.regular,
  },
  caption: {
    fontFamily: fontFamilies.body,
    fontSize: sizes.xs,
    lineHeight: lineHeights.xs,
    fontWeight: weights.regular,
  },
  label: {
    fontFamily: fontFamilies.body,
    fontSize: sizes.sm,
    lineHeight: lineHeights.sm,
    fontWeight: weights.medium,
  },
};

export default { fontFamilies, sizes, lineHeights, weights, variants };
