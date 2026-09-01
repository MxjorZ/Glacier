// Theme engine (ported from SpotiFLAC's lib/themes.ts).
// Only --primary / --primary-foreground change per accent; base surfaces stay
// consistent. The mode (light/dark) is toggled by the .dark class on <html>.

const baseLight = {
  background: 'oklch(1 0 0)',
  foreground: 'oklch(0.145 0 0)',
  card: 'oklch(1 0 0)',
  'card-foreground': 'oklch(0.145 0 0)',
  popover: 'oklch(1 0 0)',
  'popover-foreground': 'oklch(0.145 0 0)',
  secondary: 'oklch(0.967 0.001 286.375)',
  'secondary-foreground': 'oklch(0.21 0.006 285.885)',
  muted: 'oklch(0.97 0 0)',
  'muted-foreground': 'oklch(0.556 0 0)',
  accent: 'oklch(0.97 0 0)',
  'accent-foreground': 'oklch(0.205 0 0)',
  destructive: 'oklch(0.58 0.22 27)',
  border: 'oklch(0.922 0 0)',
  input: 'oklch(0.922 0 0)',
  ring: 'oklch(0.708 0 0)',
};

const baseDark = {
  background: 'oklch(0.145 0 0)',
  foreground: 'oklch(0.985 0 0)',
  card: 'oklch(0.205 0 0)',
  'card-foreground': 'oklch(0.985 0 0)',
  popover: 'oklch(0.205 0 0)',
  'popover-foreground': 'oklch(0.985 0 0)',
  secondary: 'oklch(0.274 0.006 286.033)',
  'secondary-foreground': 'oklch(0.985 0 0)',
  muted: 'oklch(0.269 0 0)',
  'muted-foreground': 'oklch(0.708 0 0)',
  accent: 'oklch(0.371 0 0)',
  'accent-foreground': 'oklch(0.985 0 0)',
  destructive: 'oklch(0.704 0.191 22.216)',
  border: 'oklch(1 0 0 / 10%)',
  input: 'oklch(1 0 0 / 15%)',
  ring: 'oklch(0.556 0 0)',
};

// AMOLED: true black chrome with barely-elevated surfaces for separation.
const baseAMOLED = {
  background: '#000000',
  foreground: '#e5e5e5',
  card: '#0a0a0a',
  'card-foreground': '#e5e5e5',
  popover: '#0a0a0a',
  'popover-foreground': '#e5e5e5',
  secondary: '#111111',
  'secondary-foreground': '#e5e5e5',
  muted: '#0f0f0f',
  'muted-foreground': '#9ca3af',
  accent: '#161616',
  'accent-foreground': '#e5e5e5',
  destructive: 'oklch(0.704 0.191 22.216)',
  border: 'oklch(1 0 0 / 12%)',
  input: 'oklch(1 0 0 / 15%)',
  ring: 'oklch(0.62 0.13 220)',
};

