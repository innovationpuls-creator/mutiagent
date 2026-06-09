export function extractLanguage(className: string | undefined): string {
  if (!className) return '';
  const match = /language-(\w+)/.exec(className);
  return match ? match[1] : '';
}