import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyShares, deleteShare } from '../api/client'

export default function MySharesPage() {
  const [shares, setShares] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => { loadShares() }, [])

  async function loadShares() {
    try {
      setLoading(true)
      const data = await getMyShares()
      setShares(data.shares || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(shareId) {
    if (!confirm('Снять с публикации?')) return
    try {
      await deleteShare(shareId)
      setShares(prev => prev.filter(s => s.id !== shareId))
    } catch (e) {
      alert(e.message)
    }
  }

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>

  return (
    <div className="content">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div className="section-title" style={{ margin: 0 }}>Мои публикации</div>
        <button className="btn btn-primary btn-sm" onClick={() => navigate('/my-shares/new')}>
          + Опубликовать
        </button>
      </div>

      {shares.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📭</div>
          <div className="empty-state-text">Вы еще не опубликовали ни одного контакта</div>
          <button className="btn btn-primary" onClick={() => navigate('/my-shares/new')}>
            Опубликовать контакт
          </button>
        </div>
      )}

      {shares.map((share) => (
        <div key={share.id} className="card" style={{ cursor: 'default' }}>
          <div className="card-header">
            <span className="card-name">{share.contact_name || 'Контакт'}</span>
            <span className={`card-badge ${share.visibility === 'paid' ? 'badge-paid' : share.visibility === 'private' ? 'badge-private' : 'badge-free'}`}>
              {share.visibility === 'paid' ? `${share.price_amount} ${share.price_currency}` : share.visibility === 'private' ? 'Приватный' : 'Публичный'}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
            <span>{share.view_count || 0} просмотров</span>
            <span>·</span>
            <span>{share.purchase_count || 0} покупок</span>
            <span>·</span>
            <span>{(share.visible_fields || []).length} полей видно</span>
          </div>

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn btn-secondary btn-sm" onClick={() => navigate(`/my-shares/edit/${share.id}`)}>
              Настроить
            </button>
            <button className="btn btn-danger btn-sm" onClick={() => handleDelete(share.id)}>
              Снять
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
