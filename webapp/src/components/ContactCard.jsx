import { useNavigate } from 'react-router-dom'

export default function ContactCard({ share }) {
  const navigate = useNavigate()

  const visibility = share.visibility
  const price = parseFloat(share.price_amount || '0')
  const isPaid = visibility === 'paid' && price > 0
  const isFree = !isPaid

  return (
    <div className="card" onClick={() => navigate(`/contact/${share.id}`)}>
      <div className="card-header">
        <span className="card-name">{share.contact_name || 'Контакт'}</span>
        <span className={`card-badge ${isPaid ? 'badge-paid' : isFree ? 'badge-free' : 'badge-private'}`}>
          {isPaid ? `${share.price_amount} ${share.price_currency}` : visibility === 'private' ? 'Приватный' : 'Бесплатно'}
        </span>
      </div>

      {share.contact_company && (
        <div className="card-meta">{share.contact_company}{share.contact_role ? ` · ${share.contact_role}` : ''}</div>
      )}

      {share.description && (
        <div className="card-meta" style={{ marginTop: 4, fontStyle: 'italic' }}>
          {share.description.length > 80 ? share.description.slice(0, 80) + '...' : share.description}
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8, fontSize: 12, color: 'var(--text-muted)' }}>
        <span>{share.view_count || 0} просмотров</span>
        <span>{share.purchase_count || 0} покупок</span>
      </div>
    </div>
  )
}
