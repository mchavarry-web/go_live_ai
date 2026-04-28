import React from 'react';
import { Text as RNText } from 'react-native';
import { colors, typography } from '../../theme';

export default function Text({
  variant = 'body',
  color = 'textPrimary',
  align = 'left',
  weight,
  style,
  children,
  ...rest
}) {
  const baseVariant = typography.variants[variant] || typography.variants.body;
  const resolvedColor = colors[color] || color;
  return (
    <RNText
      {...rest}
      style={[
        baseVariant,
        { color: resolvedColor, textAlign: align },
        weight ? { fontWeight: typography.weights[weight] || weight } : null,
        style,
      ]}
    >
      {children}
    </RNText>
  );
}
