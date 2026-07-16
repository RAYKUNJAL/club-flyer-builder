import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Audit() {
  const [events, setEvents] = useState<any[]>([])
  const [verify, setVerify] = useState<any>(null)

  useEffect(() => {
    api.get('/v1/audit-events?limit=200').then(setEvents)
    api.get('/v1/audit-events/verify').then(setVerify)
  }, [])

  return (
    <div>
      <h2>
        Immutable audit log{' '}
        {verify &&
          (verify.valid ? (
            <span className="chip ok">hash chain verified ({verify.count} events)</span>
          ) : (
            <span className="chip bad">CHAIN BROKEN at seq {verify.broken_at_seq}</span>
          ))}
      </h2>
      <div className="panel">
        <table>
          <thead>
            <tr><th>#</th><th>When (UTC)</th><th>Action</th><th>Entity</th><th>Payload</th></tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td>{e.seq}</td>
                <td>{e.created_at?.replace('T', ' ').slice(0, 19)}</td>
                <td>{e.action}</td>
                <td>{e.entity_type}</td>
                <td style={{ fontSize: '0.72rem', color: 'var(--muted)', maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {e.payload ? JSON.stringify(e.payload) : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
