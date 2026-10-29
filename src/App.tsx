import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'

type Project = {
  id: string
  name: string
  folder_path: string
  planned_start: string
  planned_end: string
  color: string
  archived: boolean
}

type ProjectForm = Omit<Project, 'id' | 'color' | 'archived'>

const emptyForm: ProjectForm = { name: '', folder_path: '', planned_start: '', planned_end: '' }
const weekDays = ['一', '二', '三', '四', '五', '六', '日']

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    throw new Error(Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join('；') : detail || `请求失败 (${response.status})`)
  }
  return response.json()
}

function dateLabel(value: string) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}

function monthCells(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
  const count = Math.ceil((new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate() + ((first.getDay() + 6) % 7)) / 7) * 7
  return Array.from({ length: count }, (_, index) => {
    const day = new Date(start)
    day.setDate(start.getDate() + index)
    return day
  })
}

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  const [selected, setSelected] = useState<Project | null>(null)
  const [editing, setEditing] = useState<Project | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<ProjectForm>(emptyForm)
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      setProjects(await api<Project[]>(`/api/projects?include_archived=${showArchived}`))
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法连接本地服务')
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  useEffect(() => { void loadProjects() }, [loadProjects])

  const cells = useMemo(() => monthCells(month), [month])
  const weeks = useMemo(() => Array.from({ length: cells.length / 7 }, (_, index) => cells.slice(index * 7, index * 7 + 7)), [cells])
  const activeProjects = projects.filter((project) => !project.archived)
  const visibleProjects = projects

  function openCreate() {
    setEditing(null)
    setForm(emptyForm)
    setFormOpen(true)
  }

  function openEdit(project: Project) {
    setSelected(null)
    setEditing(project)
    setForm({ name: project.name, folder_path: project.folder_path, planned_start: project.planned_start, planned_end: project.planned_end })
    setFormOpen(true)
  }

  async function saveProject(event: FormEvent) {
    event.preventDefault()
    try {
      const saved = await api<Project>(editing ? `/api/projects/${editing.id}` : '/api/projects', {
        method: editing ? 'PUT' : 'POST', body: JSON.stringify(form),
      })
      setFormOpen(false)
      setSelected(saved)
      await loadProjects()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    }
  }

  async function archive(project: Project, archived: boolean) {
    try {
      await api<Project>(`/api/projects/${project.id}/archive?archived=${archived}`, { method: 'PUT' })
      setSelected(null)
      await loadProjects()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败')
    }
  }

  function prevMonth() { setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1)) }
  function nextMonth() { setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1)) }
  function goToday() { setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1)) }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home" onClick={() => setSelected(null)}><span className="brand-mark">P</span><span>项目进度看板<small>PROJECT DASHBOARD</small></span></a>
        <div className="top-actions">
          <button className={`quiet-button ${showArchived ? 'selected' : ''}`} onClick={() => setShowArchived(!showArchived)}>{showArchived ? '隐藏归档' : '查看归档'}</button>
          <button className="primary-button" onClick={openCreate}><span>＋</span> 添加项目</button>
        </div>
      </header>

      <section className="page-heading">
        <div><div className="eyebrow">WORKSPACE / OVERVIEW</div><h1>项目总览</h1><p>在一个时间轴上掌握各项目的计划安排。</p></div>
        <div className="heading-stat"><strong>{activeProjects.length}</strong><span>个进行中的项目</span></div>
      </section>

      {error && <div className="notice error-notice" role="alert">{error}<button onClick={() => setError('')}>×</button></div>}

      <section className="calendar-card">
        <div className="calendar-toolbar">
          <div className="month-switch"><button className="icon-button" onClick={prevMonth} aria-label="上个月">‹</button><h2>{month.getFullYear()}年 {month.getMonth() + 1}月</h2><button className="icon-button" onClick={nextMonth} aria-label="下个月">›</button><button className="today-button" onClick={goToday}>今天</button></div>
          <span className="calendar-caption">计划周期</span>
        </div>
        <div className="calendar-grid">
          <div className="weekday-row">{weekDays.map((day) => <div key={day}>{day}</div>)}</div>
          <div className="calendar-weeks">{weeks.map((week, weekIndex) => {
            const isoDay = (day: Date) => `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
            const first = isoDay(week[0])
            const last = isoDay(week[6])
            const lanes: number[] = []
            const events = visibleProjects
              .filter((project) => project.planned_start <= last && project.planned_end >= first)
              .map((project) => ({ project, start: Math.max(0, week.findIndex((day) => isoDay(day) >= project.planned_start)), end: Math.min(6, week.findIndex((day) => isoDay(day) > project.planned_end) < 0 ? 6 : week.findIndex((day) => isoDay(day) > project.planned_end) - 1) }))
              .sort((a, b) => a.start - b.start || a.end - b.end || a.project.name.localeCompare(b.project.name))
              .map((event) => {
                let lane = 0
                while (lanes[lane] !== undefined && lanes[lane] >= event.start) lane += 1
                lanes[lane] = event.end
                return { ...event, lane }
              })
            return <div className="week-block" key={weekIndex}>
              <div className="days-grid">{week.map((day) => {
                const iso = isoDay(day)
                const inMonth = day.getMonth() === month.getMonth()
                const localToday = new Date()
                const todayIso = `${localToday.getFullYear()}-${String(localToday.getMonth() + 1).padStart(2, '0')}-${String(localToday.getDate()).padStart(2, '0')}`
                return <div key={iso} className={`day-cell ${inMonth ? '' : 'outside-month'} ${iso === todayIso ? 'today-cell' : ''}`}><span className="day-number">{day.getDate()}</span></div>
              })}</div>
              <div className="week-events" style={{ minHeight: `${Math.max(1, lanes.length) * 24 + 5}px` }}>
                {events.map(({ project, start, end, lane }) => <button key={project.id} title={`${project.name} · ${dateLabel(project.planned_start)} – ${dateLabel(project.planned_end)}`} style={{ '--project-color': project.color, gridColumn: `${start + 1} / ${end + 2}`, gridRow: lane + 1 } as CSSProperties} className={`project-chip ${project.archived ? 'archived-chip' : ''}`} onClick={() => setSelected(project)}>{project.name}</button>)}
              </div>
            </div>
          })}</div>
        </div>
        {loading && <div className="loading-state">正在读取本地项目…</div>}
        {!loading && projects.length === 0 && <div className="empty-state"><div className="empty-icon">▦</div><strong>还没有项目</strong><p>添加项目名称、文件夹路径和计划日期，开始建立你的项目时间轴。</p><button className="primary-button" onClick={openCreate}>添加第一个项目</button></div>}
      </section>

      <section className="project-list-section">
        <div className="section-heading"><div><h2>{showArchived ? '项目列表（含归档）' : '项目列表'}</h2><p>按计划开始日期排序</p></div><span>{projects.length} 个项目</span></div>
        {projects.length > 0 && <div className="project-table"><div className="table-head"><span>项目</span><span>项目文件夹</span><span>计划周期</span><span>状态</span></div>
          {projects.map((project) => <button key={project.id} className="project-row" onClick={() => setSelected(project)}><span className="project-name"><i style={{ background: project.color }} />{project.name}</span><span className="folder-value" title={project.folder_path}>{project.folder_path}</span><span>{dateLabel(project.planned_start)} — {dateLabel(project.planned_end)}</span><span className={`state-pill ${project.archived ? 'archived' : ''}`}>{project.archived ? '已归档' : '待扫描'}</span></button>)}
        </div>}
      </section>

      <footer className="app-footer"><span>本地保存 · 只记录你登记的项目信息</span><span>Phase 1 · 项目登记与日历</span></footer>

      {(formOpen || selected) && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) { setFormOpen(false); setSelected(null) } }}>
        {formOpen ? <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="form-title"><button className="dialog-close" onClick={() => setFormOpen(false)}>×</button><div className="eyebrow">PROJECT DETAILS</div><h2 id="form-title">{editing ? '编辑项目' : '添加项目'}</h2><p className="dialog-intro">路径仅作为项目来源记录。本阶段不会读取或修改项目文件。</p>
          <form onSubmit={saveProject} className="project-form"><label>项目名称<input required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：海外新品上市" /></label><label>项目文件夹完整路径<input required value={form.folder_path} onChange={(e) => setForm({ ...form, folder_path: e.target.value })} placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\…' : '/Users/… 或 Windows 路径'} /><small>可录入 Windows 路径；当前电脑无法访问的路径会原样保存。</small></label><div className="date-fields"><label>计划开始日期<input required type="date" value={form.planned_start} onChange={(e) => setForm({ ...form, planned_start: e.target.value })} /></label><label>计划结束日期<input required type="date" min={form.planned_start || undefined} value={form.planned_end} onChange={(e) => setForm({ ...form, planned_end: e.target.value })} /></label></div>{error && <div className="form-error">{error}</div>}<div className="form-actions"><button type="button" className="quiet-button" onClick={() => setFormOpen(false)}>取消</button><button className="primary-button" type="submit">{editing ? '保存更改' : '添加项目'}</button></div></form>
        </section> : selected && <section className="dialog detail-dialog" role="dialog" aria-modal="true" aria-labelledby="detail-title"><button className="dialog-close" onClick={() => setSelected(null)}>×</button><div className="eyebrow">PROJECT OVERVIEW</div><h2 id="detail-title"><i style={{ background: selected.color }} />{selected.name}</h2><div className="detail-date"><span>计划周期</span><strong>{dateLabel(selected.planned_start)} — {dateLabel(selected.planned_end)}</strong></div><div className="detail-block"><h3>项目文件夹</h3><code>{selected.folder_path}</code></div><div className="detail-block"><h3>项目简介</h3><p className="placeholder-text">项目简介将在后续 Markdown 扫描阶段从 README 中提取。</p></div><div className="detail-block"><h3>Phase 时间线</h3><div className="phase-placeholder"><span className="phase-node active" /><div><strong>尚无阶段信息</strong><small>项目 Phase 将在后续扫描阶段读取并展示。</small></div></div></div><div className="detail-actions"><button className="quiet-button" onClick={() => openEdit(selected)}>编辑项目</button>{selected.archived ? <button className="primary-button" onClick={() => void archive(selected, false)}>恢复项目</button> : <button className="quiet-button danger-button" onClick={() => void archive(selected, true)}>归档项目</button>}</div></section>}
      </div>}
    </main>
  )
}
