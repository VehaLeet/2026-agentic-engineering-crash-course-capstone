import type { Tab } from '../lib/tab.ts'

const LABELS: Record<Tab, string> = { data: 'Дані', settings: 'Налаштування' }

export function Tabs({ tab, onSelect }: { tab: Tab; onSelect: (tab: Tab) => void }) {
  return (
    <nav className="tabs" role="tablist" aria-label="Розділи">
      {(Object.keys(LABELS) as Tab[]).map((id) => (
        <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => onSelect(id)}>
          {LABELS[id]}
        </button>
      ))}
    </nav>
  )
}
