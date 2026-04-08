import { useToasts } from '../hooks/useToasts.jsx'

function ToastContainer() {
    const { toasts, removeToast } = useToasts()
    
    const getIcon = (type) => {
        switch (type) {
            case 'success': return '✓'
            case 'error': return '✕'
            case 'warning': return '⚠'
            case 'info': return 'ℹ'
            default: return '•'
        }
    }

    return (
        <div className="toast-container">
            {toasts.map(toast => (
                <div 
                    key={toast.id} 
                    className={`toast ${toast.type}`}
                    onClick={() => removeToast(toast.id)}
                    style={{ cursor: 'pointer' }}
                >
                    <div className="toast-icon">
                        {getIcon(toast.type)}
                    </div>
                    <div className="toast-message">
                        {toast.message}
                    </div>
                </div>
            ))}
        </div>
    )
}

export default ToastContainer