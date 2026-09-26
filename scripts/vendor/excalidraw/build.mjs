// Builds MetaList's vendored Excalidraw editor from the exact packages in package-lock.json:
//   app/static/js/vendor/excalidraw-<version>.min.js          single ES module (Excalidraw + React)
//   app/static/js/vendor/excalidraw-<version>.LICENSE.txt     licences of every bundled package and font
//   app/static/js/vendor/excalidraw-<version>-assets/         stylesheet and self-hosted fonts
//   scripts/vendor/excalidraw/bundle-packages.json            bundled npm packages, audited by check_supply_chain.py
// Usage (from this folder): npm ci && npm run build
import * as esbuild from 'esbuild';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, '..', '..', '..');
const nodeModules = path.join(here, 'node_modules');
const excalidrawDir = path.join(nodeModules, '@excalidraw', 'excalidraw');
const distDir = path.join(excalidrawDir, 'dist', 'prod');
const stubPath = path.join(here, 'src', 'disabled-stub.mjs');

const readJson = (file) => JSON.parse(readFileSync(file, 'utf8'));
const version = readJson(path.join(excalidrawDir, 'package.json')).version;
const pinnedVersion = readJson(path.join(here, 'package.json')).dependencies['@excalidraw/excalidraw'];
if (version !== pinnedVersion) {
  throw new Error(`Installed @excalidraw/excalidraw ${version} does not match pinned ${pinnedVersion}; run npm ci`);
}

const vendorDir = path.join(repoRoot, 'app', 'static', 'js', 'vendor');
const bundlePath = path.join(vendorDir, `excalidraw-${version}.min.js`);
const licensePath = path.join(vendorDir, `excalidraw-${version}.LICENSE.txt`);
const assetsDir = path.join(vendorDir, `excalidraw-${version}-assets`);

// The two patches below target minified code in this chunk of 0.18.1. A version bump must re-check them;
// replaceExactlyOnce fails the build if the code they patch has moved or changed.
const FONT_LOADER_CHUNK = 'chunk-K2UTITRG.js';
const CDN_FALLBACK = '`https://esm.sh/${M.PKG_NAME?`${M.PKG_NAME}@${M.PKG_VERSION}`:"@excalidraw/excalidraw"}/dist/prod/`';
const LOCAL_FALLBACK = 'new URL(window.EXCALIDRAW_ASSET_PATH, window.location.origin).toString()';
const WORKER_PROBE = 'Vd=typeof Worker<"u"';
const NO_WORKER = 'Vd=!1';

// Liberation Sans 1.05 is GPL-licensed and Xiaolai (Chinese/Japanese) is 13 MB, so neither ships;
// browsers substitute system fonts for them.
const SHIPPED_FONTS = {
  Assistant: ['Assistant-OFL.txt'],
  Cascadia: ['CascadiaCode-OFL.txt'],
  ComicShanns: ['ComicShanns-MIT.txt'],
  Excalifont: ['Excalifont-NOTICE.txt', 'Virgil-OFL.md'],
  Lilita: ['LilitaOne-OFL.txt'],
  Nunito: ['Nunito-OFL.txt'],
  Virgil: ['Virgil-OFL.md'],
};

// Packages whose npm tarball omits a licence file; the texts come from their upstream repositories.
const LICENSE_FALLBACKS = {
  '@excalidraw/excalidraw': 'excalidraw-MIT.txt',
  'fuzzy': 'fuzzy-MIT.txt',
  'react-remove-scroll-bar': 'react-remove-scroll-bar-MIT.txt',
};
// Every @radix-ui package is published from the radix-ui/primitives repository under one licence.
const RADIX_LICENSE = 'radix-ui-primitives-MIT.txt';

function replaceExactlyOnce(source, search, replacement, label) {
  const parts = source.split(search);
  if (parts.length !== 2) {
    throw new Error(`${label}: expected exactly one match in ${FONT_LOADER_CHUNK}, found ${parts.length - 1}`);
  }
  return parts.join(replacement);
}

