#!/usr/bin/env python3

import sys
import time
import logging
from typing import Optional, Any
from open_webui.env import SRC_LOG_LEVELS
from open_webui.models.queue import queue, QueueStatus, QueueMetrics, JoinRequest, ConfirmRequest, ConfirmResponse, DeleteRequest
from fastapi import APIRouter, HTTPException, status

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["DB"])

router = APIRouter()

############################
# Join Queue
############################

@router.post("/join", response_model=dict[str, int])
async def join(request: JoinRequest):
    user_id = request.user_id
    log.debug(f'-> join({user_id})')
    queue.join(user_id)
    queue.idle()
    
    user_status = queue.status(user_id)

    if user_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Unknown user {user_id}'
        )
    
    return {
        'position': user_status['position']
    }


############################
# Get Queue Status
############################

@router.get("/status/{user_id}", response_model=dict[str, Any])
async def get_status(user_id: str):
    log.debug(f'-> status({user_id})')
    out = queue.status(user_id)
    
    if out is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Unknown user {user_id}'
        )
    
    return out

###########################Leave
# Confirm Queue Position
############################

@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(request: ConfirmRequest):
    user_id = request.user_id
    log.debug(f'-> confirm({user_id})')
    
    now = int(time.time())
    session_duration = queue.confirm(user_id, now)
    
    if session_duration is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f'Unknown user {user_id}'
        )
    
    return ConfirmResponse(
        status=QueueStatus.CONNECTED,
        session_duration=session_duration,
        token=' '.join([str(now), user_id]),
        signature=None  # TODO
    )

############################
# Queue Maintenance
############################

@router.post("/idle", response_model=dict)
async def idle():
    queue.idle()
    return {}


############################
# Queue Metrics
############################

@router.get("/metrics", response_model=QueueMetrics)
async def get_metrics():
    return queue.metrics()

############################
# Queue Leave
############################

@router.post("/leave", response_model=dict)
async def delete(request: DeleteRequest):
    user_id = request.user_id
    queue.delete(user_id)
    return {}