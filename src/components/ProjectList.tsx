import type { Project } from '../types'
import { dateLabel, stateBadge } from '../lib/format'

type Props = {
  projects: Project[]
  showArchived: boolean
  onSelect: (project: Project) => void
}

export default function ProjectList({ projects, showArchived, onSelect }: Props) {
  return (
    <section className="project-list-section">
      <div className="section-heading">
        <div>
          <h2>{showArchived ? '项目列表（含归档）' : '项目列表'}</h2>
          <p>按计划开始日期排序 · 状态来自项目文档中的明确记录</p>
        </div>
        <span>{projects.length} 个项目</span>
      </div>
      {projects.length > 0 && (
        <div className="project-table">
          <div className="table-head">
            <span>项目</span>
            <span>当前阶段</span>
            <span>最近进展</span>
            <span>状态</span>
          </div>
          {projects.map((project) => {
            const badge = stateBadge(project)
            return (
              <button key={project.id} className="project-row" onClick={() => onSelect(project)}>
                <span className="project-name">
                  <i style={{ background: project.color }} />
                  {project.name}
                </span>
                <span className="phase-value">
                  {project.state.current_phase || '—'}
                  {project.state.testing && <em className="testing-tag">测试中</em>}
                </span>
                <span className="folder-value" title={project.folder_path}>
                  {project.state.newest_record_date
                    ? dateLabel(project.state.newest_record_date)
                    : project.state.scan_error || '无带日期的记录'}
                </span>
                <span className={`state-pill tone-${badge.tone}`}>{badge.text}</span>
              </button>
            )
          })}
        </div>
      )}
    </section>
  )
}
