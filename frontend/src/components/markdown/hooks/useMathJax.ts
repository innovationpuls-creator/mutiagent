import { useCallback, useState, useEffect } from 'react';

export function useMathJax() {
  const [MathJax, setMathJax] = useState<any>(null);

  useEffect(() => {
    import('mathjax').then((module) => {
      setMathJax(module.default || module);
    });
  }, []);

  const renderMath = useCallback(
    async (content: string): Promise<string> => {
      if (!MathJax) return content;

      try {
        // 配置 MathJax
        if (!MathJax.config) {
          MathJax.startup = {
            typeset: true,
            ready: () => {
              MathJax.startup.defaultReady();
            },
          };
        }

        // 渲染行内公式 $...$
        const inlineRegex = /\$([^$]+)\$/g;
        const blockRegex = /\$\$([^$]+)\$\$/g;

        let result = content;

        // 渲染块级公式
        result = result.replace(blockRegex, (match, formula) => {
          try {
            return `<div class="math-block">${MathJax.tex2chtml(formula, { display: true }).outerHTML}</div>`;
          } catch (e) {
            return match;
          }
        });

        // 渲染行内公式
        result = result.replace(inlineRegex, (match, formula) => {
          try {
            return `<span class="math-inline">${MathJax.tex2chtml(formula, { display: false }).outerHTML}</span>`;
          } catch (e) {
            return match;
          }
        });

        return result;
      } catch (error) {
        console.warn('MathJax rendering failed', error);
        return content;
      }
    },
    [MathJax]
  );

  return { renderMath, isLoaded: !!MathJax };
}
