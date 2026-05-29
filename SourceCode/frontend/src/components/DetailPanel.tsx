import type { TemplateDetail } from '../types'
import ParamForm from './ParamForm'
import ScriptPreview from './ScriptPreview'

interface DetailPanelProps {
  state: string
  templateDetail: TemplateDetail | null
  paramValues: Record<string, string>
  scriptPreview: string | null
  onLockTemplate: (templateId: string) => void
  onSubmitParams: (params: Record<string, string>) => void
  onExecute: () => void
  onEditParams: () => void
  onCancel: () => void
}

export default function DetailPanel({
  state,
  templateDetail,
  paramValues,
  scriptPreview,
  onLockTemplate,
  onSubmitParams,
  onExecute,
  onEditParams,
  onCancel,
}: DetailPanelProps) {
  if (state === 'PARAM_COLLECT' && templateDetail) {
    return (
      <div className="p-4">
        <h2 className="text-sm font-semibold text-gray-800 mb-1">
          {templateDetail.name}
        </h2>
        <p className="text-xs text-gray-500 mb-4">
          {templateDetail.description}
        </p>
        <ParamForm
          params={templateDetail.params}
          values={paramValues}
          onSubmit={onSubmitParams}
          onCancel={onCancel}
        />
      </div>
    )
  }

  if (state === 'SCRIPT_PREVIEW' && scriptPreview) {
    return (
      <div className="p-4">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">
          脚本预览
        </h2>
        <ScriptPreview
          script={scriptPreview}
          onExecute={onExecute}
          onEdit={onEditParams}
          onCancel={onCancel}
        />
      </div>
    )
  }

  if (templateDetail) {
    // IDLE or INTENT_CONFIRM: show template info
    return (
      <div className="p-4 space-y-4">
        <div>
          <h2 className="text-sm font-semibold text-gray-800">
            {templateDetail.name}
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            {templateDetail.description}
          </p>
        </div>

        {templateDetail.concepts.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              概念
            </h3>
            <div className="space-y-2">
              {templateDetail.concepts.map((c, i) => (
                <div key={i} className="text-xs">
                  <span className="font-medium text-gray-700">{c.term}</span>
                  <span className="text-gray-500"> — {c.explanation}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {templateDetail.notes.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              注意事项
            </h3>
            <ul className="list-disc list-inside space-y-1">
              {templateDetail.notes.map((n, i) => (
                <li key={i} className="text-xs text-gray-600">
                  {n}
                </li>
              ))}
            </ul>
          </div>
        )}

        {templateDetail.common_errors.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              常见错误
            </h3>
            <div className="space-y-2">
              {templateDetail.common_errors.map((e, i) => (
                <div
                  key={i}
                  className="rounded bg-red-50 border border-red-100 p-2"
                >
                  <p className="text-xs font-medium text-red-700">
                    {e.error_text}
                  </p>
                  <p className="text-xs text-red-600 mt-0.5">
                    修复: {e.fix}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={() => onLockTemplate(templateDetail.id)}
          className="w-full rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
        >
          使用此模板
        </button>
      </div>
    )
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
        详情
      </h2>
      <p className="text-xs text-gray-400">
        从左栏选择一个模板查看详情，或在聊天区输入需求
      </p>
    </div>
  )
}
