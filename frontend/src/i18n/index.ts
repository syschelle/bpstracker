import enLocale from './locales/en.json';

export type TranslationKey = keyof typeof enLocale.translations;
export type Language = string;

export type LocaleMeta = {
  code: string;
  name: string;
  nativeName: string;
  shortName?: string;
  locale: string;
  helpFile: string;
  order?: number;
};

type LocaleFile = {
  meta: LocaleMeta;
  translations: Record<TranslationKey, string>;
};

const localeModules = import.meta.glob('./locales/*.json', {
  eager: true,
  import: 'default'
}) as Record<string, LocaleFile>;

const localeFiles = Object.entries(localeModules)
  .map(([path, locale]) => {
    const fileCode = path.split('/').pop()?.replace(/\.json$/, '') || '';
    const code = String(locale.meta.code || '').trim().toLowerCase();
    return {
      ...locale,
      meta: {
        ...locale.meta,
        code,
        shortName: locale.meta.shortName || code.toUpperCase(),
        order: locale.meta.order ?? 999,
      },
      _fileCode: fileCode,
    };
  })
  .filter(locale => locale.meta.code && locale._fileCode === locale.meta.code)
  .sort((a, b) => (a.meta.order ?? 999) - (b.meta.order ?? 999) || a.meta.nativeName.localeCompare(b.meta.nativeName));

export const availableLanguages: LocaleMeta[] = localeFiles.map(locale => locale.meta);

export const DEFAULT_LANGUAGE: Language = availableLanguages.some(language => language.code === 'en')
  ? 'en'
  : availableLanguages[0]?.code || 'en';

export const translations = Object.fromEntries(
  localeFiles.map(locale => [locale.meta.code, locale.translations])
) as Record<string, Record<TranslationKey, string>>;

const localeMetaByCode = Object.fromEntries(
  availableLanguages.map(locale => [locale.code, locale])
) as Record<string, LocaleMeta>;

export function isSupportedLanguage(value: string | null | undefined): value is Language {
  if (!value) return false;
  return Object.prototype.hasOwnProperty.call(translations, value.trim().toLowerCase());
}

export function normalizeLanguage(value: string | null | undefined, fallback: Language = DEFAULT_LANGUAGE): Language {
  const normalized = String(value || '').trim().toLowerCase();
  if (isSupportedLanguage(normalized)) return normalized;
  if (isSupportedLanguage(fallback)) return fallback;
  return DEFAULT_LANGUAGE;
}

export function languageMeta(language: Language): LocaleMeta {
  const normalized = normalizeLanguage(language);
  return localeMetaByCode[normalized] || localeMetaByCode[DEFAULT_LANGUAGE] || {
    code: DEFAULT_LANGUAGE,
    name: DEFAULT_LANGUAGE,
    nativeName: DEFAULT_LANGUAGE,
    shortName: DEFAULT_LANGUAGE.toUpperCase(),
    locale: 'en-US',
    helpFile: 'README.md',
  };
}

export function localeForLanguage(language: Language): string {
  return languageMeta(language).locale;
}

export function helpFileForLanguage(language: Language): string {
  return languageMeta(language).helpFile;
}

export function nextLanguage(current: Language): Language {
  if (availableLanguages.length <= 1) return normalizeLanguage(current);
  const normalized = normalizeLanguage(current);
  const index = availableLanguages.findIndex(language => language.code === normalized);
  return availableLanguages[(index + 1 + availableLanguages.length) % availableLanguages.length].code;
}

export function languageOptionLabel(language: LocaleMeta): string {
  return language.nativeName === language.name ? language.nativeName : `${language.nativeName} / ${language.name}`;
}

export function translate(language: Language, key: TranslationKey, vars?: Record<string, string | number>): string {
  const normalized = normalizeLanguage(language);
  let value: string = translations[normalized]?.[key]
    ?? translations[DEFAULT_LANGUAGE]?.[key]
    ?? translations.de?.[key]
    ?? String(key);
  if (vars) {
    for (const [name, replacement] of Object.entries(vars)) {
      value = value.split(`{${name}}`).join(String(replacement));
    }
  }
  return value;
}
