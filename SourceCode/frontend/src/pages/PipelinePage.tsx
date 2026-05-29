import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { PipelineStep, DataLink, TemplateDef, ParamDef } from '../types'
import { previewPipeline, executePipeline } from '../api/pipeline'
import { listTemplates, getTemplate } from '../api/templates'
import ParamForm from '../components/ParamForm'

interface StepWithDetail {
  order: number
  template_id: string
  template_name: string
  params: Record<string, string>
  paramDefs: ParamDef[]
}

export default function PipelinePage() {
  const [steps, setSteps] = useState<StepWithDetail[]>([])
  const [script, setScript] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [templates, setTemplates] = useState<TemplateDef[]>([])
  const [showAddStep, setShowAddStep] = useState(false)

  const loadTemplates = async () => {
    if (templates.length === 0) {
      const list = await listTemplates()
      setTemplates(list)
    }
    setShowAddStep(true)
  }

  const addStep = async (templateId: string) => {
    const detail = await getTemplate(templateId)
    const newStep: StepWithDetail = {
      order: steps.length,
      template_id: templateId,
      template_name: detail.name,
      params: {},
      paramDefs: detail.params,
    }
    setSteps((prev) => [...prev, newStep])
    setShowAddStep(false)
  }

  const removeStep = (index: number) => {
    setSteps((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((s, i) => ({ ...s, order: i }))
    )
  }

  const updateStepParams = (index: number, params: Record<string, string>) => {
    setSteps((prev) =>
      prev.map((s, i) => (i === index ? { ...s, params } : s))
    )
  }

  const buildAutoLinks = (): DataLink[] => {
    const links: DataLink[] = []
    for (let i = 1; i < steps.length; i++) {
      const prevStep = steps[i - 1]
      const currStep = steps[i]
      // Auto-link if prev has 'output' and curr has 'input'
      if (
        prevStep.paramDefs.some((p) => p.name === 'output') &&
        currStep.paramDefs.some((p) => p.name === 'input')
      ) {
        links.push({
          fromStep: i - 1,
          fromParam: 'output',
          toStep: i,
          toParam: 'input',
        })
      }
    }
    return links
  }

  const handlePreview = async () => {
    if (steps.length === 0) return
    setIsLoading(true)
    try {
      const pipelineSteps: PipelineStep[] = steps.map((s) => ({
        order: s.order,
        template_id: s.template_id,
        params: s.params,
      }))
      const result = await previewPipeline(pipelineSteps, buildAutoLinks())
      setScript(result.script)
    } catch (e) {
      console.error('预览失败:', e)
    } finally {
      setIsLoading(false)
    }
  }

  const handleExecute = async () => {
    if (steps.length === 0) return
    setIsLoading(true)
    try {
      const pipelineSteps: PipelineStep[] = steps.map((s) => ({
        order: s.order,
        template_id: s.template_id,
        params: s.params,
      }))
      await executePipeline(pipelineSteps, buildAutoLinks())
      alert('Pipeline 已触发执行，请通过主应用查看执行日志。')
    } catch (e) {
      console.error('执行失败:', e)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-gray-50">
      <header className="h-14 border-b border-gray-200 bg-white px-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-800">Pipeline 编排</h1>
        <Link
          to="/"
          className="text-sm text-primary-600 hover:text-primary-700"
        >
          返回主应用
        </Link>
      </header>

      <main className="flex-1 flex overflow-hidden">
        {/* Steps panel */}
        <div className="flex-1 overflow-y-auto p-6">
          <div className="max-w-2xl mx-auto space-y-4">
            {steps.length === 0 && (
              <div className="text-center py-12 text-gray-400">
                <p>暂无步骤，点击下方按钮添加</p>
              </div>
            )}

            {steps.map((step, index) => (
              <div key={index} className="relative">
                {index > 0 && (
                  <div className="flex items-center justify-center py-2">
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <div className="w-8 h-px bg-gray-300" />
                      <span>
                        {steps[index - 1].paramDefs.some(
                          (p) => p.name === 'output'
                        ) &&
                        step.paramDefs.some((p) => p.name === 'input')
                          ? 'output → input'
                          : '顺序执行'}
                      </span>
                      <div className="w-8 h-px bg-gray-300" />
                    </div>
                  </div>
                )}

                <div className="bg-white rounded-lg border border-gray-200 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-primary-100 text-primary-700 text-xs font-medium flex items-center justify-center">
                        {index + 1}
                      </span>
                      <span className="text-sm font-medium text-gray-800">
                        {step.template_name}
                      </span>
                    </div>
                    <button
                      onClick={() => removeStep(index)}
                      className="text-xs text-red-500 hover:text-red-700"
                    >
                      删除
                    </button>
                  </div>

                  <ParamForm
                    params={step.paramDefs}
                    values={step.params}
                    onSubmit={(params) => updateStepParams(index, params)}
                    onCancel={() => {}}
                  />
                </div>
              </div>
            ))}

            {/* Add step */}
            {showAddStep ? (
              <div className="bg-white rounded-lg border border-gray-200 p-4">
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                  选择模板
                </h3>
                <div className="grid grid-cols-2 gap-2">
                  {templates.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => addStep(t.id)}
                      className="text-left rounded border border-gray-200 p-2 hover:border-primary-500 hover:bg-primary-50"
                    >
                      <div className="text-sm font-medium text-gray-800">
                        {t.name}
                      </div>
                      <div className="text-xs text-gray-500">
                        {t.description}
                      </div>
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setShowAddStep(false)}
                  className="mt-3 text-xs text-gray-500 hover:text-gray-700"
                >
                  取消
                </button>
              </div>
            ) : (
              <button
                onClick={loadTemplates}
                className="w-full rounded-lg border-2 border-dashed border-gray-300 py-4 text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600"
              >
                + 添加步骤
              </button>
            )}
          </div>
        </div>

        {/* Preview panel */}
        <div className="w-[400px] border-l border-gray-200 bg-white p-4 overflow-y-auto">
          <h2 className="text-sm font-semibold text-gray-800 mb-3">
            脚本预览
          </h2>

          {script ? (
            <div className="space-y-4">
              <pre className="bg-gray-900 text-gray-100 p-3 text-xs font-mono rounded-md overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                {script}
              </pre>

              <div className="flex gap-2">
                <button
                  onClick={handleExecute}
                  disabled={isLoading}
                  className="flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  执行
                </button>
                <button
                  onClick={handlePreview}
                  disabled={isLoading}
                  className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                >
                  刷新
                </button>
              </div>
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-sm text-gray-400 mb-4">
                {steps.length > 0
                  ? '点击"生成脚本"查看合并结果'
                  : '先添加步骤'}
              </p>
              {steps.length > 0 && (
                <button
                  onClick={handlePreview}
                  disabled={isLoading}
                  className="rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  生成脚本
                </button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
