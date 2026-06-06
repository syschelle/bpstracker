import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const localesDir = new URL('../src/i18n/locales/', import.meta.url);
const files = readdirSync(localesDir).filter(file => file.endsWith('.json')).sort();

if (!files.length) {
  console.error('No i18n locale files found.');
  process.exit(1);
}

function readLocale(file) {
  const path = join(localesDir.pathname, file);
  const locale = JSON.parse(readFileSync(path, 'utf8'));
  const expectedCode = file.replace(/\.json$/, '');
  if (!locale.meta || typeof locale.meta !== 'object') throw new Error(`${file}: missing meta object`);
  if (locale.meta.code !== expectedCode) throw new Error(`${file}: meta.code must match filename (${expectedCode})`);
  for (const key of ['name', 'nativeName', 'locale', 'helpFile']) {
    if (!locale.meta[key] || typeof locale.meta[key] !== 'string') throw new Error(`${file}: missing meta.${key}`);
  }
  if (!locale.translations || typeof locale.translations !== 'object') throw new Error(`${file}: missing translations object`);
  return locale;
}

const locales = Object.fromEntries(files.map(file => [file, readLocale(file)]));
const baseFile = files.includes('en.json') ? 'en.json' : files[0];
const baseKeys = Object.keys(locales[baseFile].translations).sort();
let failed = false;

for (const file of files) {
  const keys = Object.keys(locales[file].translations).sort();
  const missing = baseKeys.filter(key => !keys.includes(key));
  const extra = keys.filter(key => !baseKeys.includes(key));
  if (missing.length || extra.length) {
    failed = true;
    if (missing.length) console.error(`${file}: missing keys: ${missing.join(', ')}`);
    if (extra.length) console.error(`${file}: extra keys: ${extra.join(', ')}`);
  }
  for (const key of keys) {
    const value = locales[file].translations[key];
    if (typeof value !== 'string') {
      failed = true;
      console.error(`${file}: translation ${key} must be a string`);
    }
  }
}

if (failed) process.exit(1);
console.log(`i18n check passed for ${files.length} locale file(s).`);
