export type ImportStatus = 'running' | 'paused' | 'completed' | 'cancelled'
export type ImportOutcome = 'pending' | 'added' | 'upgraded' | 'duplicate' | 'skipped' | 'failed'
export type ImportSummary = {
  id: number; filename: string; status: ImportStatus; total: number; processed: number
  counts: Record<Exclude<ImportOutcome, 'pending'>, number>
  message: string | null; current_title: string | null; created_at: number
}
export type ImportRowsPage = {
  items: { row_number: number; title: string; outcome: ImportOutcome; message: string | null; matched_title: string | null }[]
  total: number; page: number; page_size: number
}
export type DoubanFile = { records: { status?: string; stars?: number | null }[] }

export const outcomeLabels: Record<ImportOutcome, string> = {
  pending: '未处理', added: '新增', upgraded: '转看过', duplicate: '重复', skipped: '跳过', failed: '失败',
}
export const statusLabels: Record<ImportStatus, string> = {
  running: '导入中', paused: '已暂停', completed: '已完成', cancelled: '已结束',
}
