interface ScriptPreviewProps {
  script: string
  onExecute: () => void
  onEdit: () => void
  onCancel: () => void
}

export default function ScriptPreview({
  script,
  onExecute,
  onEdit,
  onCancel,
}: ScriptPreviewProps) {
  const handleCopy = () => {
    navigator.clipboard.writeText(script)
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <div className="flex items-center justify-between bg-gray-800 text-gray-300 px-3 py-1.5 rounded-t-md">
          <span className="text-xs font-mono">脚本预览</span>
          <button
            onClick={handleCopy}
            className="text-xs text-gray-400 hover:text-white"
          >
            复制
          </button>
        </div>
        <pre className="bg-gray-900 text-gray-100 p-3 text-xs font-mono rounded-b-md overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
          {script}
        </pre>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onExecute}
          className="flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
        >
          执行脚本
        </button>
        <button
          onClick={onEdit}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          修改参数
        </button>
        <button
          onClick={onCancel}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          取消
        </button>
      </div>
    </div>
  )
}
