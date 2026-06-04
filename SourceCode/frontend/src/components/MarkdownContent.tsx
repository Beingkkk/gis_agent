import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownContentProps {
  content: string
  className?: string
}

const BASE_STYLES = [
  '[&_p]:mb-2',
  '[&_p:last-child]:mb-0',
  '[&_h1]:text-base',
  '[&_h1]:font-bold',
  '[&_h1]:mb-2',
  '[&_h2]:text-base',
  '[&_h2]:font-bold',
  '[&_h2]:mb-2',
  '[&_h3]:text-base',
  '[&_h3]:font-bold',
  '[&_h3]:mb-1.5',
  '[&_ul]:list-disc',
  '[&_ul]:pl-4',
  '[&_ul]:mb-2',
  '[&_ol]:list-decimal',
  '[&_ol]:pl-4',
  '[&_ol]:mb-2',
  '[&_li]:mb-1',
  '[&_pre]:bg-slate-900',
  '[&_pre]:text-slate-200',
  '[&_pre]:p-3',
  '[&_pre]:rounded-lg',
  '[&_pre]:text-xs',
  '[&_pre]:font-mono',
  '[&_pre]:overflow-x-auto',
  '[&_pre]:my-2',
  '[&_code]:px-1',
  '[&_code]:py-0.5',
  '[&_code]:rounded',
  '[&_code]:text-xs',
  '[&_code]:font-mono',
  '[&_pre_code]:bg-transparent',
  '[&_pre_code]:p-0',
  '[&_pre_code]:text-inherit',
  '[&_a]:underline',
  '[&_table]:w-full',
  '[&_table]:border-collapse',
  '[&_table]:my-2',
  '[&_th]:border',
  '[&_th]:border-slate-200',
  '[&_th]:px-2',
  '[&_th]:py-1',
  '[&_th]:text-left',
  '[&_th]:font-semibold',
  '[&_th]:bg-slate-50',
  '[&_td]:border',
  '[&_td]:border-slate-200',
  '[&_td]:px-2',
  '[&_td]:py-1',
  '[&_hr]:my-3',
  '[&_hr]:border-slate-200',
  '[&_blockquote]:border-l-4',
  '[&_blockquote]:border-slate-300',
  '[&_blockquote]:pl-3',
  '[&_blockquote]:italic',
  '[&_blockquote]:my-2',
  '[&_strong]:font-semibold',
].join(' ')

export default function MarkdownContent({ content, className = '' }: MarkdownContentProps) {
  return (
    <div className={`${BASE_STYLES} ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content || ''}
      </ReactMarkdown>
    </div>
  )
}
