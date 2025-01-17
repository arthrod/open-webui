import logging
import time
from typing import Optional
import os
import enum
from open_webui.env import SRC_LOG_LEVELS, MAX_ACTIVE_USERS, DRAFT_DURATION, SESSION_DURATION
from open_webui.internal.db import Base, JSONField, get_db
from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, Text, Enum as SQLEnum
import logging
from sqlalchemy.sql import and_


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["DB"])

####################
# User DB Schema
####################

class QueueStatus(str, enum.Enum):
    WAITING = 'waiting'
    DRAFT = 'draft'
    CONNECTED = 'connected'

class Queue(Base):
    __tablename__ = "queue"

    user_id = Column(String, primary_key=True)
    timestamp = Column(BigInteger)
    status = Column(SQLEnum(QueueStatus))

####################
# Forms
####################

class QueueModel(BaseModel):
    user_id: str
    timestamp: int
    status: str

class QueueMetrics(BaseModel):
    waiting_users: int
    draft_users: int
    active_users: int
    total_slots: int
    estimated_time: Optional[int] = None

class JoinRequest(BaseModel):
    user_id: str

class MetricsRequest(BaseModel):
    user_id: str

class ConfirmRequest(BaseModel):
    user_id: str

class DeleteRequest(BaseModel):
    user_id: str

class ConfirmResponse(BaseModel):
    status: str
    session_duration: int
    token: str
    signature: Optional[str] = None

class QueueTable:
    def __init__(self,
            draft_time=300,  # 5 minutes
            session_time=1200,  # 20 minutes
            max_connected=50
        ):
        self.draft_time = draft_time
        self.session_time = session_time
        self.max_connected = max_connected        
            
    def estimate_time(self, user_id: str):
        """Estimate the waiting time before joining the draft"""
        try:
            with get_db() as db:
                user = db.query(Queue).filter_by(user_id=user_id).first()
                if not user or user.status != QueueStatus.WAITING:
                    return None

                # Get current number of active users (draft + connected)
                total_active = self._count_connected_and_draft()

                # Count users ahead in the waiting queue
                n_users_ahead = db.query(Queue).filter(
                    Queue.status == QueueStatus.WAITING,
                    Queue.timestamp < user.timestamp
                ).count()

                # Calculate available slots
                available_slots = max(0, self.max_connected - total_active)
                if available_slots > 0: # if we hypothesize that draft user will join automatically else, adding this condition: "and available_slots > "
                    return 0
                else:
                    connected_users = db.query(Queue).filter(
                        Queue.status == QueueStatus.CONNECTED
                    ).order_by(Queue.timestamp).all()

                    remaining_times = []
                    # Estimate based on session expiration of currently connected users
                    current_time = int(time.time())
                    for i, conn_user in enumerate(connected_users):
                        time_remaining = max(0, (conn_user.timestamp + self.session_time) - current_time)
                        remaining_times.append(time_remaining)
                    
                    if n_users_ahead < len(remaining_times):
                        t = remaining_times[n_users_ahead - 1]
                        return t
                    else:
                        return max(remaining_times) + ((n_users_ahead - len(remaining_times)) / (self.max_connected)) * self.session_time
                    
        except Exception as e:
            log.error(f"Error estimating wait time: {e}")

# """
# waiting_user_n = id  
# position = n 
# list_session_user_duration = list()
# max_session = m
# len_lsud = t
# session_duration = x
# def estimation (user):
#     n = user.position
#     time_session_lasting = 0
#     for su in list_session_user_duration[:n] :
#         time_session_lasting += su
#     return  time_session_lasting

