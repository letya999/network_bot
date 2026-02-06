import { useLocation, useNavigate } from 'react-router-dom'

const tabs = [
  { path: '/catalog', icon: '🔍', label: 'Каталог' },
  { path: '/my-shares', icon: '📢', label: 'Мои' },
  { path: '/purchases', icon: '🛍', label: 'Покупки' },
  { path: '/subscribe', icon: '💳', label: 'Подписка' },
  { path: '/profile', icon: '👤', label: 'Профиль' },
]

export default function BottomNav() {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <nav className="bottom-nav">
      <div className="bottom-nav-inner">
        {tabs.map((tab) => (
          <button
            key={tab.path}
            className={`bottom-nav-item ${location.pathname === tab.path || (tab.path === '/catalog' && location.pathname === '/') ? 'active' : ''}`}
            onClick={() => navigate(tab.path)}
          >
            <span className="bottom-nav-icon">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>
    </nav>
  )
}
