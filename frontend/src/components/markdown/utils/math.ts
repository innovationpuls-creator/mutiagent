export function hasLatexSyntax(content: string): boolean {
  return /\$[^$]+\$|\$\$[^$]+\$\$/.test(content);
}

export function extractLatexBlocks(content: string): string[] {
  const blocks: string[] = [];
  const regex = /\$\$([^$]+)\$\$/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    blocks.push(match[1]);
  }
  return blocks;
}