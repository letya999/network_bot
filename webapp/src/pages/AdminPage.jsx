import { useState, useEffect } from 'react'
import { getAdminStats, getAdminUsers, getAdminPayments } from '../api/client'

export default function AdminPage() {
  const [tab, setTab] = useState('stats')
  const [stats, setStats] = useState(null)
  const [users, setUsers] = useState([])
  const [payments, setPayments] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => { loadTab(tab) }, [tab])

  async function loadTab(t) {
    try {
      setLoading(true)
      if (t === 'stats') {
        setStats(await getAdminStats())
      } else if (t === 'users') {
        const data = await getAdminUsers()
        setUsers(data || [])
      } else if (t === 'payments') {
        const data = await getAdminPayments()
        setPayments(data || [])
      }
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="content">
      <div className="section-title">Админ-панель</div>

      <div className="nav-tabs" style={{ borderRadius: 'var(--radius-sm)', overflow: 'hidden', marginBottom: 16 }}>
        {['stats', 'users', 'payments'].map(t => (
          <button key={t} className={`nav-tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {t === 'stats' ? 'Статистика' : t === 'users' ? 'Пользователи' : 'Платежи'}
          </button>
        ))}
      </div>

      {loading && <div className="loading"><div className="spinner" /></div>}

      {!loading && tab === 'stats' && stats && (
        <div className="stats-grid">
          <div className="stat-card"><div className="stat-value">{stats.users}</div><div className="stat-label">Пользователей</div></div>
          <div className="stat-card"><div className="stat-value">{stats.contacts}</div><div className="stat-label">Контактов</div></div>
          <div className="stat-card"><div className="stat-value">{stats.active_subscriptions}</div><div className="stat-label">Подписок</div></div>
          <div className="stat-card"><div className="stat-value">{stats.active_shares}</div><div className="stat-label">Публикаций</div></div>
          <div className="stat-card"><div className="stat-value">{stats.successful_payments}</div><div className="stat-label">Платежей</div></div>
          <div className="stat-card"><div className="stat-value">{stats.revenue_rub?.toLocaleString()} ₽</div><div className="stat-label">Выручка</div></div>
        </div>
      )}

      {!loading && tab === 'users' && (
        <div>
          {users.map(u => (
            <div key={u.id} className="card" style={{ cursor: 'default' }}>
              <div className="card-name">{u.name || '—'}</div>
              <div className="card-meta">
                {u.username ? `@${u.username}` : ''} · TG: {u.telegram_id}
              </div>
              <div className="card-meta">{u.created_at ? new Date(u.created_at).toLocaleDateString('ru-RU') : ''}</div>
            </div>
          ))}
        </div>
      )}

      {!loading && tab === 'payments' && (
        <div>
          {payments.map(p => (
            <div key={p.id} className="card" style={{ cursor: 'default' }}>
              <div className="card-header">
                <span className="card-name">{p.type}</span>
                <span className={`card-badge ${p.status === 'succeeded' ? 'badge-free' : 'badge-paid'}`}>{p.status}</span>
              </div>
              <div className="card-meta">{p.amount} · {p.provider}</div>
              <div className="card-meta">{p.created_at ? new Date(p.created_at).toLocaleDateString('ru-RU') : ''}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
