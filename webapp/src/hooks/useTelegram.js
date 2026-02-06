import { useState, useEffect, useCallback } from 'react'

/**
 * Hook to interact with Telegram WebApp SDK.
 * Returns null values when running as a regular website.
 */
export function useTelegram() {
  const [webApp, setWebApp] = useState(null)
  const [user, setUser] = useState(null)
  const [isTelegram, setIsTelegram] = useState(false)
  const [colorScheme, setColorScheme] = useState('dark')
  const [initData, setInitData] = useState('')

  useEffect(() => {
    const tg = window.Telegram?.WebApp
    if (tg && tg.initData) {
      tg.ready()
      tg.expand()
      tg.enableClosingConfirmation?.()

      setWebApp(tg)
      setUser(tg.initDataUnsafe?.user || null)
      setIsTelegram(true)
      setColorScheme(tg.colorScheme || 'dark')
      setInitData(tg.initData)

      // Apply TG theme class
      document.body.classList.add('tg-theme')

      // Listen for theme changes
      const handleThemeChanged = () => {
        setColorScheme(tg.colorScheme || 'dark')
      }
      tg.onEvent?.('themeChanged', handleThemeChanged)

      return () => {
        tg.offEvent?.('themeChanged', handleThemeChanged)
        document.body.classList.remove('tg-theme')
      }
    }
  }, [])

  const showMainButton = useCallback((text, onClick) => {
    if (!webApp) return
    webApp.MainButton.setText(text)
    webApp.MainButton.show()
    webApp.MainButton.onClick(onClick)
    return () => {
      webApp.MainButton.offClick(onClick)
      webApp.MainButton.hide()
    }
  }, [webApp])

  const showBackButton = useCallback((onClick) => {
    if (!webApp) return
    webApp.BackButton.show()
    webApp.BackButton.onClick(onClick)
    return () => {
      webApp.BackButton.offClick(onClick)
      webApp.BackButton.hide()
    }
  }, [webApp])

  const hideBackButton = useCallback(() => {
    if (!webApp) return
    webApp.BackButton.hide()
  }, [webApp])

  const hapticFeedback = useCallback((type = 'light') => {
    if (!webApp?.HapticFeedback) return
    webApp.HapticFeedback.impactOccurred(type)
  }, [webApp])

  const close = useCallback(() => {
    if (webApp) webApp.close()
  }, [webApp])

  const openInvoice = useCallback((url, callback) => {
    if (!webApp?.openInvoice) return false
    webApp.openInvoice(url, callback)
    return true
  }, [webApp])

  return {
    webApp,
    user,
    isTelegram,
    colorScheme,
    initData,
    showMainButton,
    showBackButton,
    hideBackButton,
    hapticFeedback,
    close,
    openInvoice,
  }
}

export default useTelegram
