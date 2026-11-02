import { useMemo } from 'react'
import type { CSSProperties } from 'react'
import type { Project } from '../types'
import { dateLabel, isoDay, monthCells, weekDays } from '../lib/format'

type Props = {
  projects: Project[]
  month: Date
  loading: boolean
  onPrev: () => void
  onNext: () => void
  onToday: () => void
  onSelect: (project: Project) => void
  onCreate: () => void
}

export default function Calendar({ projects, month, loading, onPrev, onNext, onToday, onSelect, onCreate }: Props) {
  const cells = useMemo(() => monthCells(month), [month])

  const weeks = useMemo(
    () => Array.from({ length: cells.length / 7 }, (_, index) => cells.slice(index * 7, index * 7 + 7)),
    [cells],
  )
  const todayIso = isoDay(new Date())

  return (
    <section className="calendar-card">
      <div className="calendar-toolbar">
        <div className="month-switch">
          <button className="icon-button" onClick={onPrev} aria-label="上个月">‹</button>
          <h2>{month.getFullYear()}年 {month.getMonth() + 1}月</h2>
          <button className="icon-button" onClick={onNext} aria-label="下个月">›</button>
          <button className="today-button" onClick={onToday}>今天</button>
        </div>
        <span className="calendar-caption">计划周期 · 当前阶段</span>
      </div>
      <div className="calendar-grid">
        <div className="weekday-row">{weekDays.map((day) => <div key={day}>{day}</div>)}</div>
        <div className="calendar-weeks">
          {weeks.map((week, weekIndex) => {
            const first = isoDay(week[0])
            const last = isoDay(week[6])
            const lanes: number[] = []
            const events = projects
              .filter((project) => project.planned_start <= last && project.planned_end >= first)
              .map((project) => {
                const startIndex = week.findIndex((day) => isoDay(day) >= project.planned_start)
                const endIndex = week.findIndex((day) => isoDay(day) > project.planned_end)
                return {
                  project,
                  start: Math.max(0, startIndex),
                  end: endIndex < 0 ? 6 : endIndex - 1,
                }
              })
              .sort((a, b) => a.start - b.start || a.end - b.end || a.project.name.localeCompare(b.project.name))
              .map((event) => {
                let lane = 0
                while (lanes[lane] !== undefined && lanes[lane] >= event.start) lane += 1
                lanes[lane] = event.end
                return { ...event, lane }
              })
            return (
              <div className="week-block" key={weekIndex}>
                <div className="days-grid">
                  {week.map((day) => (
                    <div
                      key={isoDay(day)}
                      className={`day-cell ${day.getMonth() === month.getMonth() ? '' : 'outside-month'} ${
                        isoDay(day) === todayIso ? 'today-cell' : ''
                      }`}
                    >
                      <span className="day-number">{day.getDate()}</span>
                    </div>
                  ))}
                </div>
                <div className="week-events" style={{ minHeight: `${Math.max(1, lanes.length) * 22 + 6}px` }}>
                  {events.map(({ project, start, end, lane }) => {
                    const state = project.state
                    const tone =
                      state.scan_error ? 'chip-error' : state.status === 'needs_confirmation' ? 'chip-warn' : ''
                    return (
                      <button
                        key={project.id}
                        title={`${project.name} · ${dateLabel(project.planned_start)} – ${dateLabel(project.planned_end)}${
                          state.current_phase ? ` · 当前阶段：${state.current_phase}` : ''
                        }`}
                        style={{ '--project-color': project.color, gridColumn: `${start + 1} / ${end + 2}`, gridRow: lane + 1 } as CSSProperties}
                        className={`project-chip ${project.archived ? 'archived-chip' : ''} ${tone}`}
                        onClick={() => onSelect(project)}
                      >
                        {state.status === 'needs_confirmation' || state.scan_error ? (
                          <span className="chip-flag">!</span>
                        ) : null}
                        <span className="chip-name">{project.name}</span>
                        {state.current_phase && <span className="chip-phase">{state.current_phase}</span>}
                      </button>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      {loading && <div className="loading-state">正在读取本地项目…</div>}
      {!loading && projects.length === 0 && (
        <div className="empty-state">
          <div className="empty-icon">▦</div>
          <strong>还没有项目</strong>
          <p>添加项目名称、文件夹路径和计划日期，开始建立你的项目时间轴。</p>
          <button className="primary-button" onClick={onCreate}>添加第一个项目</button>
        </div>
      )}
    </section>
  )
}
