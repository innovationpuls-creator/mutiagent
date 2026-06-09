export function isMermaidBlock(className: string | undefined, content: string): boolean {
  return !!className && className.includes('language-mermaid') && !!content;
}

export function extractMermaidCode(content: string): string {
  return content.replace(/^```mermaid\n/, '').replace(/\n```$/, '');
}