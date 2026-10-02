import { useState, useCallback } from 'react'
import Summary from './components/Summary'
import Customers from './components/Customers'
import Reviews from './components/Reviews'
import Audit from './components/Audit'
import Import from './components/Import'

const TABS = [
  ['summary', 'Summary'],
  ['customers', 'Customers'],
  ['reviews', 'Review queue'],
  ['audit', 'Audit log'],
  ['import', 'Import'],
]

export default function App() {
  const [tab, setTab] = useState('summary')
  const [msg, setMsg] = useState('')
  const [steward, setSteward] = useState('')

  const toast = useCallback((m) => {
    setMsg(m)
    setTimeout(() => setMsg(''), 4000)
  }, [])

  const shared = { toast, steward, setSteward }

  return (
    <>
      <div className="app">
        <aside>
          <h1>Customer 360</h1>
          {TABS.map(([k, label]) => (
            <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </aside>
        <main>
          {tab === 'summary' && <Summary toast={toast} />}
          {tab === 'customers' && <Customers {...shared} />}
          {tab === 'reviews' && <Reviews {...shared} />}
          {tab === 'audit' && <Audit toast={toast} />}
          {tab === 'import' && <Import {...shared} />}
        </main>
      </div>
      {msg && (
        <div className="toast" role="status">
          {msg}
        </div>
      )}
    </>
  )
}