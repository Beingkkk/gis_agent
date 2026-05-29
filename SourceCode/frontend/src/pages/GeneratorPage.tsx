import { useState } from 'react'
import { Link } from 'react-router-dom'
import { generateTemplate, validateTemplate, saveTemplate } from '../api/generator'
import type { GeneratedTemplate, ParamDef } from '../types'

type Step = 1 | 2 | 3 | 4 | 5

export default function GeneratorPage() {
  const [step, setStep] = useState<Step>(1)
  const [documentText, setDocumentText] = useState('')
  const [category, setCategory] = useState('vector')
  const [toolSource, setToolSource] = useState('GDAL')
  const [generated, setGenerated] = useState<GeneratedTemplate | null>(null)
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [savedPath, setSavedPath] = useState<string | null>(null)

  const handleGenerate = async () => {
    if (!documentText.trim()) return
    setIsLoading(true)
    try {
      const result = await generateTemplate(documentText, {
        category,
        tool_source: toolSource,
      })
      setGenerated(result)
      setStep(3)
    } catch (e) {
      console.error('生成失败:', e)
      alert('生成失败，请检查输入')
    } finally {
      setIsLoading(false)
    }
  }

  const handleValidate = async () => {
    if (!generated) return
    setIsLoading(true)
    try {
      const result = await validateTemplate(generated.body)
      setValidation(result)
      setStep(4)
    } catch (e) {
      console.error('验证失败:', e)
    } finally {
      setIsLoading(false)
    }
  }

  const handleSave = async () => {
    if (!generated) return
    setIsLoading(true)
    try {
      const result = await saveTemplate(
        generated.template_id,
        generated.body,
        false
      )
      setSavedPath(result.saved_path)
      setStep(5)
    } catch (e) {
      console.error('保存失败:', e)
      alert('保存失败，可能模板已存在')
    } finally {
      setIsLoading(false)
    }
  }

  const steps: { num: Step; label: string }[] = [
    { num: 1, label: '文档' },
    { num: 2, label: '配置' },
    { num: 3, label: '预览' },
    { num: 4, label: '审查' },
    { num: 5, label: '保存' },
  ]

  return (
    <div className="h-screen w-screen flex flex-col bg-gray-50">
      <header className="h-14 border-b border-gray-200 bg-white px-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-800">J2 模板生成器</h1>
        <Link
          to="/"
          className="text-sm text-primary-600 hover:text-primary-700"
        >
          返回主应用
        </Link>
      </header>

      {/* Step indicator */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-2 max-w-3xl mx-auto">
          {steps.map((s, i) => (
            <div key={s.num} className="flex items-center">
              <button
                onClick={() => {
                  if (s.num <= step) setStep(s.num)
                }}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium ${
                  s.num === step
                    ? 'bg-primary-600 text-white'
                    : s.num < step
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-400'
                }`}
              >
                <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-xs">
                  {s.num}
                </span>
                {s.label}
              </button>
              {i < steps.length - 1 && (
                <div
                  className={`w-8 h-px mx-1 ${
                    s.num < step ? 'bg-primary-400' : 'bg-gray-200'
                  }`}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6">
        <div className="max-w-3xl mx-auto">
          {/* Step 1: Document input */}
          {step === 1 && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">
                输入 GDAL 文档
              </h2>
              <p className="text-sm text-gray-500">
                粘贴 GDAL 工具的 HTML 文档或命令说明文本，LLM 将据此生成 J2 模板。
              </p>
              <textarea
                value={documentText}
                onChange={(e) => setDocumentText(e.target.value)}
                placeholder="在此粘贴 GDAL 文档内容..."
                className="w-full h-[300px] rounded-md border border-gray-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
              />
              <div className="flex justify-end">
                <button
                  onClick={() => setStep(2)}
                  disabled={!documentText.trim()}
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  下一步
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Config */}
          {step === 2 && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">
                配置模板属性
              </h2>
              <div className="space-y-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    类别
                  </label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    <option value="vector">矢量 (vector)</option>
                    <option value="raster">栅格 (raster)</option>
                    <option value="general">通用 (general)</option>
                    <option value="database">数据库 (database)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    工具来源
                  </label>
                  <input
                    type="text"
                    value={toolSource}
                    onChange={(e) => setToolSource(e.target.value)}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                </div>
              </div>
              <div className="flex justify-between">
                <button
                  onClick={() => setStep(1)}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={isLoading}
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {isLoading ? '生成中...' : '生成模板'}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Preview */}
          {step === 3 && generated && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">
                生成结果
              </h2>
              <div className="space-y-2">
                <p className="text-sm">
                  <span className="font-medium text-gray-700">ID:</span>{' '}
                  {generated.template_id}
                </p>
                <p className="text-sm">
                  <span className="font-medium text-gray-700">名称:</span>{' '}
                  {generated.name}
                </p>
                <p className="text-sm">
                  <span className="font-medium text-gray-700">描述:</span>{' '}
                  {generated.description}
                </p>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  参数
                </h3>
                <div className="space-y-1">
                  {generated.params.map((p: ParamDef) => (
                    <div
                      key={p.name}
                      className="text-xs bg-gray-50 rounded px-2 py-1"
                    >
                      {p.name} ({p.type})
                      {p.required && ' *'} — {p.description}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  模板体
                </h3>
                <pre className="bg-gray-900 text-gray-100 p-3 text-xs font-mono rounded-md overflow-x-auto whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                  {generated.body}
                </pre>
              </div>

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(2)}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleValidate}
                  disabled={isLoading}
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {isLoading ? '验证中...' : '安全审查'}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Review */}
          {step === 4 && validation && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">
                安全审查结果
              </h2>

              {validation.valid ? (
                <div className="rounded-lg bg-green-50 border border-green-200 p-4">
                  <p className="text-sm font-medium text-green-700">
                    通过安全审查
                  </p>
                  <p className="text-xs text-green-600 mt-1">
                    模板语法正确，未发现危险模式。
                  </p>
                </div>
              ) : (
                <div className="rounded-lg bg-red-50 border border-red-200 p-4">
                  <p className="text-sm font-medium text-red-700">
                    审查未通过
                  </p>
                  <ul className="mt-2 space-y-1">
                    {validation.errors.map((err, i) => (
                      <li key={i} className="text-xs text-red-600">
                        • {err}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => setStep(3)}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleSave}
                  disabled={isLoading || !validation.valid}
                  className="rounded-md bg-green-600 px-6 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {isLoading ? '保存中...' : '保存模板'}
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Saved */}
          {step === 5 && savedPath && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
                <svg
                  className="w-8 h-8 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-800">
                模板保存成功
              </h2>
              <p className="text-sm text-gray-500">
                保存路径: {savedPath}
              </p>
              <div className="flex justify-center gap-3">
                <Link
                  to="/"
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700"
                >
                  返回主应用
                </Link>
                <button
                  onClick={() => {
                    setStep(1)
                    setDocumentText('')
                    setGenerated(null)
                    setValidation(null)
                    setSavedPath(null)
                  }}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  再生成一个
                </button>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
