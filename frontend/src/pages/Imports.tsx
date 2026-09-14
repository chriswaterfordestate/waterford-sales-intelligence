import { useState, useEffect, useRef } from 'react'
import { Upload, CheckCircle, AlertCircle, FileText, Loader2, X, ChevronRight } from 'lucide-react'
import { importsApi } from '../lib/api'

type BatchRow = {
  id: string; file_name: string; status: string; source_code: string;
  source_name: string; total_rows: number; mapped: number; pending: number; created_at: string
}

const KNOWN_FORMATS = [
  { code: 'ERP_EXPORT',    name: 'ERP / EzyWine CSV export',                        hint: '.csv · debtor, salgrpname, finmth columns' },
  { code: 'NGF_SALESOUT',  name: 'NGF SalesOut',                                    hint: '.xlsx · 4REP tab' },
  { code: 'NGF_MONTHLY',   name: 'NGF Monthly Waterford Report',                    hint: '.xlsx · flat Data tab' },
  { code: 'DISTRILIQ_CPT', name: 'Distriliq CPT Client Report',                     hint: '.xlsx · Client History pivot tab' },
]

const STATUS_COLOURS: Record<string, string> = {
  COMPLETE:           'bg-emerald-100 text-emerald-700',
  PARTIAL_COMPLETE:   'bg-amber-100 text-amber-700',
  FAILED:             'bg-red-100 text-red-700',
  DUPLICATE_DETECTED: 'bg-gray-100 text-gray-600',
}

