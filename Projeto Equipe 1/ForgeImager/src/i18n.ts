import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { invoke } from '@tauri-apps/api/core';
import { load } from '@tauri-apps/plugin-store';
import { getLanguageFromLocale, getDefaultLanguage } from './config/i18n';

// Load every locale JSON via Vite glob so new languages are picked up automatically
const localeModules = import.meta.glob('./locales/*.json', { eager: true });

// Build the i18next resources map keyed by language code
const resources = Object.entries(localeModules).reduce((acc, [path, module]) => {
  // './locales/en.json' -> 'en'
  const langCode = path.match(/\.\/locales\/(.+)\.json$/)?.[1];
  if (langCode && module) {
    const data = (module as any).default ?? (module as Record<string, unknown>);
    acc[langCode] = { translation: data };
  }
  return acc;
}, {} as Record<string, { translation: Record<string, unknown> }>);

/** Initialize i18n using the saved language, falling back to pt-BR default */
export async function initI18n(): Promise<void> {
  let language = getDefaultLanguage(); // 'pt-BR'
  const isTauri = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__);

  if (!isTauri) {
    const saved = typeof localStorage !== 'undefined' ? localStorage.getItem('forge_setting_language') : null;
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed && parsed !== 'auto') {
          language = parsed;
        }
      } catch {
        if (saved !== 'auto') {
          language = saved;
        }
      }
    }
  } else {
    try {
      const store = await load('settings.json', { autoSave: true, defaults: {} });
      const savedLanguage = await store.get<string>('language');
      if (savedLanguage && savedLanguage !== 'auto') {
        language = savedLanguage;
      }
    } catch {
      language = getDefaultLanguage();
    }
  }

  await i18n
    .use(initReactI18next)
    .init({
      resources,
      lng: language,
      fallbackLng: 'pt-BR',
      interpolation: {
        escapeValue: false, // React already escapes values
      },
      react: {
        useSuspense: false, // Disable suspense for sync initialization
      },
    });
}

/** Change the active language (e.g. 'en', 'it', 'auto') and persist it */
export async function changeLanguage(lang: string): Promise<void> {
  const isTauri = typeof window !== 'undefined' && Boolean((window as any).__TAURI_INTERNALS__);

  if (!isTauri) {
    if (lang === 'auto') {
      try {
        localStorage.removeItem('forge_setting_language');
      } catch {
        // ignore
      }
      const detected = (typeof navigator !== 'undefined' && navigator.language) ? getLanguageFromLocale(navigator.language) : 'en';
      await i18n.changeLanguage(detected);
    } else {
      await i18n.changeLanguage(lang);
      try {
        localStorage.setItem('forge_setting_language', JSON.stringify(lang));
      } catch {
        // ignore
      }
    }
    return;
  }

  const store = await load('settings.json', { autoSave: true, defaults: {} });

  if (lang === 'auto') {
    // Remove saved language to enable auto-detection
    try {
      await store.delete('language');
    } catch (error) {
      console.error('Failed to delete language from storage:', error);
    }

    // Detect system locale and change to it
    try {
      const systemLocale = await invoke<string>('get_system_locale');
      const detectedLang = getLanguageFromLocale(systemLocale);
      await i18n.changeLanguage(detectedLang);
    } catch (localeError) {
      console.warn('Failed to get system locale, using default:', localeError);
      await i18n.changeLanguage('en');
    }
  } else {
    // Change language in i18next
    await i18n.changeLanguage(lang);

    // Persist to storage using Store plugin
    try {
      await store.set('language', lang);
    } catch (error) {
      console.error('Failed to save language to storage:', error);
    }
  }
}

/** Get the current language */
export function getCurrentLanguage(): string {
  return i18n.language;
}

export default i18n;
