import { useCallback, useEffect, useState } from 'react'
import type { Project, ProviderSettings, ScanRun } from './types'
import { api } from './lib/api'
import Calendar from './components/Calendar'
import ProjectDetail from './components/ProjectDetail'
import ProjectForm from './components/ProjectForm'
import ProjectList from './components/ProjectList'
import ProviderForm from './components/ProviderForm'
import ScanBar from './components/ScanBar'

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [run, setRun] = useState<ScanRun | null>(null)
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  const [detailId, setDetailId] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [providerOpen, setProviderOpen] = useState(false)
  const [provider, setProvider] = useState<ProviderSettings | null>(null)
  const [editing, setEditing] = useState<Project | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [detailKey, setDetailKey] = useState(0)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [projectList, scan, providerSettings] = await Promise.all([
        api.listProjects(showArchived),
        api.latestScan(),
        api.getProvider(),
      ])
      setProjects(projectList)
      setRun(scan.run)
      setProvider(providerSettings)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '无法连接本地服务')
    } finally {
      setLoading(false)
    }
  }, [showArchived])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  async function scanNow() {
    setScanning(true)
    try {
      const result = await api.scan()
      setRun(result)
      await loadAll()
      setDetailKey((value) => value + 1)
      if (result.result === 'failed') {
        setError(`${result.message}。上次成功状态已保留。`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '巡检失败')
    } finally {
      setScanning(false)
    }
  }

  async function archive(project: Project, archived: boolean) {
    try {
      await api.setArchived(project.id, archived)
      setDetailId(null)
      await loadAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失败')
    }
  }

  function openCreate() {
    setEditing(null)
    setDetailId(null)
    setProviderOpen(false)
    setFormOpen(true)
  }

  function openSelect(project: Project) {
    setDetailId(project.id)
    setFormOpen(false)
    setProviderOpen(false)
  }

  function openProvider() {
    setDetailId(null)
    setFormOpen(false)
    setProviderOpen(true)
  }

  const activeProjects = projects.filter((project) => !project.archived)
  const activeList = showArchived ? projects : activeProjects
  const needsConfirmation = activeProjects.filter(
    (project) => project.state.status === 'needs_confirmation' || project.state.scan_error,
  ).length

  function prevMonth() {
    setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
  }
  function nextMonth() {
    setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
  }
  function goToday() {
    setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a
          className="brand"
          href="#home"
          onClick={(event) => {
            event.preventDefault()
            setDetailId(null)
            setFormOpen(false)
          }}
        >
          <span className="brand-mark">P</span>
          <span>
            项目进度看板
            <small>PROJECT DASHBOARD</small>
          </span>
        </a>
        <div className="top-actions">
          <button
            className={`quiet-button ${provider?.enabled ? 'selected' : ''}`}
            onClick={openProvider}
            title="配置模型抽取使用的接口与密钥"
          >
            {provider?.enabled ? `模型 · ${provider.model || '已启用'}` : '模型设置'}
          </button>
          <button className={`quiet-button ${showArchived ? 'selected' : ''}`} onClick={() => setShowArchived(!showArchived)}>
            {showArchived ? '隐藏归档' : '查看归档'}
          </button>
          <button className="primary-button" onClick={openCreate}>
            <span>＋</span> 添加项目
          </button>
        </div>
      </header>

      <section className="page-heading">
        <div>
          <div className="eyebrow">WORKSPACE / OVERVIEW</div>
          <h1>项目总览</h1>
          <p>在一条时间轴上掌握各项目的计划安排，状态只来自项目文档中的明确记录。</p>
        </div>
        <div className="heading-stat">
          <strong>{activeProjects.length}</strong>
          <span>
            个进行中的项目{needsConfirmation > 0 ? ` · ${needsConfirmation} 个待确认` : ''}
          </span>
        </div>
      </section>

      {error && (
        <div className="notice error-notice" role="alert">
          {error}
          <button onClick={() => setError('')}>×</button>
        </div>
      )}

      <ScanBar
        run={run}
        scanning={scanning}
        projectCount={activeProjects.length}
        modelEnabled={Boolean(provider?.ready)}
        onScan={() => void scanNow()}
      />

      <Calendar
        projects={activeList}
        month={month}
        loading={loading}
        onPrev={prevMonth}
        onNext={nextMonth}
        onToday={goToday}
        onSelect={openSelect}
        onCreate={openCreate}
      />

      <ProjectList projects={activeList} showArchived={showArchived} onSelect={openSelect} />

      <footer className="app-footer">
        <span>本地保存 · 只读巡检项目文件夹中的 Markdown</span>
        <span>Phase 3 · 规则 + 模型复核，密钥只留在本机</span>
      </footer>

      {(formOpen || detailId || providerOpen) && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setFormOpen(false)
              setDetailId(null)
              setProviderOpen(false)
            }
          }}
        >
          {providerOpen ? (
            <ProviderForm
              onClose={() => setProviderOpen(false)}
              onSaved={(saved) => {
                setProvider(saved)
                setDetailKey((value) => value + 1)
              }}
            />
          ) : formOpen ? (
            <ProjectForm
              project={editing}
              onClose={() => setFormOpen(false)}
              onSaved={(saved) => {
                setFormOpen(false)
                setEditing(null)
                void loadAll()
                setDetailId(saved.id)
              }}
            />
          ) : (
            detailId && (
              <ProjectDetail
                projectId={detailId}
                refreshKey={detailKey}
                onClose={() => setDetailId(null)}
                onEdit={(project) => {
                  setDetailId(null)
                  setEditing(project)
                  setFormOpen(true)
                }}
                onArchive={(project, archived) => void archive(project, archived)}
                onChanged={() => void loadAll()}
              />
            )
          )}
        </div>
      )}
    </main>
  )
}
