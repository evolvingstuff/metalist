// MetaList replacement for optional Excalidraw features that are not shipped:
// interface translations other than English, and the Mermaid-to-Excalidraw importer.
export default {};

export function parseMermaidToExcalidraw() {
  throw new Error('Mermaid import is not available in MetaList');
}