const metalistPatches = {
  name: 'metalist-patches',
  setup(build) {
    // Font subsetting compiles WebAssembly, which MetaList's CSP blocks: embed whole font files instead.
    build.onResolve({ filter: /subset-(shared|worker)\.chunk\.js$/ }, () => ({ path: path.join(here, 'src', 'subset-stub.mjs') }));
    // Only the English interface ships.
    build.onResolve({ filter: /^\.\/locales\// }, (args) => (args.path.startsWith('./locales/en-') ? undefined : { path: stubPath }));
    // The Mermaid importer would add a second copy of Mermaid; MetaList renders Mermaid itself.
    build.onResolve({ filter: /^@excalidraw\/mermaid-to-excalidraw$/ }, () => ({ path: stubPath }));
    build.onLoad({ filter: /chunk-K2UTITRG\.js$/ }, (args) => {
      let source = readFileSync(args.path, 'utf8');
      // Never fall back to the esm.sh CDN for fonts: they are served from MetaList's own static folder.
      source = replaceExactlyOnce(source, CDN_FALLBACK, LOCAL_FALLBACK, 'CDN font fallback');
      // Skip the subsetting worker entirely (it would only fail and log an error before falling back).
      source = replaceExactlyOnce(source, WORKER_PROBE, NO_WORKER, 'subsetting worker probe');
      return { contents: source, loader: 'js' };
    });
  },
};

function packageRootOf(inputPath) {
  const marker = 'node_modules/';
  const index = inputPath.lastIndexOf(marker);
  if (index === -1) {
    return null;
  }
  const segments = inputPath.slice(index + marker.length).split('/');
  const name = segments[0].startsWith('@') ? `${segments[0]}/${segments[1]}` : segments[0];
  // lockKey matches the package's entry in package-lock.json, including nested node_modules copies.
  const lockKey = inputPath.slice(0, index + marker.length) + name;
  return { name, lockKey, dir: path.join(here, ...lockKey.split('/')) };
}

function findLicenseText(name, dir) {
  const candidates = readdirSync(dir).filter((file) => /^(licen[cs]e|copying)(\.(md|txt|markdown))?$/i.test(file));
  if (candidates.length > 0) {
    return readFileSync(path.join(dir, candidates.sort()[0]), 'utf8').trim();
  }
  if (name in LICENSE_FALLBACKS) {
    return readFileSync(path.join(here, 'licenses', LICENSE_FALLBACKS[name]), 'utf8').trim();
  }
  if (name.startsWith('@radix-ui/')) {
    return readFileSync(path.join(here, 'licenses', RADIX_LICENSE), 'utf8').trim();
  }
  return null;
}

const result = await esbuild.build({
  entryPoints: [path.join(here, 'src', 'entry.mjs')],
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: ['es2020'],
  minify: true,
  conditions: ['production'],
  define: { 'process.env.NODE_ENV': '"production"', 'process.env.IS_PREACT': '"false"' },
  legalComments: 'none',
  banner: { js: `/*! MetaList build of @excalidraw/excalidraw ${version} with React ${readJson(path.join(nodeModules, 'react', 'package.json')).version}. Licences: excalidraw-${version}.LICENSE.txt. Built by scripts/vendor/excalidraw/build.mjs. */` },
  metafile: true,
  write: false,
  outfile: bundlePath,
  plugins: [metalistPatches],
  logLevel: 'warning',
});

const packages = new Map();
for (const inputPath of Object.keys(result.metafile.inputs)) {
  const root = packageRootOf(inputPath);
  if (root !== null && !packages.has(root.lockKey)) {
    const manifest = readJson(path.join(root.dir, 'package.json'));
    packages.set(root.lockKey, { name: root.name, lockKey: root.lockKey, version: manifest.version, license: manifest.license, dir: root.dir });
  }
}
const bundled = [...packages.values()].sort((a, b) => a.lockKey.localeCompare(b.lockKey));
for (const required of ['@excalidraw/excalidraw', 'react', 'react-dom']) {
  if (!packages.has(`node_modules/${required}`)) {
    throw new Error(`Bundle is missing ${required}`);
  }
}

const licenseSections = [
  `MetaList build of @excalidraw/excalidraw ${version}`,
  '',
  'This file lists the licences of everything in excalidraw-' + version + '.min.js and in the',
  'excalidraw-' + version + '-assets folder. The bundle is built by scripts/vendor/excalidraw/build.mjs from the',
  'exact package versions in scripts/vendor/excalidraw/package-lock.json, with these changes:',
  '- fonts load only from MetaList\'s own static folder (the esm.sh CDN fallback is removed);',
  '- font subsetting (WebAssembly) is replaced by embedding whole font files in exported SVGs;',
  '- only the English interface is included, and the Mermaid-to-Excalidraw importer is left out;',
  '- the Liberation Sans and Xiaolai fonts are not included.',
  '',
  '='.repeat(78),
  'Bundled JavaScript packages',
  '='.repeat(78),
];
const missingLicenses = bundled.filter((pkg) => findLicenseText(pkg.name, pkg.dir) === null);
if (missingLicenses.length > 0) {
  const described = missingLicenses.map((pkg) => `${pkg.name}@${pkg.version} (${pkg.license})`).join(', ');
  throw new Error(`No licence text for bundled packages; add them to licenses/ and LICENSE_FALLBACKS: ${described}`);
}
for (const pkg of bundled) {
  licenseSections.push('', `--- ${pkg.name}@${pkg.version} (${pkg.license}) ---`, '', findLicenseText(pkg.name, pkg.dir));
}
licenseSections.push('', '='.repeat(78), 'Fonts (excalidraw-' + version + '-assets/fonts)', '='.repeat(78));
for (const [family, files] of Object.entries(SHIPPED_FONTS)) {
  for (const file of files) {
    licenseSections.push('', `--- ${family}: ${file} ---`, '', readFileSync(path.join(here, 'licenses', file), 'utf8').trim());
  }
}

const bundleFile = result.outputFiles.find((file) => file.path === bundlePath);
if (bundleFile === undefined || result.outputFiles.length !== 1) {
  throw new Error('esbuild must produce exactly one output file (no code splitting)');
}
const bundleText = bundleFile.text;
// (pica, used to downscale images dropped into a drawing, still probes for WebAssembly and workers
// and falls back to plain JavaScript when the CSP refuses them.)
for (const forbidden of ['esm.sh', 'unpkg.com', 'jsdelivr.net']) {
  if (bundleText.includes(forbidden)) {
    throw new Error(`Bundle still references ${forbidden}`);
  }
}

mkdirSync(vendorDir, { recursive: true });
writeFileSync(bundlePath, bundleText);
writeFileSync(licensePath, licenseSections.join('\n') + '\n');
rmSync(assetsDir, { recursive: true, force: true });
mkdirSync(path.join(assetsDir, 'fonts'), { recursive: true });
copyFileSync(path.join(distDir, 'index.css'), path.join(assetsDir, 'excalidraw.css'));
for (const family of Object.keys(SHIPPED_FONTS)) {
  const source = path.join(distDir, 'fonts', family);
  if (!existsSync(source)) {
    throw new Error(`Font folder missing from the package: ${family}`);
  }
  const target = path.join(assetsDir, 'fonts', family);
  mkdirSync(target, { recursive: true });
  for (const file of readdirSync(source)) {
    if (!file.endsWith('.woff2')) {
      throw new Error(`Unexpected file in ${family} fonts: ${file}`);
    }
    copyFileSync(path.join(source, file), path.join(target, file));
  }
}
writeFileSync(
  path.join(here, 'bundle-packages.json'),
  JSON.stringify(bundled.map(({ name, lockKey, version: packageVersion, license }) => ({ name, version: packageVersion, license, lockKey })), null, 2) + '\n',
);

const sha256 = createHash('sha256').update(readFileSync(bundlePath)).digest('hex');
console.log(`${path.relative(repoRoot, bundlePath)} ${bundleText.length} bytes sha256=${sha256}`);
console.log(`${bundled.length} bundled packages written to bundle-packages.json`);
