import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getProfile } from '../api/client'
import { useTelegram } from '../hooks/useTelegram'

export default function ProfilePage() {
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const { isTelegram, user } = useTelegram()
  const navigate = useNavigate()

  useEffect(() => { loadProfile() }, [])

  async function loadProfile() {
    try {
      setLoading(true)
      const data = await getProfile()
      setProfile(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>

  const name = profile?.name || user?.first_name || 'Пользователь'

  return (
    <div className="content">
      <div style={{ textAlign: 'center', marginBottom: 24 }}>
        <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'var(--accent-light)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 12px', fontSize: 32 }}>
          {name[0]?.toUpperCase()}
        </div>
        <h2 style={{ fontSize: 22 }}>{name}</h2>
        {profile?.company && (
          <div style={{ color: 'var(--text-secondary)' }}>
            {profile.job_title ? `${profile.job_title} @ ` : ''}{profile.company}
          </div>
        )}
      </div>

      {profile?.bio && (
        <div style={{ background: 'var(--bg-card)', padding: 12, borderRadius: 'var(--radius-sm)', marginBottom: 16, fontStyle: 'italic', fontSize: 14 }}>
          {profile.bio}
        </div>
      )}

      <div className="section-title">Статистика</div>
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{profile?.contacts_count || 0}</div>
          <div className="stat-label">Контактов</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{profile?.shares_count || 0}</div>
          <div className="stat-label">Публикаций</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{profile?.purchases_count || 0}</div>
          <div className="stat-label">Покупок</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{profile?.subscription_active ? '✅' : '—'}</div>
          <div className="stat-label">Подписка</div>
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={() => navigate('/my-shares')}>
          Мои публикации
        </button>
        <button className="btn btn-secondary" onClick={() => navigate('/purchases')}>
          Мои покупки
        </button>
        {profile?.is_admin && (
          <button className="btn btn-secondary" onClick={() => navigate('/admin')}>
            Админ-панель
          </button>
        )}
      </div>
    </div>
  )
}
