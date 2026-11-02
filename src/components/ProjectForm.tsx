import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Project, ProjectInput } from '../types'
import { api } from '../lib/api'

type Props = {
  project: Project | null
  onClose: () => void
  onSaved: (project: Project) => void
}

const empty: ProjectInput = { name: '', folder_path: '', planned_start: '', planned_end: '' }

export default function ProjectForm({ project, onClose, onSaved }: Props) {
  const [form, setForm] = useState<ProjectInput>(
    project
      ? {
          name: project.name,
          folder_path: project.folder_path,
          planned_start: project.planned_start,
          planned_end: project.planned_end,
        }
      : empty,
  )
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const saved = project ? await api.updateProject(project.id, form) : await api.createProject(form)
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="form-title">
      <button className="dialog-close" onClick={onClose} aria-label="关闭">×</button>
      <div className="eyebrow">PROJECT DETAILS</div>
      <h2 id="form-title">{project ? '编辑项目' : '添加项目'}</h2>
      <p className="dialog-intro">路径只作为只读来源登记。巡检会读取该文件夹下的 Markdown，但不会修改任何项目文件。</p>
      <form onSubmit={submit} className="project-form">
        <label>
          项目名称
          <input
            required
            maxLength={120}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
            placeholder="例如：海外新品上市"
          />
        </label>
        <label>
          项目文件夹完整路径
          <input
            required
            value={form.folder_path}
            onChange={(event) => setForm({ ...form, folder_path: event.target.value })}
            placeholder={navigator.platform.startsWith('Win') ? 'C:\\Users\\…' : '/Users/… 或 Windows 路径'}
          />
          <small>可录入 Windows 路径；当前电脑无法访问的路径会原样保存，巡检时标记为无法访问。</small>
        </label>
        <div className="date-fields">
          <label>
            计划开始日期
            <input
              required
              type="date"
              value={form.planned_start}
              onChange={(event) => setForm({ ...form, planned_start: event.target.value })}
            />
          </label>
          <label>
            计划结束日期
            <input
              required
              type="date"
              min={form.planned_start || undefined}
              value={form.planned_end}
              onChange={(event) => setForm({ ...form, planned_end: event.target.value })}
            />
          </label>
        </div>
        {error && <div className="form-error">{error}</div>}
        <div className="form-actions">
          <button type="button" className="quiet-button" onClick={onClose}>取消</button>
          <button className="primary-button" type="submit" disabled={saving}>
            {saving ? '保存中…' : project ? '保存更改' : '添加项目'}
          </button>
        </div>
      </form>
    </section>
  )
}
