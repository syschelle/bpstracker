import { cpSync, mkdirSync, rmSync, copyFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, '..');
const projectRoot = join(frontendRoot, '..');
const helpRoot = join(frontendRoot, 'public', 'help');

rmSync(helpRoot, { recursive: true, force: true });
mkdirSync(helpRoot, { recursive: true });

copyFileSync(join(projectRoot, 'README.md'), join(helpRoot, 'README.md'));
copyFileSync(join(projectRoot, 'deREADME.md'), join(helpRoot, 'deREADME.md'));

const imageSource = join(projectRoot, 'docs', 'images');
const imageTarget = join(helpRoot, 'docs', 'images');
mkdirSync(imageTarget, { recursive: true });
cpSync(imageSource, imageTarget, { recursive: true });

console.log('Synced README help documents to frontend/public/help');
