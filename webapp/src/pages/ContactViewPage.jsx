import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getShareById, getShareByToken, purchaseContact } from '../api/client'
import { useTelegram } from '../hooks/useTelegram'

export default function ContactViewPage({ byToken = false }) {
  const { shareId, token } = useParams()
  const navigate = useNavigate()
  const { isTelegram, hapticFeedback, showMainButton } = useTelegram()

  const [share, setShare] = useState(null)
  const [loading, setLoading] = useState(true)
  const [purchasing, setPurchasing] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadShare()
  }, [shareId, token])

  async function loadShare() {
    try {
      setLoading(true)
      const data = byToken
        ? await getShareByToken(token)
        : await getShareById(shareId)
      setShare(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const handlePurchase = useCallback(async (provider = 'free') => {
    if (!share) return
    try {
      setPurchasing(true)
      hapticFeedback('medium')
      await purchaseContact(share.id, provider)
      hapticFeedback('success')
      // Reload to show updated state
      await loadShare()
    } catch (e) {
      setError(e.message)
    } finally {
      setPurchasing(false)
    }
  }, [share, hapticFeedback])

  // Telegram main button for purchase
  useEffect(() => {
    if (!isTelegram || !share) return
    if (share.already_purchased || share.is_owner) return

    const isPaid = share.visibility === 'paid' && parseFloat(share.price_amount || '0') > 0
    const label = isPaid ? `Купить за ${share.price_amount} ${share.price_currency}` : 'Добавить в контакты'

    return showMainButton(label, () => handlePurchase(isPaid ? 'telegram' : 'free'))
  }, [isTelegram, share, showMainButton, handlePurchase])

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>
  if (error) return <div className="content"><div className="empty-state"><div className="empty-state-text">{error}</div></div></div>
  if (!share) return <div className="content"><div className="empty-state"><div className="empty-state-text">Контакт не найден</div></div></div>

  const data = share.contact_data || {}
  const isPaid = share.visibility === 'paid' && parseFloat(share.price_amount || '0') > 0
  const canSeeDetails = share.already_purchased || share.is_owner || share.visibility === 'public'

  return (
    <div className="content">
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'var(--accent-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: 28 }}>
          {(data.name || '?')[0]?.toUpperCase()}
        </div>
        <h2 style={{ fontSize: 22, marginBottom: 4 }}>{data.name || 'Контакт'}</h2>
        {data.company && (
          <div style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
            {data.company}{data.role ? ` · ${data.role}` : ''}
          </div>
        )}
      </div>

      {share.description && (
        <div style={{ background: 'var(--bg-card)', padding: 12, borderRadius: 'var(--radius-sm)', marginBottom: 16, fontStyle: 'italic', fontSize: 14, color: 'var(--text-secondary)' }}>
          {share.description}
        </div>
      )}

      {data.what_looking_for && (
        <>
          <div className="section-title">Ищет</div>
          <div style={{ marginBottom: 16, fontSize: 14 }}>{data.what_looking_for}</div>
        </>
      )}

      {data.can_help_with && (
        <>
          <div className="section-title">Может помочь</div>
          <div style={{ marginBottom: 16, fontSize: 14 }}>{data.can_help_with}</div>
        </>
      )}

      {data.topics && data.topics.length > 0 && (
        <>
          <div className="section-title">Темы</div>
          <div className="card-tags" style={{ marginBottom: 16 }}>
            {data.topics.map((t, i) => <span key={i} className="tag">{t}</span>)}
          </div>
        </>
      )}

      <div className="section-title">Контактные данные</div>
      {canSeeDetails ? (
        <div>
          {data.phone && <div className="contact-field"><span className="contact-field-label">Телефон</span><span className="contact-field-value"><a href={`tel:${data.phone}`}>{data.phone}</a></span></div>}
          {data.email && <div className="contact-field"><span className="contact-field-label">Email</span><span className="contact-field-value"><a href={`mailto:${data.email}`}>{data.email}</a></span></div>}
          {data.telegram_username && <div className="contact-field"><span className="contact-field-label">Telegram</span><span className="contact-field-value"><a href={`https://t.me/${data.telegram_username.replace('@', '')}`} target="_blank" rel="noreferrer">@{data.telegram_username.replace('@', '')}</a></span></div>}
          {data.linkedin_url && <div className="contact-field"><span className="contact-field-label">LinkedIn</span><span className="contact-field-value"><a href={data.linkedin_url} target="_blank" rel="noreferrer">Профиль</a></span></div>}
          {!data.phone && !data.email && !data.telegram_username && !data.linkedin_url && (
            <div style={{ color: 'var(--text-muted)', fontSize: 14, padding: '8px 0' }}>Нет контактных данных</div>
          )}
        </div>
      ) : (
        <div style={{ background: 'var(--accent-light)', padding: 16, borderRadius: 'var(--radius)', textAlign: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 24, marginBottom: 8 }}>🔒</div>
          <div style={{ fontSize: 14, marginBottom: 8 }}>Контактные данные доступны после покупки</div>
          {isPaid && <div className="price">{share.price_amount} {share.price_currency}</div>}
        </div>
      )}

      {share.already_purchased && (
        <div style={{ background: 'rgba(52, 199, 89, 0.1)', padding: 12, borderRadius: 'var(--radius-sm)', textAlign: 'center', marginTop: 16, color: 'var(--success)', fontSize: 14 }}>
          Вы уже приобрели этот контакт
        </div>
      )}

      {/* Web buttons (not shown in TG - main button is used instead) */}
      {!isTelegram && !share.already_purchased && !share.is_owner && (
        <div style={{ marginTop: 20 }}>
          {isPaid ? (
            <>
              <button className="btn btn-primary" onClick={() => handlePurchase('yookassa')} disabled={purchasing}>
                {purchasing ? 'Обработка...' : `Купить за ${share.price_amount} ${share.price_currency}`}
              </button>
            </>
          ) : (
            <button className="btn btn-primary" onClick={() => handlePurchase('free')} disabled={purchasing}>
              {purchasing ? 'Добавление...' : 'Добавить в мои контакты'}
            </button>
          )}
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={() => navigate('/catalog')}>
          Назад к каталогу
        </button>
      </div>
    </div>
  )
}