# si c'est superieur 
# time_session_lasting + (n -m)* x
# """


    def metrics(self, user_id: str = None) -> QueueMetrics:
        waiting_users = self._count_in_status(status=QueueStatus.WAITING)
        draft_users = self._count_in_status(status=QueueStatus.DRAFT)
        active_users = self._count_in_status(status=QueueStatus.CONNECTED)
        estimated_time = self.estimate_time(user_id=user_id) if user_id else None
        return QueueMetrics(
                waiting_users=waiting_users,
                draft_users=draft_users,
                active_users=active_users,
                total_slots=self.max_connected,
                estimated_time=estimated_time
            )

    def join(self, user_id: str) -> Optional[QueueModel]:
        with get_db() as db:
            queue = QueueModel(
                **{
                "user_id" : user_id,
                "timestamp" : int(time.time()),
                "status" : QueueStatus.WAITING
                })
            result = Queue(**queue.model_dump())
            db.add(result)
            db.commit()
            db.refresh(result)
            if result:
                return queue
            else:
                return None


    def status(self, user_id: str):
        try:
            with get_db() as db:
                user = db.query(Queue).filter_by(user_id = user_id).first()
                log.info(f"USER: {user}")
                status = user.status

                position = db.query(Queue).filter(
                    Queue.status == status,
                    Queue.timestamp <= user.timestamp
                ).count()
                
                return {'position': position, 'status': status }
                                
        except Exception as e:
            log.error(f"Error calling `status`: {e}")
            return None



    def _set_status_and_timestamp(self, user_id: str, new_status: QueueStatus, timestamp: int):
        try:
            with get_db() as db:
                db.query(Queue).filter_by(user_id=user_id).update({"status": new_status, "timestamp": timestamp})
                db.commit()

        except Exception as e:
            log.error(f"Error updating user status and timestamp: {e}")
            raise


    def confirm(self, user_id: str, timestamp: int) -> int:
        try:
            with get_db() as db:
                user = (db.query(Queue)
                    .filter(
                        Queue.user_id == user_id, 
                        Queue.status == QueueStatus.DRAFT)
                    .first()
                )

                log.info(f"USER: {user}")
                
                db.query(Queue).filter_by(user_id=user_id).update(
                    {
                        "status": QueueStatus.CONNECTED,
                        "timestamp": timestamp
                    }
                )

                db.commit()
                return self.session_time

        except Exception as e:
            log.error(f"Error happened: {e}")
            return None


    def _count_in_status(self, status: QueueStatus):
        try:
            with get_db() as db:
                count = db.query(Queue).filter_by(status = status.value).count()
                return count

        except Exception as e:
            log.error(f'Error: \'{type(e)}\'')
            return 0 # by default


    def _count_connected_and_draft(self):
        with get_db() as db:
            active_count = db.query(Queue).filter(
                        Queue.status.in_([QueueStatus.CONNECTED, QueueStatus.DRAFT])
                    ).count()
            
        return active_count



    def idle(self):
        try:
            with get_db() as db:
                # Remove expired connected users
                expired_connected = int(time.time()) - self.session_time
                db.query(Queue).filter(
                    and_(
                    Queue.status == QueueStatus.CONNECTED,
                    Queue.timestamp < expired_connected)
                ).delete()
                db.commit()

                # Remove expired draft users
                expired_draft = int(time.time()) - self.draft_time
                db.query(Queue).filter(
                    and_(
                    Queue.status == QueueStatus.DRAFT,
                    Queue.timestamp < expired_draft)
                ).delete()
                db.commit()

                # Move waiting users to draft if space available
                while self._count_connected_and_draft() < self.max_connected and self._count_in_status(QueueStatus.WAITING) > 0:
                    try:
                        # Get oldest waiting user
                        waiting_user = (db.query(Queue)
                            .filter(Queue.status == QueueStatus.WAITING)
                            .order_by(Queue.timestamp)
                            .first()
                        )
                        if waiting_user:
                            self._set_status_and_timestamp(user_id=waiting_user.user_id, new_status=QueueStatus.DRAFT, timestamp=int(time.time()))
                        return
                    except Exception as e:
                        log.error(f'{type(e)}')
                        log.error(f'Error: \'{e}\'')
        except Exception as e:
            log.error(f"An error happened: {e}")
    

    def delete(self, user_id: str):
        try:
            with get_db() as db:
                db.query(Queue).filter_by(user_id=user_id).delete()
                db.commit()
        except Exception as e:
            log.error(f"Error deleting user: {e}")
            raise


############################
# Initialize Queue
############################

queue = QueueTable(
    draft_time= DRAFT_DURATION,
    session_time=SESSION_DURATION,
    max_connected= MAX_ACTIVE_USERS
)