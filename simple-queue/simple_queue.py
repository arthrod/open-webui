#!/usr/bin/env python3

import sys
import time

from bisect import bisect_left


class SimpleQueue:
    def __init__(self, logger, draft_time: int = 5 * 60, session_time: int = 20 * 60, max_connected: int = 50):
        self.logger = logger
        self.draft_time = draft_time
        self.session_time = session_time
        self.max_connected = max_connected
        self.users = {}  # uid -> something
        self.waiting = []
        self.draft = []
        self.connected = []


    def metrics(self):
        return {
            "waiting_users": len(self.waiting),
            "draft_users": len(self.draft),
            "active_users": len(self.connected),
            "total_slots": self.max_connected
        }


    def join(self, user_id: int):
        if user_id in self.users:
            return -1

        join_time = int(time.time())
        self.users[user_id] = {
            'joined': join_time,
            'status': 'waiting'
        }

        self.waiting.append((join_time, user_id))


    def status(self, user_id: int):
        if user_id not in self.users:
            return None
        idx = 0
        if self.users[user_id]['status'] in [ 'waiting' ]:
            idx = SimpleQueue._index(self.waiting, self.users[user_id]['joined'], user_id)
            
        return {
            'position': idx,
            'status': self.users[user_id]['status']
        }


    def confirm(self, user_id: str, timestamp: int) -> int:
        if user_id not in self.users:
            return None

        assert('draft' == self.users[user_id]['status'])
        self.users[user_id]['status'] = 'connected'
        self.connected.append((timestamp, user_id))
        assert('draft_timestamp' in self.users[user_id])
        idx = SimpleQueue._index(self.draft, self.users[user_id]['draft_timestamp'], user_id)
        del self.draft[idx]

        return self.session_time


    def idle(self, steps: int = 1):
        while steps > 0:
            self._idle_step()
            steps -= 1


    @staticmethod
    def _index(lst: list, timestamp: int, user_id: str) -> int:
        idx = bisect_left(lst, timestamp, key=lambda x: x[0])
        while idx < len(lst) and lst[idx][0] == timestamp and lst[idx][1] != user_id:
            idx += 1
        if idx < len(lst) and lst[idx][0] == timestamp and lst[idx][1] == user_id:
            return idx
        raise ValueError


    def _prune_list(self, lst, min_value, list_name):
        while len(lst) > 0 and lst[0][0] < min_value:
            user_id = lst[0][1]
            self.logger.info(f'expired {user_id} in {list_name}')
            del lst[0]
            del self.users[user_id]


    def _idle_step(self):
        now = int(time.time())
        self._prune_list(self.draft, now - self.draft_time, 'DRAFT')
        now = int(time.time())
        self._prune_list(self.connected, now - self.session_time, 'CONNECTED')
        while (len(self.connected) + len(self.draft)) < self.max_connected and len(self.waiting) > 0:
            user_id = self.waiting[0][1]
            self.logger.info(f'moving {user_id} to DRAFT')
            now = int(time.time())
            self.draft.append((now, user_id))
            assert('waiting' == self.users[user_id]['status'])
            self.users[user_id]['status'] = 'draft'
            self.users[user_id]['draft_timestamp'] = now
            del self.waiting[0]
       
