import React from 'react';
import ReactMarkdown from 'react-markdown';
import '../../styles/editorial.css';

interface EditorialMarkdownProps {
  content: string;
}

export function EditorialMarkdown({ content }: EditorialMarkdownProps) {
  return (
    <div className="editorial-canvas">
      <ReactMarkdown
        components={{
          h1: ({ node, ...props }) => <h1 className="editorial-h1" {...props} />,
          h2: ({ node, ...props }) => <h2 className="editorial-h2" {...props} />,
          h3: ({ node, ...props }) => <h3 className="editorial-h3" {...props} />,
          p: ({ node, ...props }) => <p className="editorial-p" {...props} />,
          blockquote: ({ node, ...props }) => (
            <blockquote className="editorial-quote" {...props} />
          ),
          code: ({ node, inline, className, children, ...props }: any) => {
            const match = /language-(\w+)/.exec(className || '');
            return !inline ? (
              <div className="editorial-code-block">
                <code className={className} {...props}>
                  {children}
                </code>
              </div>
            ) : (
              <code className="editorial-code-inline" {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
