import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./auditor-markdown.css";

export default function AuditorMarkdown({ children }: { children: string }) {
  return (
    <div className="auditor-markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          // Model output must never cause automatic requests for remote images.
          img: ({ alt }) => <span>{alt}</span>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          ),
          table: ({ children }) => <div className="markdown-table"><table>{children}</table></div>,
        }}
      >
        {children}
      </Markdown>
    </div>
  );
}