const primaryColors = {
  cyan: { light: { primary: 'oklch(0.61 0.11 222)', 'primary-foreground': 'oklch(0.98 0.02 201)' }, dark: { primary: 'oklch(0.71 0.13 215)', 'primary-foreground': 'oklch(0.3 0.05 230)' } },
  sky: { light: { primary: 'oklch(0.59 0.14 242)', 'primary-foreground': 'oklch(0.98 0.01 237)' }, dark: { primary: 'oklch(0.68 0.15 237)', 'primary-foreground': 'oklch(0.29 0.06 243)' } },
  teal: { light: { primary: 'oklch(0.6 0.1 185)', 'primary-foreground': 'oklch(0.98 0.01 181)' }, dark: { primary: 'oklch(0.7 0.12 183)', 'primary-foreground': 'oklch(0.28 0.04 193)' } },
  blue: { light: { primary: 'oklch(0.488 0.243 264.376)', 'primary-foreground': 'oklch(0.97 0.014 254.604)' }, dark: { primary: 'oklch(0.42 0.18 266)', 'primary-foreground': 'oklch(0.97 0.014 254.604)' } },
  purple: { light: { primary: 'oklch(0.541 0.281 293.009)', 'primary-foreground': 'oklch(0.969 0.016 293.756)' }, dark: { primary: 'oklch(0.606 0.25 292.717)', 'primary-foreground': 'oklch(0.969 0.016 293.756)' } },
  green: { light: { primary: 'oklch(0.648 0.2 131.684)', 'primary-foreground': 'oklch(0.986 0.031 120.757)' }, dark: { primary: 'oklch(0.7 0.2 155)', 'primary-foreground': 'oklch(0.25 0.05 160)' } },
  orange: { light: { primary: 'oklch(0.7 0.18 60)', 'primary-foreground': 'oklch(0.99 0.02 60)' }, dark: { primary: 'oklch(0.78 0.16 65)', 'primary-foreground': 'oklch(0.3 0.07 45)' } },
  red: { light: { primary: 'oklch(0.63 0.24 25)', 'primary-foreground': 'oklch(0.97 0.015 12)' }, dark: { primary: 'oklch(0.7 0.22 25)', 'primary-foreground': 'oklch(0.97 0.015 12)' } },
  yellow: { light: { primary: 'oklch(0.852 0.199 91.936)', 'primary-foreground': 'oklch(0.421 0.095 57.708)' }, dark: { primary: 'oklch(0.795 0.184 86.047)', 'primary-foreground': 'oklch(0.421 0.095 57.708)' } },
};

export const ACCENTS = Object.keys(primaryColors).sort();

const _clamp = (v) => Math.max(0, Math.min(255, Math.round(Number(v) || 0)));

// Parse a custom accent: '#RGB' / '#RRGGBB' or 'r,g,b'. Returns {r,g,b} or null.
export function parseAccentColor(input) {
  let s = (input || '').trim();
  if (s.startsWith('#')) s = s.slice(1);
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join('');
  if (/^[0-9a-f]{6}$/i.test(s)) {
    return {
      r: parseInt(s.slice(0, 2), 16),
      g: parseInt(s.slice(2, 4), 16),
      b: parseInt(s.slice(4, 6), 16),
    };
  }
  const m = s.match(/^\(?\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)?$/);
  if (m) return { r: _clamp(m[1]), g: _clamp(m[2]), b: _clamp(m[3]) };
  return null;
}

// Turn a custom accent into CSS variables, choosing a readable foreground
// (white or near-black) based on perceived luminance.
export function customAccentVars(input) {
  const c = parseAccentColor(input);
  if (!c) return null;
  const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
  const fg = lum > 0.62 ? '#0a0a0a' : '#ffffff';
  return { '--primary': `rgb(${c.r} ${c.g} ${c.b})`, '--primary-foreground': fg };
}

export function applyTheme(themeName, customColor) {
  const root = document.documentElement;
  const isDark = root.classList.contains('dark');
  const isAmoled = root.classList.contains('amoled');

  if (themeName === 'custom' && customColor) {
    const vars = customAccentVars(customColor);
    if (vars) {
      const base = isAmoled ? baseAMOLED : (isDark ? baseDark : baseLight);
      Object.entries(base).forEach(([key, value]) => root.style.setProperty(`--${key}`, value));
      Object.entries(vars).forEach(([key, value]) => root.style.setProperty(key, value));
      root.setAttribute('data-accent', 'custom');
      return;
    }
  }

  const primary = primaryColors[themeName] || primaryColors.cyan;
  const vars = isAmoled
    ? { ...baseAMOLED, ...primary.dark }
    : isDark
      ? { ...baseDark, ...primary.dark }
      : { ...baseLight, ...primary.light };
  Object.entries(vars).forEach(([key, value]) => root.style.setProperty(`--${key}`, value));
  root.setAttribute('data-accent', themeName || 'cyan');
}