export function ImportsPage() {
  const [batches, setBatches] = useState<BatchRow[]>([])
  const [loading, setLoading] = useState(true)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  // Source-selection state — held when API returns IDENTIFICATION_REQUIRED
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  function loadBatches() {
    return importsApi.batches(15).then(d => setBatches((d.batches || []) as BatchRow[]))
  }
  useEffect(() => { loadBatches().finally(() => setLoading(false)) }, [])

  async function handleFile(file: File, sourceOverride?: string) {
    setUploading(true)
    if (!sourceOverride) {
      setResult(null)
      setPendingFile(null)
    }
    try {
      const res = await importsApi.upload(file, 'webapp', sourceOverride)
      if (res.status === 'IDENTIFICATION_REQUIRED' && !sourceOverride) {
        // Keep the file in memory so the user can select a source and resubmit
        setPendingFile(file)
      } else {
        setPendingFile(null)
      }
      setResult(res)
      if (res.status !== 'IDENTIFICATION_REQUIRED') loadBatches()
    } catch (e: any) {
      setResult({ status: 'ERROR', error: e.message })
    } finally {
      setUploading(false)
    }
  }

  async function handleSourceChoice(code: string) {
    if (!pendingFile) return
    await handleFile(pendingFile, code)
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    e.target.value = ''
  }

  const summary = result?.summary as Record<string, unknown> | undefined
  const summaryLines = summary?.lines as string[] | undefined
  const isIdentificationRequired = result?.status === 'IDENTIFICATION_REQUIRED'

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#1F3864]">Import Centre</h1>

      {/* Upload zone — hidden while awaiting source selection */}
      {!isIdentificationRequired && (
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors cursor-pointer
            ${dragging ? 'border-[#1F3864] bg-blue-50' : 'border-gray-300 bg-gray-50 hover:border-gray-400'}`}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !uploading && fileRef.current?.click()}
        >
          <input ref={fileRef} type="file" className="hidden"
            accept=".csv,.xlsx,.xls" onChange={onFileChange} />
          {uploading ? (
            <div className="flex flex-col items-center gap-2 text-[#1F3864]">
              <Loader2 size={32} className="animate-spin" />
              <p className="font-medium">Importing…</p>
              <p className="text-xs text-gray-500">Classify → match clients → DC rules → coverage</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 text-gray-500">
              <Upload size={32} className="text-gray-400" />
              <p className="font-medium text-gray-700">Drop a sales file here or click to browse</p>
              <p className="text-xs">ERP CSV · NGF SalesOut · NGF Monthly · Distriliq CPT</p>
            </div>
          )}
        </div>
      )}

      {/* ── IDENTIFICATION_REQUIRED: source selection ───────────────────── */}
      {isIdentificationRequired && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-5 space-y-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={18} className="text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-amber-800 text-sm">
                Cannot identify file format — {String(result?.filename || pendingFile?.name || '')}
              </p>
              <p className="text-amber-700 text-xs mt-1">
                Select the correct source type and the file will be imported using that connector.
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {KNOWN_FORMATS.map(fmt => (
              <button
                key={fmt.code}
                onClick={() => handleSourceChoice(fmt.code)}
                disabled={uploading}
                className="text-left bg-white border border-amber-200 rounded-lg px-4 py-3 hover:border-[#1F3864] hover:bg-blue-50 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-gray-800 group-hover:text-[#1F3864]">{fmt.name}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{fmt.hint}</p>
                  </div>
                  <ChevronRight size={14} className="text-gray-300 group-hover:text-[#1F3864]" />
                </div>
              </button>
            ))}
          </div>
          <button
            onClick={() => { setResult(null); setPendingFile(null) }}
            className="text-xs text-gray-500 underline"
          >
            Cancel — upload a different file
          </button>
        </div>
      )}

      {/* Import result (non-IDENTIFICATION_REQUIRED) */}
      {result && !isIdentificationRequired && (
        <div className={`rounded-lg border p-4 relative
          ${result.status === 'ERROR' ? 'bg-red-50 border-red-200'
          : result.status === 'DUPLICATE_DETECTED' ? 'bg-gray-50 border-gray-200'
          : 'bg-emerald-50 border-emerald-200'}`}>
          <button className="absolute top-3 right-3 text-gray-400 hover:text-gray-600" onClick={() => setResult(null)}>
            <X size={14} />
          </button>
          <div className="flex items-start gap-3">
            {result.status === 'ERROR'
              ? <AlertCircle size={18} className="text-red-500 flex-shrink-0 mt-0.5" />
              : result.status === 'DUPLICATE_DETECTED'
              ? <AlertCircle size={18} className="text-gray-400 flex-shrink-0 mt-0.5" />
              : <CheckCircle size={18} className="text-emerald-600 flex-shrink-0 mt-0.5" />
            }
            <div className="space-y-1">
              <p className="font-medium text-sm text-gray-800">
                {summary?.headline as string || String(result.status)}
              </p>
              {result.status === 'ERROR' && (
                <p className="text-xs text-red-700">{result.error as string}</p>
              )}
              {summaryLines?.map((line, i) => (
                <p key={i} className="text-xs text-gray-700">• {line}</p>
              ))}
              {result.status === 'DUPLICATE_DETECTED' && (
                <p className="text-xs text-gray-500">
                  Already imported (batch {String(result.existing_batch_id || '').slice(0, 8)}…). No action taken.
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Recent batches */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Recent Imports</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 size={14} className="animate-spin" /> Loading…
          </div>
        ) : batches.length === 0 ? (
          <p className="text-sm text-gray-400">No imports yet.</p>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-2 text-left">File</th>
                  <th className="px-4 py-2 text-left">Source</th>
                  <th className="px-4 py-2 text-right">Rows</th>
                  <th className="px-4 py-2 text-right">Mapped</th>
                  <th className="px-4 py-2 text-right">Pending</th>
                  <th className="px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {batches.map(b => (
                  <tr key={b.id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <FileText size={13} className="text-gray-400 flex-shrink-0" />
                        <span className="text-gray-800 font-medium truncate max-w-48">{b.file_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{b.source_code}</td>
                    <td className="px-4 py-2.5 text-right text-gray-700">{b.total_rows?.toLocaleString('en-ZA')}</td>
                    <td className="px-4 py-2.5 text-right text-emerald-700 font-medium">{b.mapped?.toLocaleString('en-ZA')}</td>
                    <td className="px-4 py-2.5 text-right text-amber-700">{b.pending?.toLocaleString('en-ZA')}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full
                        ${STATUS_COLOURS[b.status] || 'bg-gray-100 text-gray-600'}`}>
                        {b.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
