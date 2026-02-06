import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getMyContacts, getShareById, createShare, updateShare } from '../api/client'

const ALL_FIELDS = [
  { key: 'name', label: 'Имя' },
  { key: 'company', label: 'Компания' },
  { key: 'role', label: 'Роль' },
  { key: 'phone', label: 'Телефон' },
  { key: 'email', label: 'Email' },
  { key: 'telegram_username', label: 'Telegram' },
  { key: 'linkedin_url', label: 'LinkedIn' },
  { key: 'what_looking_for', label: 'Ищет' },
  { key: 'can_help_with', label: 'Может помочь' },
  { key: 'topics', label: 'Темы' },
  { key: 'event_name', label: 'Событие' },
]

export default function ShareEditorPage() {
  const { shareId } = useParams()
  const navigate = useNavigate()
  const isEdit = !!shareId

  const [contacts, setContacts] = useState([])
  const [selectedContactId, setSelectedContactId] = useState('')
  const [visibility, setVisibility] = useState('public')
  const [visibleFields, setVisibleFields] = useState(['name', 'company', 'role', 'what_looking_for', 'can_help_with', 'topics'])
  const [price, setPrice] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadData()
  }, [shareId])

  async function loadData() {
    try {
      setLoading(true)
      if (isEdit) {
        const share = await getShareById(shareId)
        setSelectedContactId(share.contact_id)
        setVisibility(share.visibility || 'public')
        setVisibleFields(share.visible_fields || [])
        setPrice(share.price_amount || '')
        setDescription(share.description || '')
      }
      const contactsData = await getMyContacts()
      setContacts(contactsData.contacts || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  function toggleField(key) {
    setVisibleFields(prev =>
      prev.includes(key) ? prev.filter(f => f !== key) : [...prev, key]
    )
  }

  async function handleSave() {
    if (!selectedContactId) {
      alert('Выберите контакт')
      return
    }
    try {
      setSaving(true)
      const payload = {
        contact_id: selectedContactId,
        visibility,
        visible_fields: visibleFields,
        price_amount: visibility === 'paid' ? price : '0',
        price_currency: 'RUB',
        description,
      }
      if (isEdit) {
        await updateShare(shareId, payload)
      } else {
        await createShare(selectedContactId, payload)
      }
      navigate('/my-shares')
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="content"><div className="loading"><div className="spinner" /></div></div>

  return (
    <div className="content">
      <div className="section-title">{isEdit ? 'Настройка публикации' : 'Новая публикация'}</div>

      {!isEdit && (
        <div className="form-group">
          <label className="form-label">Контакт</label>
          <select className="form-select" value={selectedContactId} onChange={e => setSelectedContactId(e.target.value)}>
            <option value="">Выберите контакт...</option>
            {contacts.map(c => (
              <option key={c.id} value={c.id}>
                {c.name}{c.company ? ` (${c.company})` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="form-group">
        <label className="form-label">Видимость</label>
        <select className="form-select" value={visibility} onChange={e => setVisibility(e.target.value)}>
          <option value="public">Публичный (все видят бесплатно)</option>
          <option value="paid">Платный (контакты за оплату)</option>
          <option value="private">Приватный (по ссылке)</option>
        </select>
      </div>

      {visibility === 'paid' && (
        <div className="form-group">
          <label className="form-label">Цена (RUB)</label>
          <input
            className="form-input"
            type="number"
            min="0"
            placeholder="500"
            value={price}
            onChange={e => setPrice(e.target.value)}
          />
        </div>
      )}

      <div className="form-group">
        <label className="form-label">Описание (необязательно)</label>
        <input
          className="form-input"
          placeholder="Коротко о контакте..."
          value={description}
          onChange={e => setDescription(e.target.value)}
        />
      </div>

      <div className="section-title">Видимые поля</div>
      <div style={{ marginBottom: 16 }}>
        {ALL_FIELDS.map(f => (
          <div key={f.key} className="toggle-row">
            <span className="toggle-label">{f.label}</span>
            <button
              className={`toggle ${visibleFields.includes(f.key) ? 'active' : ''}`}
              onClick={() => toggleField(f.key)}
            />
          </div>
        ))}
      </div>

      <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
        {saving ? 'Сохранение...' : isEdit ? 'Сохранить' : 'Опубликовать'}
      </button>
      <button className="btn btn-secondary" onClick={() => navigate('/my-shares')}>
        Отмена
      </button>
    </div>
  )
}
