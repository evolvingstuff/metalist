# Vendored Excalidraw bundle

MetaList edits diagrams with [Excalidraw](https://github.com/excalidraw/excalidraw). The npm package is published
as ES modules that expect a bundler, so this folder builds one self-contained file that the browser can import:

| Output | Contents |
| --- | --- |
| `app/static/js/vendor/excalidraw-<version>.min.js` | Excalidraw, React and React DOM as one ES module |
| `app/static/js/vendor/excalidraw-<version>.LICENSE.txt` | Licence of every bundled package and shipped font |
| `app/static/js/vendor/excalidraw-<version>-assets/` | `excalidraw.css` and the self-hosted fonts |
| `bundle-packages.json` | Every npm package compiled into the bundle, checked against `package-lock.json` and audited by `scripts/check_supply_chain.py` |

Node is only needed to rebuild; MetaList itself runs no Node process.

## Rebuilding

```bash
cd scripts/vendor/excalidraw
npm ci --ignore-scripts
npm run build
```

Then update the Excalidraw entry's `sha256` in `docs/security/vendor-manifest.json` (the build prints it) and run
`python scripts/check_supply_chain.py check`. The build is deterministic: rebuilding unchanged inputs reproduces the
same checksum.

## What the build changes

- **No CDN.** Excalidraw falls back to loading fonts from esm.sh even when a local asset path is configured. The build
  replaces that fallback with `window.EXCALIDRAW_ASSET_PATH`, so fonts only ever load from MetaList's static folder.
- **No WebAssembly.** Exported SVGs normally embed font subsets produced by a WebAssembly tool, which MetaList's
  Content-Security-Policy blocks. `src/subset-stub.mjs` embeds each needed font file whole instead (a few KB to
  25 KB per file).
- **Smaller.** Only the English interface ships, and the Mermaid-to-Excalidraw importer is left out
  (`src/disabled-stub.mjs`); MetaList already renders Mermaid itself.
- **Fonts.** Liberation Sans (the npm package ships version 1.05, which predates its OFL relicensing) and Xiaolai
  (Chinese/Japanese, 13 MB) are not shipped; browsers substitute system fonts.
- **Security fixes.** `package.json` overrides Excalidraw's `nanoid` dependency to a patched 3.x release.

The patches target minified code in one chunk of the pinned release. When upgrading, the build fails loudly if the
patched code has moved; re-check the patches against the new release before adjusting them.

Licence texts that are missing from npm tarballs live in `licenses/`, with their sources in `licenses/SOURCES.md`.
