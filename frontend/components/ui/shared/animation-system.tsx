import { keyframes } from "@emotion/react";

export const fadeIn = keyframes`
  from { opacity: 0; }
  to { opacity: 1; }
`;

export const slideUp = keyframes`
  from { transform: translateY(10px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
`;

export const scaleIn = keyframes`
  from { transform: scale(0.95); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
`;

export const orbit = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`;

export const animations = {
  fadeIn: `1s ease-out 0s 1 ${fadeIn}`,
  slideUp: `0.5s ease-out 0s 1 ${slideUp}`,
  scaleIn: `0.3s ease-out 0s 1 ${scaleIn}`,
  orbit: `20s linear infinite ${orbit}`,
};
