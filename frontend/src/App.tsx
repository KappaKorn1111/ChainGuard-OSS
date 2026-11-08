import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'

type Job = {
  id: string
  source_type: 'image' | 'archive'
  source_ref: string
  artifact_sha256: string | null
  status: 'queued' | 'running' | 'completed' | 'failed'
  error: string | null
  created_at: string
}

type Result = {
  sbom: Record<string, unknown>
  vulnerabilities: Array<Record<string, unknown>>
  dependencies: Array<Record<string, unknown>>
  provenance: Record<string, unknown>
  dependency_track_project_uuid: string | null
}

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const statusColor: Record<Job['status'], string> = {
  queued: 'bg-amber-400/15 text-amber-300',
  running: 'bg-cyan-400/15 text-cyan-300',
  completed: 'bg-emerald-400/15 text-emerald-300',
  failed: 'bg-rose-400/15 text-rose-300',
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
  }
  return response.json() as Promise<T>
}

function App() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [resultEnvelope, setResultEnvelope] = useState<{ jobId: string; data: Result } | null>(null)
  const [tab, setTab] = useState<'findings' | 'dependencies' | 'sbom' | 'provenance'>('findings')
  const [imageRef, setImageRef] = useState('alpine:3.20')
  const [health, setHealth] = useState<'checking' | 'healthy' | 'degraded'>('checking')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await api<Job[]>('/api/v1/jobs')
      setJobs(next)
      setSelected((current) => next.find((job) => job.id === current?.id) ?? current)
    } catch (error) {
      setMessage((error as Error).message)
    }
  }, [])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- synchronize remote job state
    void refresh()
    void api('/health/ready').then(() => setHealth('healthy')).catch(() => setHealth('degraded'))
    const timer = window.setInterval(refresh, 5000)
    return () => window.clearInterval(timer)
  }, [refresh])

  useEffect(() => {
    if (selected?.status === 'completed') {
      void api<Result>(`/api/v1/jobs/${selected.id}/results`)
        .then((data) => setResultEnvelope({ jobId: selected.id, data }))
        .catch((error) => setMessage((error as Error).message))
    }
  }, [selected])

  const result = selected && resultEnvelope?.jobId === selected.id ? resultEnvelope.data : null

  async function submitImage(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setMessage('')
    try {
      const job = await api<Job>('/api/v1/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_ref: imageRef }),
      })
      setJobs((current) => [job, ...current])
      setSelected(job)
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function submitArchive(file: File | undefined) {
    if (!file) return
    setSubmitting(true)
    setMessage('')
    const form = new FormData()
    form.append('archive', file)
    try {
      const job = await api<Job>('/api/v1/jobs/upload', { method: 'POST', body: form })
      setJobs((current) => [job, ...current])
      setSelected(job)
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const severities = result?.vulnerabilities.reduce<Record<string, number>>((counts, finding) => {
    const severity = String(finding.severity ?? 'Unknown')
    counts[severity] = (counts[severity] ?? 0) + 1
    return counts
  }, {}) ?? {}

  return (
    <div className="min-h-screen text-slate-200">
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-400">ChainGuard OSS</p>
            <h1 className="mt-1 text-xl font-semibold text-white">Supply chain inspection</h1>
          </div>
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <span className={`h-2.5 w-2.5 rounded-full ${health === 'healthy' ? 'bg-emerald-400' : health === 'degraded' ? 'bg-rose-400' : 'bg-amber-400'}`} />
            API {health}
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-6 py-8 lg:grid-cols-[22rem_1fr]">
        <aside className="space-y-6">
          <section className="rounded-xl border border-slate-800 bg-slate-900/70 p-5">
            <h2 className="font-semibold text-white">New inspection</h2>
            <p className="mt-1 text-sm text-slate-400">Scan a registry image or upload an archive.</p>
            <form className="mt-4 space-y-3" onSubmit={submitImage}>
              <label className="block text-xs font-medium uppercase tracking-wider text-slate-400" htmlFor="image-ref">Container image</label>
              <input id="image-ref" value={imageRef} onChange={(event) => setImageRef(event.target.value)} required className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-emerald-500" />
              <button disabled={submitting} className="w-full rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-50">Inspect image</button>
            </form>
            <div className="my-4 flex items-center gap-3 text-xs text-slate-600"><span className="h-px flex-1 bg-slate-800" />OR<span className="h-px flex-1 bg-slate-800" /></div>
            <label className="block cursor-pointer rounded-lg border border-dashed border-slate-700 px-4 py-3 text-center text-sm text-slate-400 hover:border-emerald-600 hover:text-emerald-300">
              Upload archive
              <input type="file" className="sr-only" disabled={submitting} onChange={(event) => void submitArchive(event.target.files?.[0])} />
            </label>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-white">Inspection jobs</h2><span className="text-xs text-slate-500">{jobs.length} total</span></div>
            <div className="space-y-2">
              {jobs.map((job) => (
                <button key={job.id} onClick={() => setSelected(job)} className={`w-full rounded-lg border p-3 text-left transition ${selected?.id === job.id ? 'border-emerald-600 bg-emerald-950/30' : 'border-slate-800 bg-slate-900/50 hover:border-slate-700'}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-slate-200">{job.source_ref}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${statusColor[job.status]}`}>{job.status}</span>
                  </div>
                  <p className="mt-2 font-mono text-[11px] text-slate-500">{job.id.slice(0, 12)}</p>
                </button>
              ))}
              {!jobs.length && <p className="rounded-lg border border-slate-800 p-4 text-sm text-slate-500">No inspections yet.</p>}
            </div>
          </section>
        </aside>

        <section className="min-w-0">
          {message && <div className="mb-5 rounded-lg border border-rose-900 bg-rose-950/40 p-3 text-sm text-rose-300">{message}</div>}
          {!selected ? (
            <div className="grid min-h-96 place-items-center rounded-xl border border-slate-800 bg-slate-900/40 text-center"><div><div className="text-4xl">⌁</div><h2 className="mt-3 text-lg font-semibold text-white">Select or start an inspection</h2><p className="mt-1 text-sm text-slate-400">Scanner evidence and findings will appear here.</p></div></div>
          ) : (
            <div className="space-y-5">
              <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div><p className="text-xs uppercase tracking-wider text-slate-500">{selected.source_type}</p><h2 className="mt-1 text-xl font-semibold text-white">{selected.source_ref}</h2><p className="mt-2 font-mono text-xs text-slate-500">{selected.id}</p></div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${statusColor[selected.status]}`}>{selected.status}</span>
                </div>
                {selected.error && <p className="mt-4 rounded bg-rose-950/50 p-3 text-sm text-rose-300">{selected.error}</p>}
              </div>

              {result && <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Metric label="Dependencies" value={result.dependencies.length} />
                  <Metric label="Vulnerabilities" value={result.vulnerabilities.length} />
                  <Metric label="Critical / High" value={(severities.Critical ?? 0) + (severities.High ?? 0)} alert />
                </div>
                <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60">
                  <nav className="flex overflow-x-auto border-b border-slate-800 px-3">
                    {(['findings', 'dependencies', 'sbom', 'provenance'] as const).map((item) => <button key={item} onClick={() => setTab(item)} className={`border-b-2 px-4 py-3 text-sm capitalize ${tab === item ? 'border-emerald-400 text-emerald-300' : 'border-transparent text-slate-400'}`}>{item}</button>)}
                  </nav>
                  <div className="max-h-[42rem] overflow-auto p-4">
                    {tab === 'findings' && <DataTable rows={result.vulnerabilities} columns={['severity', 'id', 'package', 'installed_version', 'fixed_versions']} empty="No vulnerabilities found by Grype." />}
                    {tab === 'dependencies' && <DataTable rows={result.dependencies} columns={['name', 'version', 'type', 'purl', 'licenses']} empty="No dependencies found." />}
                    {tab === 'sbom' && <JsonView value={result.sbom} />}
                    {tab === 'provenance' && <JsonView value={result.provenance} />}
                  </div>
                </div>
              </>}
              {!result && selected.status !== 'failed' && <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-10 text-center text-slate-400">Waiting for Syft, Protobom, and Grype to finish…</div>}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

function Metric({ label, value, alert = false }: { label: string; value: number; alert?: boolean }) {
  return <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4"><p className="text-xs uppercase tracking-wider text-slate-500">{label}</p><p className={`mt-2 text-2xl font-semibold ${alert && value ? 'text-rose-400' : 'text-white'}`}>{value}</p></div>
}

function DataTable({ rows, columns, empty }: { rows: Array<Record<string, unknown>>; columns: string[]; empty: string }) {
  if (!rows.length) return <p className="py-10 text-center text-sm text-slate-500">{empty}</p>
  return <table className="w-full text-left text-sm"><thead><tr className="text-xs uppercase tracking-wider text-slate-500">{columns.map((column) => <th className="px-3 py-2" key={column}>{column.replace('_', ' ')}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr className="border-t border-slate-800" key={index}>{columns.map((column) => <td className="max-w-64 truncate px-3 py-3 text-slate-300" key={column} title={String(row[column] ?? '')}>{Array.isArray(row[column]) ? (row[column] as unknown[]).join(', ') : String(row[column] ?? '—')}</td>)}</tr>)}</tbody></table>
}

function JsonView({ value }: { value: unknown }) {
  return <pre className="overflow-auto whitespace-pre-wrap break-all text-xs leading-5 text-slate-300">{JSON.stringify(value, null, 2)}</pre>
}

export default App
