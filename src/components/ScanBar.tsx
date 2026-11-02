import type { ScanRun } from '../types'
import { timestampLabel, triggerLabel } from '../lib/format'

type Props = {
  run: ScanRun | null
  scanning: boolean
  projectCount: number
  modelEnabled: boolean
  onScan: () => void
}

const changeText = (kind: string, previous: string | null, current: string | null) => {
  if (kind === 'phase') return `${previous || '未知'} → ${current || '未知'}`
  if (kind === 'record') return `最新进展 ${previous || '无'} → ${current || '无'}`
  return `${previous || '无'} → ${current || '无'}`
}

export default function ScanBar({ run, scanning, projectCount, modelEnabled, onScan }: Props) {
  const failed = (run?.projects_failed ?? 0) > 0 || (run?.projects_model_error ?? 0) > 0 || run?.result === 'failed'
  const changed = run?.changes ?? []
  const modelFailed = run?.model_failed ?? 0

  return (
    <section className={`scan-bar ${failed ? 'scan-bar-warn' : ''}`}>
      <div className="scan-main">
        <div className="scan-headline">
          <span className={`scan-dot ${run ? (failed ? 'dot-warn' : 'dot-ok') : 'dot-idle'}`} />
          <strong>
            {run
              ? failed
                ? `巡检有失败项 · ${run.message}`
                : changed.length
                  ? `本次巡检发现 ${changed.length} 项变化`
                  : '项目状态无更新'
              : '尚未巡检'}
          </strong>
          <span className="scan-time">
            {run
              ? `${triggerLabel(run.trigger)} · ${timestampLabel(run.finished_at || run.started_at)}`
              : `共 ${projectCount} 个项目待扫描`}
          </span>
        </div>
        {run && (
          <div className="scan-meta">
            <span>已同步 {run.projects_ok}</span>
            {run.projects_needing_confirmation > 0 && <span>待确认 {run.projects_needing_confirmation}</span>}
            {run.projects_unknown > 0 && <span>阶段未知 {run.projects_unknown}</span>}
            {run.projects_failed > 0 && <span>读取失败 {run.projects_failed}</span>}
            {modelFailed > 0 && <span className="meta-alert">模型失败 {modelFailed}</span>}
            {failed && <span className="meta-alert">失败时间 {timestampLabel(run.finished_at || run.started_at)}</span>}
            {run.schedule_proposals > 0 && <span>排期变更 {run.schedule_proposals}</span>}
            <span>{run.model_enabled ? `模型核对 ${run.model_ok ?? 0}` : '仅本地规则'}</span>
          </div>
        )}
        {changed.length > 0 && (
          <ul className="scan-changes">
            {changed.slice(0, 3).map((change, index) => (
              <li key={`${change.project_id}-${change.kind}-${index}`}>
                <b>{change.project_name}</b>
                {change.kind === 'phase' ? ' 阶段 ' : change.kind === 'record' ? ' ' : ' 状态 '}
                {changeText(change.kind, change.previous, change.current)}
              </li>
            ))}
            {changed.length > 3 && <li className="scan-more">另有 {changed.length - 3} 项变化</li>}
          </ul>
        )}
      </div>
      <button className="primary-button scan-button" onClick={onScan} disabled={scanning}>
        {scanning ? '巡检中…' : failed ? '重试巡检' : modelEnabled ? '立即复核' : '立即巡检'}
      </button>
    </section>
  )
}
