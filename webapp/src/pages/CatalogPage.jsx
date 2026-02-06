import { useState, useEffect } from 'react'
import { getCatalog } from '../api/client'
import ContactCard from '../components/ContactCard'

export default function CatalogPage() {
  const [shares, setShares] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadCatalog()
  }, [])

  async function loadCatalog() {
    try {
      setLoading(true)
      const data = await getCatalog()
      setShares(data.shares || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="content">
      <div className="section-title">Каталог контактов</div>

      {loading && (
        <div className="loading"><div className="spinner" /></div>
      )}

      {error && (
        <div className="empty-state">
          <div className="empty-state-text">Ошибка загрузки: {error}</div>
          <button className="btn btn-secondary btn-sm" onClick={loadCatalog}>Повторить</button>
        </div>
      )}

      {!loading && !error && shares.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📭</div>
          <div className="empty-state-text">Пока нет доступных контактов</div>
        </div>
      )}

      {shares.map((share) => (
        <ContactCard key={share.id} share={share} />
      ))}
    </div>
  )
}
