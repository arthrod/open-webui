// Imports
// import { QUEUE_API_BASE_URL } from '$lib/constants';
import type { QueueMetrics, QueueStatus, TimerInfo, UserRequest } from './types';

// Utility function to handle fetch errors
const handleFetchError = (error: unknown) => {
    console.error('Detailed error:', error);
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
        throw new Error('The server is not available');
    }
    throw error;
};

const QUEUE_API_BASE_URL = "http://localhost:8000/queue"

// Join Queue
export const joinQueue = async (userRequest: UserRequest): Promise<{ position: number }> => {
    try {
        console.log('Attempting joinQueue with:', userRequest);
        const response = await fetch(`${QUEUE_API_BASE_URL}/join`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(userRequest),
        });

        console.log('joinQueue response:', response.status);
        if (!response.ok) {
            const error = await response.json();
            console.error('joinQueue error:', error);
            throw new Error(error.detail);
        }

        const data = await response.json();
        console.log('joinQueue data:', data);
        return data;
    } catch (error) {
        console.error('joinQueue exception:', error);
        handleFetchError(error);
        throw error;
    }
};

// Leave Queue
export const leaveQueue = async (userRequest: UserRequest): Promise<{ success: boolean }> => {
    const response = await fetch(`${QUEUE_API_BASE_URL}/leave`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(userRequest),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
    }

    return await response.json();
};

// Confirm Connection
export const confirmConnection = async (userRequest: UserRequest): Promise<{ session_duration: number }> => {
    const response = await fetch(`${QUEUE_API_BASE_URL}/confirm`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(userRequest),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
    }

    return await response.json();
};

// Get Status
export const getStatus = async (userId: string): Promise<QueueStatus> => {
    try {
        console.log('Attempting getStatus for:', userId);
        const response = await fetch(`${QUEUE_API_BASE_URL}/status/${userId}`, {
            method: 'GET',
        });

        console.log('getStatus response:', response.status);
        if (!response.ok) {
            const error = await response.json();
            console.error('getStatus error:', error);
            throw new Error(error.detail);
        }

        const data = await response.json();
        console.log('getStatus data:', data);
        return data;
    } catch (error) {
        console.error('getStatus exception:', error);
        handleFetchError(error);
        throw error;
    }
};

// Heartbeat
export const heartbeat = async (userRequest: UserRequest): Promise<{ success: boolean }> => {
    const response = await fetch(`${QUEUE_API_BASE_URL}/heartbeat`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(userRequest),
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
    }

    return await response.json();
};

// Get Metrics
export const getMetrics = async (): Promise<QueueMetrics> => {
    const response = await fetch(`${QUEUE_API_BASE_URL}/metrics`, {
        method: 'GET',
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
    }

    return await response.json();
};

// Get Timers
export const getTimers = async (userId: string): Promise<TimerInfo> => {
    const response = await fetch(`${QUEUE_API_BASE_URL}/timers/${userId}`, {
        method: 'GET',
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
    }

    return await response.json();
};
