import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import Detail from './Detail'

const N = 50

export default function Customers({ toast, steward, setSteward }) {
  const [q, setQ] = useState('')
  const [list, setList] = useState([])
  const [sel, setSel] = useState(null)
  const [d, setD] = useState(null)
  const [page, setPage] = useState(0)
  const [low, setLow] = useState(false)

  const search = useCallback(
    () =>
      api(
        `/customers?limit=${N}&offset=${page * N}${low ? '&quality_below=100' : ''}&q=` +
          encodeURIComponent(q)
      )
        .then(setList)
        .catch((e) => toast(e.message)),
    [q, page, low, toast]
  )

  useEffect(() => {
    const t = setTimeout(search, 250)
    return () => clearTimeout(t)
  }, [search])

  const open = (id) => {
    setSel(id)
    api('/customers/' + id)
      .then(setD)
      .catch((e) => toast(e.message))
  }

  return (
    <div className="grid">
      <div className="panel">
        <input
          style={{ width: '100%', marginBottom: 10 }}
          placeholder="Search name, email, phone, ID…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setPage(0)
          }}
        />
        <div className="mute" style={{ marginBottom: 6 }}>
          <label className="row" style={{ marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={low}
              onChange={(e) => {
                setLow(e.target.checked)
                setPage(0)
              }}
            />{' '}
            Only records with quality below 100
          </label>
          <div className="row">
            <button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <button className="btn" disabled={list.length < N} onClick={() => setPage(page + 1)}>
              Next
            </button>
            <span>
              Rows {list.length ? page * N + 1 : 0} to {page * N + list.length}
            </span>
          </div>
        </div>
        <div className="scroll" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th className="num">Score</th>
                <th className="num">Txns</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr
                  key={c.golden_id}
                  className={'click ' + (sel === c.golden_id ? 'sel' : '')}
                  onClick={() => open(c.golden_id)}
                >
                  <td>{c.golden_id}</td>
                  <td>{c.name}</td>
                  <td className="num">{c.quality_score}</td>
                  <td className="num">{c.txn_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {d ? (
        <Detail
          key={d.golden.golden_id}
          d={d}
          reload={() => open(sel)}
          toast={toast}
          steward={steward}
          setSteward={setSteward}
        />
      ) : (
        <div className="panel mute">
          Select a customer to see their sources, lineage and transactions.
        </div>
      )}
    </div>
  )
}