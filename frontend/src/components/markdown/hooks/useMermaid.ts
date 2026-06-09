import { useCallback, useState, useEffect, useRef } from 'react';

export function useMermaid() {
  const [isLoaded, setIsLoaded] = useState(false);
  const mermaidRef = useRef<any>(null);

  useEffect(() => {
    let active = true;

    import('mermaid').then((module) => {
      const m = (module.default || module) as any;
      m.initialize({ startOnLoad: false, theme: 'default' });
      if (active) {
        mermaidRef.current = m;
        setIsLoaded(true);
      }
    });

    return () => { active = false; };
  }, []);

  const renderDiagram = useCallback(
    async (code: string): Promise<string> => {
      if (!mermaidRef.current) return code;

      try {
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaidRef.current.render(id, code);
        return svg;
      } catch (error) {
        console.warn('Mermaid rendering failed', error);
        return `<pre class="mermaid-error">${code}</pre>`;
      }
    },
    []
  );

  return { renderDiagram, isLoaded };
}
