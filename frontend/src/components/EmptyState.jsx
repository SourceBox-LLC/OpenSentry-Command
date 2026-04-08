import LoadingSpinner from './LoadingSpinner'

function EmptyState({ icon, title, message, children }) {
    return (
        <div className="empty-state">
            {icon && <div className="empty-icon">{icon}</div>}
            {title && <h3>{title}</h3>}
            {message && <p>{message}</p>}
            {children}
        </div>
    )
}

function DiscoveringState() {
    return (
        <EmptyState 
            icon="📹"
            title="No Camera Nodes Found"
            message="Go to Settings to add and configure your OpenSentry camera nodes."
        />
    )
}

function NoCamerasState() {
    return (
        <EmptyState 
            icon="📹"
            title="No Cameras Found"
            message="Connect OpenSentry camera nodes to your network to get started."
        />
    )
}

export { EmptyState, DiscoveringState, NoCamerasState }
export default EmptyState