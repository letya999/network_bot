import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyPurchases } from '../api/client'

export default function PurchasesPage() {
  const [purchases, setPurchases] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => { loadPurchases() }, [])

  async function loadPurchases() {
    try {
      setLoading(true)
      const data = await getMyPurchases()
      setPurchases(data.purchases || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>

  return (
    <div className="content">
      <div className="section-title">Мои покупки</div>

      {purchases.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🛍</div>
          <div className="empty-state-text">Вы пока не приобрели ни одного контакта</div>
          <button className="btn btn-primary" onClick={() => navigate('/catalog')}>
            Перейти в каталог
          </button>
        </div>
      )}

      {purchases.map((p) => (
        <div key={p.id} className="card" onClick={() => p.copied_contact_id && navigate(`/contact/${p.share_id}`)}>
          <div className="card-header">
            <span className="card-name">{p.contact_name || 'Контакт'}</span>
            <span className={`card-badge ${p.amount_paid === '0' ? 'badge-free' : 'badge-paid'}`}>
              {p.amount_paid === '0' ? 'Бесплатно' : `${p.amount_paid} ${p.currency}`}
            </span>
          </div>
          {p.seller_name && (
            <div className="card-meta">Продавец: {p.seller_name}</div>
          )}
          <div className="card-meta">
            {new Date(p.created_at).toLocaleDateString('ru-RU')}
          </div>
        </div>
      ))}
    </div>
  )
}
