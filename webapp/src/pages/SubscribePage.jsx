import { useState, useEffect } from 'react'
import { getSubscription, createSubscriptionPayment } from '../api/client'
import { useTelegram } from '../hooks/useTelegram'

export default function SubscribePage() {
  const [subscription, setSubscription] = useState(null)
  const [loading, setLoading] = useState(true)
  const [paying, setPaying] = useState(false)
  const { isTelegram } = useTelegram()

  useEffect(() => { loadSubscription() }, [])

  async function loadSubscription() {
    try {
      setLoading(true)
      const data = await getSubscription()
      setSubscription(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  async function handlePay(provider) {
    try {
      setPaying(true)
      const result = await createSubscriptionPayment(provider)
      if (result.confirmation_url) {
        window.open(result.confirmation_url, '_blank')
      } else if (result.invoice_url && isTelegram) {
        window.Telegram?.WebApp?.openInvoice?.(result.invoice_url)
      }
    } catch (e) {
      alert(e.message)
    } finally {
      setPaying(false)
    }
  }

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>

  const isActive = subscription?.status === 'active'

  return (
    <div className="content">
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>{isActive ? '✅' : '💳'}</div>
        <h2 style={{ fontSize: 22 }}>Подписка Seller</h2>
      </div>

      {isActive ? (
        <>
          <div className="card" style={{ textAlign: 'center', cursor: 'default' }}>
            <div style={{ color: 'var(--success)', fontWeight: 600, marginBottom: 8 }}>Активна</div>
            <div className="card-meta">План: {subscription.plan}</div>
            <div className="card-meta">
              Действует до: {subscription.period_end ? new Date(subscription.period_end).toLocaleDateString('ru-RU') : '—'}
            </div>
            <div className="card-meta">
              Оплата: {subscription.price_amount} {subscription.price_currency}/мес
            </div>
          </div>

          <div className="section-title">Возможности</div>
          <div style={{ fontSize: 14, lineHeight: 2 }}>
            ✅ Публикация контактов для продажи<br />
            ✅ Настройка видимости полей<br />
            ✅ Получение оплаты за контакты<br />
            ✅ Публичный профиль в каталоге
          </div>
        </>
      ) : (
        <>
          <div className="card" style={{ textAlign: 'center', cursor: 'default' }}>
            <div className="price" style={{ marginBottom: 8 }}>990 ₽/мес</div>
            <div className="card-meta">или 500 Telegram Stars</div>
          </div>

          <div className="section-title">Что дает подписка</div>
          <div style={{ fontSize: 14, lineHeight: 2, marginBottom: 24 }}>
            📢 Публикация контактов для продажи<br />
            🔒 Настройка видимости каждого поля<br />
            💰 Получение оплаты за контакты<br />
            👤 Публичный профиль в каталоге
          </div>

          <button className="btn btn-primary" onClick={() => handlePay('yookassa')} disabled={paying}>
            {paying ? 'Обработка...' : 'Оплатить 990 ₽ (карта)'}
          </button>

          {isTelegram && (
            <button className="btn btn-secondary" onClick={() => handlePay('telegram')} disabled={paying}>
              Оплатить 500 Stars
            </button>
          )}
        </>
      )}
    </div>
  )
}
