#!/usr/bin/env node
/**
 * Извлекает данные Simple Icons в два артефакта:
 *
 * 1. ../app/simple_icons_index.json — индекс {slug: hex} для Python-резолвера
 * 2. ../app/static/icons/{slug}.svg — SVG-файлы для локальной раздачи
 *
 * Запуск: cd scripts && npm install && npm run extract
 * Docker: docker run --rm -v $(pwd)/scripts:/scripts -v $(pwd)/app:/app -w /scripts node:22-slim sh -c "npm install && node extract-icons.js"
 */

const fs = require('fs');
const path = require('path');

const icons = require('simple-icons');

const index = {};
let count = 0;

// Папка для SVG-файлов
const svgDir = path.join(__dirname, '..', 'app', 'static', 'icons');
fs.mkdirSync(svgDir, { recursive: true });

for (const key of Object.keys(icons)) {
    if (!key.startsWith('si')) continue;
    const icon = icons[key];
    if (!icon || !icon.slug || !icon.hex || !icon.path) continue;

    // Индекс: slug → hex
    index[icon.slug] = icon.hex;

    // SVG-файл: viewBox 0 0 24 24, fill=currentColor для гибкости
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="${icon.path}" fill="currentColor"/></svg>`;
    fs.writeFileSync(path.join(svgDir, `${icon.slug}.svg`), svg);

    count++;
}

// Записываем JSON-индекс
const indexPath = path.join(__dirname, '..', 'app', 'simple_icons_index.json');
fs.writeFileSync(indexPath, JSON.stringify(index));

const indexSize = (fs.statSync(indexPath).size / 1024).toFixed(1);
console.log(`Извлечено ${count} иконок:`);
console.log(`  Индекс: ${indexPath} (${indexSize} KB)`);
console.log(`  SVG:    ${svgDir}/ (${count} файлов)`);
