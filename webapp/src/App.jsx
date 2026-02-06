import { useEffect } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { useTelegram } from './hooks/useTelegram'
import { setInitData } from './api/client'
import Header from './components/Header'
import BottomNav from './components/BottomNav'
import CatalogPage from './pages/CatalogPage'
import ContactViewPage from './pages/ContactViewPage'
import MySharesPage from './pages/MySharesPage'
import PurchasesPage from './pages/PurchasesPage'
import SubscribePage from './pages/SubscribePage'
import ProfilePage from './pages/ProfilePage'
import AdminPage from './pages/AdminPage'
import ShareEditorPage from './pages/ShareEditorPage'

export default function App() {
  const { isTelegram, initData, user, showBackButton, hideBackButton } = useTelegram()
  const navigate = useNavigate()
  const location = useLocation()

  // Pass initData to API client
  useEffect(() => {
    if (initData) {
      setInitData(initData)
    }
  }, [initData])

  // Handle TG back button
  useEffect(() => {
    if (!isTelegram) return
    const isRoot = location.pathname === '/' || location.pathname === '/catalog'
    if (!isRoot) {
      const cleanup = showBackButton(() => navigate(-1))
      return cleanup
    } else {
      hideBackButton()
    }
  }, [isTelegram, location.pathname, showBackButton, hideBackButton, navigate])

  return (
    <div className={`app-container ${location.pathname.startsWith('/admin') ? 'wide' : ''}`}>
      <Header isTelegram={isTelegram} user={user} />

      <Routes>
        <Route path="/" element={<CatalogPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/contact/:shareId" element={<ContactViewPage />} />
        <Route path="/s/:token" element={<ContactViewPage byToken />} />
        <Route path="/my-shares" element={<MySharesPage />} />
        <Route path="/my-shares/new" element={<ShareEditorPage />} />
        <Route path="/my-shares/edit/:shareId" element={<ShareEditorPage />} />
        <Route path="/purchases" element={<PurchasesPage />} />
        <Route path="/subscribe" element={<SubscribePage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>

      {!isTelegram && <BottomNav />}
    </div>
  )
}