export function applyThemeMode(mode) {
  // mode: 'light' | 'dark' | 'amoled' | 'auto'
  const root = document.documentElement;
  let effective = mode;
  if (mode === 'auto') {
    effective = window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  root.classList.toggle('dark', effective !== 'light');
  root.classList.toggle('amoled', effective === 'amoled');
}

// Apply theme + mode + custom accent from a Glacier settings object.
export function applySettingsThemeLegacy(settings) {
  const theme = settings?.theme || {};
  applyThemeMode(theme.mode || 'dark');
  applyTheme(theme.accent || 'cyan', theme.accent_custom);
}

// Strip the accent-preset data attribute + inline overrides (used when reverting).
export function resetAccentOverrides() {
  const root = document.documentElement;
  root.style.removeProperty('--primary');
  root.style.removeProperty('--primary-foreground');
}

// ---- Stage 4 #16: Enhanced UI animations ---------------------------------
const PRESETS = {
  minimal: { duration: 120, easing: 'ease' },
  modern: { duration: 200, easing: 'ease-out' },
  material: { duration: 300, easing: 'cubic-bezier(0.4, 0, 0.2, 1)' },
  smooth: { duration: 360, easing: 'cubic-bezier(0.25, 1, 0.5, 1)' },
  fast: { duration: 100, easing: 'ease-out' },
  playful: { duration: 280, easing: 'cubic-bezier(0.34, 1.56, 0.64, 1)' },
};

export const ANIM_PRESETS = Object.keys(PRESETS);

// Apply animation preferences from a Glacier settings object to <html>.
export function applyAnimations(settings) {
  const a = settings?.animations || {};
  const preset = PRESETS[a.preset] || PRESETS.modern;
  const duration = a.duration_ms ?? preset.duration;
  const easing = a.easing || preset.easing;
  const root = document.documentElement;
  root.style.setProperty('--anim-duration', `${duration}ms`);
  root.style.setProperty('--anim-easing', easing);
  root.setAttribute('data-anim', a.preset || 'modern');
  root.setAttribute('data-anim-page', a.page_transitions === false ? 'off' : 'on');
  root.setAttribute('data-anim-hover', a.hover === false ? 'off' : 'on');
  root.setAttribute('data-anim-click', a.click === false ? 'off' : 'on');
}

// Apply theme + mode + accent + animations + glass from a Glacier settings object.
export function applySettingsTheme(settings) {
  const theme = settings?.theme || {};
  applyThemeMode(theme.mode || 'dark');
  applyTheme(theme.accent || 'cyan', theme.accent_custom);
  applyAnimations(settings);
  applyGlass(settings?.glass || {});
}

// ---- Liquid glass customization -------------------------------------------
// Maps the persisted glass settings to CSS variables on <html>. All values
// are optional; anything missing falls back to the CSS defaults.
export function applyGlass(g) {
  const root = document.documentElement;
  const glass = g || {};

  if (glass.blur != null) {
    root.style.setProperty('--glass-blur', `${Math.max(0, Math.min(64, Number(glass.blur) || 0))}px`);
  }
  if (glass.alpha != null) {
    const a = Math.max(0, Math.min(1, Number(glass.alpha) || 0));
    root.style.setProperty('--glass-alpha', String(a));
    root.style.setProperty('--glass-alpha-strong', String(Math.min(1, a + 0.16)));
  }
  if (glass.saturation != null) {
    root.style.setProperty('--glass-saturation', `${Math.max(100, Math.min(300, Number(glass.saturation) || 100))}%`);
  }
  if (glass.border != null) {
    root.style.setProperty('--glass-border-alpha', String(Math.max(0, Math.min(0.5, Number(glass.border) || 0))));
  }
  if (glass.radius != null) {
    const r = Math.max(0, Math.min(32, Number(glass.radius) || 0));
    root.style.setProperty('--glass-radius', `${r}px`);
    root.style.setProperty('--radius', `${Math.max(0, r - 4)}px`);
  }
  root.setAttribute('data-glass-ambience', glass.ambience === false ? 'off' : 'on');
  root.setAttribute('data-glass-sheen', glass.sheen === false ? 'off' : 'on');
}

export const GLASS_DEFAULTS = {
  blur: 24,
  alpha: 0.62,
  saturation: 160,
  border: 0.14,
  radius: 16,
  ambience: true,
  sheen: true,
};
