"use client";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function Markdown({text}:{text:string}) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml urlTransform={url=>/^(https?:\/\/|#)/i.test(url)?url:''} components={{
    a:({node,...props})=><a {...props} className={/^\d+(?:[,\s–-]\d+)*$/.test(String(props.children))?'citation-link':undefined} target="_blank" rel="noopener noreferrer" />,
    table:({node,...props})=><div className="markdown-table"><table {...props}/></div>,
    img:({alt})=><span>{alt||''}</span>,
  }}>{text}</ReactMarkdown></div>;
}
