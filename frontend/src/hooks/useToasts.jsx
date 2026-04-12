import { createContext, useContext, useState, useCallback } from 'react'

const ToastContext = createContext(null)

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([])

    const showToast = useCallback((message, type = 'success', durationMs = 3000) => {
        const id = Date.now()
        const toast = { id, message, type }

        setToasts(prev => [...prev, toast])

        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id))
        }, durationMs)

        return id
    }, [])

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id))
    }, [])

    return (
        <ToastContext.Provider value={{ toasts, showToast, removeToast }}>
            {children}
        </ToastContext.Provider>
    )
}

export function useToasts() {
    const context = useContext(ToastContext)
    if (!context) {
        throw new Error('useToasts must be used within ToastProvider')
    }
    return context
}

export default ToastContext