import { useState, useRef, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import TopBar from '../components/TopBar'
import {
  validateTemplate,
  saveTemplate,
  parseDocument,
} from '../api/generator'
import { getApiBaseUrl } from '../electron-api'
import type { GeneratedTemplate, ParamDef } from '../types'

type Step = 1 | 2 | 3 | 4 | 5

type ValidationStatus = 'none' | 'pending' | 'valid' | 'invalid'

interface InlineValidation {
  status: ValidationStatus
  errors: string[]
  checkedBody: string
}

interface ImportedFile {
  name: string
  content: string
  fileType: string
}

// Token budget for LLM input. Claude supports 200K context;
// we allow up to 12000 tokens for the user document.
const MAX_TOKENS = 12000

// Simple Jinja2 syntax highlighter — runs client-side, no extra deps
function highlightJinja2(code: string): string {
  let html = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Jinja2 comment: {# ... #}
  html = html.replace(
    /\{\#\s*(@\w+)\s+(.*?)\s*\#\}/g,
    '<span class="text-gray-500">{#</span> <span class="text-purple-400">$1</span> <span class="text-green-400">$2</span> <span class="text-gray-500">#}</span>'
  )

  // Jinja2 variable: {{ var | filter }}
  html = html.replace(
    /\{\{\s*(.*?)\s*\}\}/g,
    (_match, inner) => {
      const highlighted = inner
        .replace(/(\w+)(?=\s*\|)/g, '<span class="text-cyan-400">$1</span>')
        .replace(/\|/g, '<span class="text-yellow-400">|</span>')
        .replace(/\b(quote|safe_path|default)\b/g, '<span class="text-orange-400">$1</span>')
      return `<span class="text-gray-500">{{</span> ${highlighted} <span class="text-gray-500">}}</span>`
    }
  )

  // Jinja2 statement: {% ... %}
  html = html.replace(
    /\{%\s*(.*?)\s*%\}/g,
    (_match, inner) => {
      const highlighted = inner
        .replace(/\b(if|else|elif|endif|for|endfor|set|include|extends|macro|endmacro)\b/g, '<span class="text-pink-400">$1</span>')
        .replace(/\b(and|or|not|in|is)\b/g, '<span class="text-yellow-400">$1</span>')
      return `<span class="text-gray-500">{%</span> ${highlighted} <span class="text-gray-500">%}</span>`
    }
  )

  return html
}

// Line numbers for the editor
function LineNumbers({ count }: { count: number }) {
  return (
    <div className="select-none text-right pr-3 text-xs text-gray-500 font-mono leading-[22px]">
      {Array.from({ length: Math.max(count, 1) }, (_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  )
}

export default function GeneratorPage() {
  const [step, setStep] = useState<Step>(1)
  const [documentText, setDocumentText] = useState('')
  const [category, setCategory] = useState('vector')
  const [toolSource, setToolSource] = useState('GDAL')
  const [generated, setGenerated] = useState<GeneratedTemplate | null>(null)
  const [validation, setValidation] = useState<{ valid: boolean; errors: string[] } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [savedPath, setSavedPath] = useState<string | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [editedBody, setEditedBody] = useState('')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [inlineValidation, setInlineValidation] = useState<InlineValidation>({
    status: 'none',
    errors: [],
    checkedBody: '',
  })
  const [editorLineCount, setEditorLineCount] = useState(1)
  const editorRef = useRef<HTMLTextAreaElement>(null)

  // Multi-file import state (DC-0095)
  const [importedFiles, setImportedFiles] = useState<ImportedFile[]>([])
  const [parseResult, setParseResult] = useState<{
    files: Array<{ file_type: string; raw_chars: number; cleaned_chars: number }>
    document_text: string
    estimated_tokens: number
    total_raw_chars: number
    total_cleaned_chars: number
  } | null>(null)
  const [isParsing, setIsParsing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // WebSocket streaming state (DC-0096)
  const [isGenerating, setIsGenerating] = useState(false)
  const [streamedText, setStreamedText] = useState('')
  const wsRef = useRef<WebSocket | null>(null)

  // Get the effective template body (edited or original)
  const effectiveBody = editedBody || generated?.body || ''

  // Track line count for editor
  useEffect(() => {
    if (isEditing && effectiveBody) {
      setEditorLineCount(effectiveBody.split('\n').length)
    }
  }, [effectiveBody, isEditing])

  // Check if edited body differs from last validated body
  const hasUnvalidatedChanges = isEditing && inlineValidation.checkedBody !== effectiveBody

  // Token budget check
  const estimatedTokens = parseResult?.estimated_tokens ?? 0
  const isOverBudget = estimatedTokens > MAX_TOKENS

  // File import handlers (DC-0095)
  const handleFileSelect = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    setIsParsing(true)
    setErrorMsg(null)

    try {
      const imported: ImportedFile[] = []
      for (const file of Array.from(files)) {
        const ext = file.name.split('.').pop()?.toLowerCase() || ''
        if (!['html', 'htm', 'md', 'markdown'].includes(ext)) {
          setErrorMsg(`不支持的文件格式: ${file.name}，仅支持 .html 和 .md`)
          continue
        }
        const content = await file.text()
        const fileType = ext === 'htm' ? 'html' : ext === 'md' ? 'markdown' : ext
        imported.push({ name: file.name, content, fileType })
      }

      if (imported.length === 0) {
        setIsParsing(false)
        return
      }

      setImportedFiles(imported)

      const result = await parseDocument(
        imported.map((f) => ({ content: f.content, file_type: f.fileType }))
      )

      setParseResult(result)
      setDocumentText(result.document_text)
    } catch (e: any) {
      console.error('文件导入失败:', e)
      const msg = e.response?.data?.detail || e.message || '未知错误'
      setErrorMsg(`文件导入失败: ${msg}`)
    } finally {
      setIsParsing(false)
    }

    // Reset file input so the same files can be selected again
    e.target.value = ''
  }

  const handleRemoveFile = (index: number) => {
    const newFiles = importedFiles.filter((_, i) => i !== index)
    setImportedFiles(newFiles)
    if (newFiles.length === 0) {
      setParseResult(null)
      setDocumentText('')
    }
  }

  // WebSocket generation (DC-0096)
  const handleGenerate = async () => {
    if (!documentText.trim()) return

    setIsGenerating(true)
    setStreamedText('')
    setErrorMsg(null)

    try {
      const apiBase = await getApiBaseUrl()
      if (!apiBase) {
        setErrorMsg('无法获取后端地址')
        setIsGenerating(false)
        return
      }
      const wsUrl = apiBase.replace(/^http/, 'ws') + '/ws/generator/generate'

      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        ws.send(
          JSON.stringify({
            type: 'start',
            document_text: documentText,
            config: { category, tool_source: toolSource },
          })
        )
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          switch (msg.type) {
            case 'chunk':
              setStreamedText((prev) => prev + msg.content)
              break
            case 'done':
              setGenerated(msg.result)
              setEditedBody(msg.result.body)
              setIsEditing(false)
              setInlineValidation({ status: 'none', errors: [], checkedBody: '' })
              setValidation(null)
              setStep(3)
              setIsGenerating(false)
              ws.close()
              break
            case 'error':
              setErrorMsg(`生成失败: ${msg.message || '未知错误'}`)
              setIsGenerating(false)
              ws.close()
              break
            default:
              console.warn('收到未知类型的 WebSocket 消息:', msg.type)
              break
          }
        } catch (parseErr) {
          console.error('WebSocket 消息解析失败:', parseErr)
          setErrorMsg('收到无效的服务器响应，请重试')
          setIsGenerating(false)
          ws.close()
        }
      }

      ws.onerror = () => {
        setErrorMsg('WebSocket 连接失败')
        setIsGenerating(false)
      }

      ws.onclose = (event) => {
        setIsGenerating(false)
        // 只有非 clean close 且没有已显示的错误时才设置兜底提示
        if (!event.wasClean && event.code !== 1000) {
          setErrorMsg((prev) => prev || '连接意外中断，请重试')
        }
        wsRef.current = null
      }
    } catch (e: any) {
      console.error('生成失败:', e)
      setErrorMsg(`生成失败: ${e.message || '未知错误'}`)
      setIsGenerating(false)
    }
  }

  const handleCancelGenerate = () => {
    wsRef.current?.close()
    setIsGenerating(false)
    setStreamedText('')
  }

  const handleValidate = async () => {
    if (!effectiveBody) return
    setIsLoading(true)
    try {
      const result = await validateTemplate(effectiveBody)
      setValidation(result)
      setInlineValidation({
        status: result.valid ? 'valid' : 'invalid',
        errors: result.errors,
        checkedBody: effectiveBody,
      })
      setStep(4)
    } catch (e) {
      console.error('验证失败:', e)
      setErrorMsg('验证请求失败，请重试')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRevalidate = useCallback(async () => {
    if (!effectiveBody) return
    setIsLoading(true)
    setErrorMsg(null)
    try {
      const result = await validateTemplate(effectiveBody)
      setInlineValidation({
        status: result.valid ? 'valid' : 'invalid',
        errors: result.errors,
        checkedBody: effectiveBody,
      })
      if (!result.valid) {
        setErrorMsg(null)
      }
    } catch (e) {
      console.error('重新验证失败:', e)
      setInlineValidation({
        status: 'invalid',
        errors: ['验证请求失败'],
        checkedBody: effectiveBody,
      })
    } finally {
      setIsLoading(false)
    }
  }, [effectiveBody])

  const handleResetBody = () => {
    if (!generated) return
    setEditedBody(generated.body)
    setEditorLineCount(generated.body.split('\n').length)
    setInlineValidation({ status: 'none', errors: [], checkedBody: '' })
    setErrorMsg(null)
  }

  const handleSave = async () => {
    if (!generated || !effectiveBody) return
    setIsLoading(true)
    try {
      const result = await saveTemplate(
        generated.template_id,
        effectiveBody,
        false
      )
      setSavedPath(result.saved_path)
      setStep(5)
    } catch (e: any) {
      console.error('保存失败:', e)
      if (e.response?.status === 409) {
        const ok = window.confirm('模板已存在，是否覆盖？')
        if (ok) {
          try {
            const result = await saveTemplate(
              generated.template_id,
              effectiveBody,
              true
            )
            setSavedPath(result.saved_path)
            setStep(5)
            return
          } catch (e2) {
            console.error('覆盖保存失败:', e2)
            setErrorMsg('覆盖保存失败')
            return
          }
        }
      } else {
        const msg = e.response?.data?.detail || e.message || '未知错误'
        setErrorMsg(`保存失败: ${msg}`)
      }
    } finally {
      setIsLoading(false)
    }
  }

  // Tab key support in editor
  const handleEditorKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault()
      const target = e.currentTarget
      const start = target.selectionStart
      const end = target.selectionEnd
      const value = target.value
      target.value = value.substring(0, start) + '  ' + value.substring(end)
      target.selectionStart = target.selectionEnd = start + 2
      setEditedBody(target.value)
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
      <TopBar title="J2 模板生成器" backTo="/" />

      {/* Step indicator */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center gap-2 max-w-5xl mx-auto">
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
        <div className="max-w-5xl mx-auto">
          {/* Global error banner */}
          {errorMsg && (
            <div className="mb-4 rounded-lg bg-red-50 border border-red-200 p-4">
              <p className="text-sm font-medium text-red-700">{errorMsg}</p>
            </div>
          )}

          {/* Step 1: Document input */}
          {step === 1 && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-4">
              <h2 className="text-lg font-semibold text-gray-800">
                输入 GDAL 文档
              </h2>
              <p className="text-sm text-gray-500">
                粘贴 GDAL 工具的 HTML 文档或命令说明文本，或导入多个文件。LLM 将据此生成 J2 模板。
              </p>

              {/* File import area */}
              <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50/50 p-4">
                <div className="flex items-center gap-3">
                  <button
                    onClick={handleFileSelect}
                    disabled={isParsing}
                    className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 hover:border-gray-400 transition-all disabled:opacity-50"
                  >
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    {isParsing ? '解析中...' : '选择文件'}
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".html,.htm,.md,.markdown"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <span className="text-xs text-gray-400">
                    支持多文件 .html、.md，自动提取正文并去除噪音
                  </span>
                </div>

                {/* File list */}
                {importedFiles.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {importedFiles.map((file, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between bg-white rounded-md border border-gray-200 px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-700">{file.name}</span>
                          <span className="text-2xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                            {file.fileType}
                          </span>
                          {parseResult && (
                            <span className="text-xs text-gray-400">
                              {parseResult.files[idx]?.raw_chars.toLocaleString()} →{' '}
                              {parseResult.files[idx]?.cleaned_chars.toLocaleString()} 字符
                            </span>
                          )}
                        </div>
                        <button
                          onClick={() => handleRemoveFile(idx)}
                          className="text-gray-400 hover:text-red-500 transition-colors"
                          title="删除"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                        </button>
                      </div>
                    ))}

                    {/* Token budget display */}
                    {parseResult && (
                      <div className="flex items-center justify-between pt-2 border-t border-gray-200">
                        <div className="text-xs text-gray-500">
                          总计: {parseResult.total_raw_chars.toLocaleString()} →{' '}
                          {parseResult.total_cleaned_chars.toLocaleString()} 字符
                          {' · '}
                          <span className={isOverBudget ? 'text-red-600 font-medium' : 'text-gray-600'}>
                            预估 token: {parseResult.estimated_tokens}
                          </span>
                          {' / '}{MAX_TOKENS}
                        </div>
                      </div>
                    )}

                    {/* Over budget warning — advisory only, not blocking */}
                    {isOverBudget && (
                      <div className="rounded-md bg-yellow-50 border border-yellow-200 p-2">
                        <p className="text-xs text-yellow-700">
                          文档较长（约 {estimatedTokens} tokens），生成可能需要更长时间。若超出 LLM 上限，生成时会提示。
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <textarea
                value={documentText}
                onChange={(e) => {
                  setDocumentText(e.target.value)
                  // Clear parse result when manually editing
                  if (parseResult) {
                    setParseResult(null)
                    setImportedFiles([])
                  }
                }}
                placeholder="在此粘贴 GDAL 文档内容..."
                className="w-full h-[260px] rounded-md border border-gray-300 p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
              />
              <div className="flex justify-end">
                <button
                  onClick={() => { setErrorMsg(null); setStep(2) }}
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

              {/* Streaming panel */}
              {isGenerating && (
                <div className="rounded-lg border border-primary-200 bg-primary-50/50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <svg className="animate-spin h-4 w-4 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      <span className="text-sm font-medium text-primary-700">正在生成模板...</span>
                    </div>
                    <button
                      onClick={handleCancelGenerate}
                      className="text-xs text-red-600 hover:text-red-700 font-medium"
                    >
                      取消
                    </button>
                  </div>
                  <div className="rounded-md bg-[#1e1e1e] p-3 overflow-x-auto max-h-[200px] overflow-y-auto">
                    <pre className="text-xs font-mono text-gray-300 whitespace-pre-wrap">
                      {streamedText || '文档解析中，请稍候...'}
                    </pre>
                  </div>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => { setErrorMsg(null); setStep(1) }}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  {isGenerating ? '生成中...' : '生成模板'}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Preview */}
          {step === 3 && generated && (
            <div className="bg-white rounded-lg shadow-sm p-6 space-y-5">
              <h2 className="text-lg font-semibold text-gray-800">
                生成结果
              </h2>

              {/* Metadata grid */}
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">ID</p>
                  <p className="text-sm font-mono text-gray-800 mt-0.5">{generated.template_id}</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">名称</p>
                  <p className="text-sm text-gray-800 mt-0.5">{generated.name}</p>
                </div>
                <div className="col-span-2 bg-gray-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wider">描述</p>
                  <p className="text-sm text-gray-700 mt-0.5">{generated.description}</p>
                </div>
              </div>

              {/* Concepts */}
              {generated.concepts && generated.concepts.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">
                    核心概念
                  </h3>
                  <div className="space-y-1.5">
                    {generated.concepts.map((concept, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 text-sm text-gray-600 bg-blue-50 rounded-lg px-3 py-2"
                      >
                        <svg className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>{concept}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Notes */}
              {generated.notes && generated.notes.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-gray-700 mb-2">
                    注意事项
                  </h3>
                  <div className="space-y-1.5">
                    {generated.notes.map((note, i) => (
                      <div
                        key={i}
                        className="flex items-start gap-2 text-sm text-gray-600 bg-amber-50 rounded-lg px-3 py-2"
                      >
                        <svg className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <span>{note}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Parameters */}
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">
                  参数定义
                </h3>
                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">参数名</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">类型</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">必填</th>
                        <th className="text-left px-3 py-2 text-xs font-medium text-gray-500">描述</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {generated.params.map((p: ParamDef) => (
                        <tr key={p.name} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono text-xs text-gray-700">{p.name}</td>
                          <td className="px-3 py-2">
                            <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">{p.type}</span>
                          </td>
                          <td className="px-3 py-2">
                            {p.required ? (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-red-50 text-red-600 font-medium">必填</span>
                            ) : (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-400">可选</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-xs text-gray-500">{p.description || '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Template body — editor or preview */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-medium text-gray-700">
                    模板体
                  </h3>
                  <button
                    onClick={() => {
                      setIsEditing(!isEditing)
                      if (!isEditing) {
                        // Switching to edit mode — mark as unvalidated
                        setInlineValidation((prev) => ({
                          ...prev,
                          status: prev.checkedBody === effectiveBody ? prev.status : 'none',
                        }))
                      }
                    }}
                    className="text-xs text-primary-600 hover:text-primary-700 font-medium"
                  >
                    {isEditing ? '预览模式' : '编辑模板'}
                  </button>
                </div>

                {isEditing ? (
                  <div className="space-y-2">
                    {/* Monaco-style editor */}
                    <div className="rounded-lg border border-gray-300 overflow-hidden bg-[#1e1e1e]">
                      <div className="flex items-center justify-between px-3 py-1.5 bg-[#252526] border-b border-[#333]">
                        <span className="text-xs text-gray-400">{generated.template_id}.j2</span>
                        <span className="text-2xs text-gray-500">Jinja2</span>
                      </div>
                      <div className="flex">
                        <div className="bg-[#1e1e1e] border-r border-[#333] py-2 select-none">
                          <LineNumbers count={editorLineCount} />
                        </div>
                        <textarea
                          ref={editorRef}
                          value={editedBody}
                          onChange={(e) => {
                            setEditedBody(e.target.value)
                            setEditorLineCount(e.target.value.split('\n').length)
                          }}
                          onKeyDown={handleEditorKeyDown}
                          className="flex-1 bg-[#1e1e1e] text-gray-300 p-2 text-xs font-mono leading-[22px] focus:outline-none resize-none min-h-[300px]"
                          spellCheck={false}
                          style={{ tabSize: 2 }}
                        />
                      </div>
                    </div>

                    {/* Inline validation result */}
                    {inlineValidation.status !== 'none' && (
                      <div
                        className={`rounded-lg border p-3 ${
                          inlineValidation.status === 'valid'
                            ? 'bg-green-50 border-green-200'
                            : 'bg-red-50 border-red-200'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          {inlineValidation.status === 'valid' ? (
                            <svg className="w-4 h-4 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          )}
                          <span
                            className={`text-sm font-medium ${
                              inlineValidation.status === 'valid' ? 'text-green-700' : 'text-red-700'
                            }`}
                          >
                            {inlineValidation.status === 'valid'
                              ? '校验通过，可以进入安全审查'
                              : '校验未通过，请修复以下问题'}
                          </span>
                        </div>
                        {inlineValidation.status === 'invalid' && inlineValidation.errors.length > 0 && (
                          <ul className="mt-2 space-y-1 ml-6">
                            {inlineValidation.errors.map((err, i) => (
                              <li key={i} className="text-xs text-red-600">
                                • {err}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    {/* Unvalidated changes warning */}
                    {hasUnvalidatedChanges && (
                      <div className="rounded-lg bg-yellow-50 border border-yellow-200 p-3">
                        <p className="text-xs text-yellow-700">
                          模板内容已修改，请先点击"重新校验"确认无误后再进入下一步。
                        </p>
                      </div>
                    )}

                    <div className="flex justify-end gap-2">
                      <button
                        onClick={handleResetBody}
                        disabled={!generated || editedBody === generated.body}
                        className="rounded-md border border-gray-300 px-4 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                      >
                        恢复原始
                      </button>
                      <button
                        onClick={handleRevalidate}
                        disabled={isLoading}
                        className="rounded-md border border-primary-600 px-4 py-1.5 text-xs font-medium text-primary-600 hover:bg-primary-50 disabled:opacity-50"
                      >
                        {isLoading ? '校验中...' : '重新校验'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-gray-200 overflow-hidden">
                    <div className="flex items-center justify-between px-3 py-1.5 bg-gray-100 border-b border-gray-200">
                      <span className="text-xs text-gray-500 font-mono">{generated.template_id}.j2</span>
                      <span className="text-2xs text-gray-400">Jinja2</span>
                    </div>
                    <div className="bg-[#1e1e1e] p-3 overflow-x-auto max-h-[400px] overflow-y-auto">
                      <pre
                        className="text-xs font-mono leading-[22px] text-gray-300"
                        dangerouslySetInnerHTML={{ __html: highlightJinja2(effectiveBody) }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div className="flex justify-between">
                <button
                  onClick={() => { setErrorMsg(null); setStep(2) }}
                  className="rounded-md border border-gray-300 px-6 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                >
                  上一步
                </button>
                <button
                  onClick={handleValidate}
                  disabled={isLoading || (isEditing && hasUnvalidatedChanges)}
                  className="rounded-md bg-primary-600 px-6 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50"
                  title={isEditing && hasUnvalidatedChanges ? '请先重新校验修改后的模板' : ''}
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
                  <div className="flex items-center gap-2 mb-1">
                    <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p className="text-sm font-medium text-green-700">
                      通过安全审查
                    </p>
                  </div>
                  <p className="text-xs text-green-600 ml-7">
                    模板语法正确，未发现危险模式。可安全保存。
                  </p>
                </div>
              ) : (
                <div className="rounded-lg bg-red-50 border border-red-200 p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <p className="text-sm font-medium text-red-700">
                      审查未通过
                    </p>
                  </div>
                  <ul className="mt-2 space-y-1.5 ml-7">
                    {validation.errors.map((err, i) => (
                      <li key={i} className="text-xs text-red-600 flex items-start gap-1.5">
                        <span className="text-red-400 mt-0.5">•</span>
                        <span>{err}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs text-red-500 mt-3 ml-7">
                    请返回上一步编辑模板，修复问题后重新校验。
                  </p>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  onClick={() => { setErrorMsg(null); setStep(3) }}
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
                保存路径: <code className="bg-gray-100 px-1.5 py-0.5 rounded text-xs font-mono">{savedPath}</code>
              </p>

              {/* Hot-reload notification */}
              <div className="rounded-lg bg-green-50 border border-green-200 p-4 mx-auto max-w-md">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <div className="text-left">
                    <p className="text-sm font-medium text-green-800">
                      已自动热加载
                    </p>
                    <p className="text-xs text-green-600 mt-1">
                      模板注册表已重新扫描，新模板立即可用。返回主应用后，该模板将自动出现在模板列表中，无需重启服务。
                    </p>
                  </div>
                </div>
              </div>

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
                    setIsEditing(false)
                    setEditedBody('')
                    setInlineValidation({ status: 'none', errors: [], checkedBody: '' })
                    setErrorMsg(null)
                    setImportedFiles([])
                    setParseResult(null)
                    setStreamedText('')
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
