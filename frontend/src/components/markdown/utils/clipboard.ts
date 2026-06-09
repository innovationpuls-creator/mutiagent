export async function copyToClipboard(
  text: string,
  button: HTMLButtonElement
): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    button.textContent = 'COPIED!';
    button.ariaLabel = 'Code copied';
  } catch {
    button.textContent = 'FAILED';
    button.ariaLabel = 'Failed to copy code';
  } finally {
    setTimeout(() => {
      button.textContent = 'COPY';
      button.ariaLabel = 'Copy code to clipboard';
    }, 2000);
  }
}
