import { Link } from 'react-router-dom'

export default function Header({ isTelegram, user }) {
  // In Telegram Mini App, keep header minimal (TG provides its own header)
  if (isTelegram) {
    return null
  }

  return (
    <header className="header">
      <Link to="/" style={{ textDecoration: 'none', color: 'inherit' }}>
        <h1>NetworkBot</h1>
      </Link>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {user && (
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
            {user.first_name}
          </span>
        )}
      </div>
    </header>
  )
}
