export interface UserRequest {
    user_id: string;
}

// Types pour les réponses de l'API
export interface QueueStatus {
    status: 'waiting' | 'draft' | 'connected' | 'disconnected';
    position: number;
}

export interface QueueMetrics {
    active_users: number;
    waiting_users: number;
    total_slots: number;
}

export interface TimerInfo {
    timer_type: 'draft' | 'session';
    ttl: number;
    channel?: string;
}

export interface ApiResponse {
    success: boolean;
    position?: number;
    detail?: string;
}

// Type pour le mock de fetch
export interface MockFetch {
    ok: boolean;
    json: () => Promise<QueueStatus | QueueMetrics | TimerInfo | ApiResponse>;
    status?: number;
    statusText?: string;
}