import type { Project, ProjectState } from '../types'

export const weekDays = ['一', '二', '三', '四', '五', '六', '日']

export function isoDay(day: Date): string {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
}

export function dateLabel(value: string | null | undefined, fallback = '未记录'): string {
  if (!value) return fallback
  const parsed = new Date(`${value}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return fallback
  return parsed.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}

export function timestampLabel(value: string | null | undefined): string {
  if (!value) return '尚未巡检'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function monthCells(month: Date): Date[] {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first)
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7))
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate()
  const count = Math.ceil((daysInMonth + ((first.getDay() + 6) % 7)) / 7) * 7
  return Array.from({ length: count }, (_, index) => {
    const day = new Date(start)
    day.setDate(start.getDate() + index)
    return day
  })
}

export type StateTone = 'neutral' | 'ok' | 'warn' | 'muted' | 'error'

export function stateBadge(project: Project): { text: string; tone: StateTone } {
  const state: ProjectState = project.state
  if (state.scan_error) return { text: '无法访问', tone: 'error' }
  if (project.archived) return { text: '已归档', tone: 'muted' }
  switch (state.status) {
    case 'ok':
      return { text: state.current_phase ? `已同步 · ${state.current_phase}` : '已同步', tone: 'ok' }
    case 'needs_confirmation':
      return { text: '待确认', tone: 'warn' }
    case 'model_error':
      return { text: '模型未确认', tone: 'error' }
    case 'unknown':
      return { text: '阶段未知', tone: 'muted' }
    default:
      return { text: '待扫描', tone: 'neutral' }
  }
}

export function phaseStatusLabel(status: string): string {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'current':
      return '进行中'
    case 'upcoming':
      return '未开始'
    case 'conflict':
      return '文档冲突'
    default:
      return '未标注'
  }
}

export function basisNote(basis: string | undefined): string {
  switch (basis) {
    case 'newest_record':
      return '当前阶段来自最新一条带日期的进展记录'
    case 'explicit':
      return '当前阶段由文档中的“进行中”标记确定'
    case 'derived_completed_prefix':
      return '文档没有标注进行中，当前阶段按“已完成”前缀推定'
    case 'all_completed':
      return '所有阶段都标记为已完成'
    case 'rules_and_model':
      return '规则与模型都指向同一阶段，已互相对照'
    default:
      return ''
  }
}

export function modelStatusLabel(status: string | undefined): string {
  switch (status) {
    case 'ok':
      return '模型已核对'
    case 'invalid':
      return '模型输出未通过校验'
    case 'failed':
      return '模型调用失败'
    case 'skipped':
      return '本次未调用模型'
    default:
      return '未启用模型'
  }
}

export function citationSupportLabel(supports: string): string {
  switch (supports) {
    case 'current_phase':
      return '当前阶段'
    case 'testing':
      return '测试状态'
    case 'summary':
      return '项目简介'
    case 'schedule':
      return '排期日期'
    case 'conflict':
      return '证据冲突'
    case 'phase_status':
      return '阶段状态'
    default:
      return supports
  }
}

export function evidenceKindLabel(kind: string): string {
  switch (kind) {
    case 'progress':
      return '进展记录'
    case 'phase_status':
      return '阶段状态'
    case 'schedule':
      return '排期描述'
    case 'summary':
      return '项目简介'
    default:
      return kind
  }
}

export function fieldLabel(field: string): string {
  return field === 'planned_start' ? '计划开始日期' : field === 'planned_end' ? '计划结束日期' : field
}

export function triggerLabel(trigger: string | undefined): string {
  switch (trigger) {
    case 'auto':
      return '自动巡检'
    case 'cli':
      return '命令行巡检'
    case 'manual':
      return '手动巡检'
    default:
      return '巡检'
  }
}

export function dailyResultLabel(result: string | null | undefined): string {
  switch (result) {
    case 'running':
      return '执行中'
    case 'ok':
      return '成功'
    case 'partial':
      return '部分失败'
    case 'failed':
      return '失败'
    default:
      return '尚未执行'
  }
}
