#!/usr/bin/env python3

import sys
import os
import time
import json

from bisect import bisect_left


class SimpleQueue:
    def __init__(self, logger, draft_time: int = 5 * 60, session_time: int = 20 * 60, max_connected: int = 50, fn_prefix = None, max_states: int = 10):
        self.logger = logger
        self.draft_time = draft_time
        self.session_time = session_time
        self.max_connected = max_connected
        self.users = {}  # uid -> something
        self.waiting = []
        self.draft = []
        self.connected = []
        self.dir_name, self.fn_prefix = None, None
        self.max_states = max_states
        self.save_step = 0
        if fn_prefix is not None:
            self.dir_name, self.fn_prefix = os.path.split(os.path.normpath(fn_prefix))
            self._load()


    def _save(self):
        fn = os.path.join(self.dir_name, self.fn_prefix) + f'_{self.save_step}.json'
        self.save_step = (self.save_step + 1) % self.max_states
        with open(fn, 'w') as f:
            state = {
                'waiting': self.waiting,
                'draft': self.draft,
                'connected': self.connected,
                'users': self.users
            }
            json.dump(state, f, ensure_ascii=False, indent=4)


    def _find_last_state_fn(self):
        last_ts, last_fn = 0, None
        for f in os.listdir(self.dir_name):
            if not f.startswith(self.fn_prefix):
                continue
            fn = os.path.join(self.dir_name, f)
            if not os.path.isfile(fn):
                continue
            ts = os.path.getmtime(fn)
            if ts > last_ts:
                last_ts = ts
                last_fn = fn

        self.logger.info(f'Last state is in \'{last_fn}\' ({last_ts})')
        return last_fn


    def _load(self):
        fn = self._find_last_state_fn()
        if fn is None:
            return
        with open(fn, 'r') as f:
            state = json.load(f)
            self.waiting = state['waiting']
            self.draft = state['draft']
            self.connected = state['connected']
            self.users = state['users']


    def metrics(self):
        return {
            "waiting_users": len(self.waiting),
            "draft_users": len(self.draft),
            "active_users": len(self.connected),
            "total_slots": self.max_connected
        }


    def join(self, user_id: str):
        if user_id in self.users:
            return

        join_time = int(time.time())
        self.users[user_id] = {
            'joined': join_time,
            'status': 'waiting'
        }

        self.waiting.append((join_time, user_id))

        if self.fn_prefix is not None:
            self._save()


    def status(self, user_id: str):
        if user_id not in self.users:
            return None
        idx = 0
        if self.users[user_id]['status'] in [ 'waiting' ]:
            idx = SimpleQueue._index(self.waiting, self.users[user_id]['joined'], user_id)
            
        return {
            'position': idx,
            'status': self.users[user_id]['status']
        }


    def confirm(self, user_id: str) -> tuple:
        if user_id not in self.users:
            return None, None

        timestamp = int(time.time())
        assert('draft' == self.users[user_id]['status'])
        self.users[user_id]['status'] = 'connected'
        self.users[user_id]['connected_timestamp'] = timestamp
        self.connected.append((timestamp, user_id))
        assert('draft_timestamp' in self.users[user_id])
        idx = SimpleQueue._index(self.draft, self.users[user_id]['draft_timestamp'], user_id)
        del self.draft[idx]

        if self.fn_prefix is not None:
            self._save()

        return self.session_time, timestamp


    def leave(self, user_id: str):
        if user_id not in self.users:
            return None

        user = self.users[user_id]
        if user['status'] in [ 'waiting' ]:
            idx = SimpleQueue._index(self.waiting, user['joined'], user_id)
            del self.waiting[idx]
            self.logger.info(f'removed {user_id} from WAITING')
        elif user['status'] in [ 'draft' ]:
            idx = SimpleQueue._index(self.draft, user['draft_timestamp'], user_id)
            del self.draft[idx]
            self.logger.info(f'removed {user_id} from DRAFT')
        elif user['status'] in [ 'connected' ]:
            idx = SimpleQueue._index(self.connected, user['connected_timestamp'], user_id)
            del self.connected[idx]
            self.logger.info(f'removed {user_id} from CONNECTED')
        else:
            raise Exception(f'Unknown status: \'{user.status}\'')

        del self.users[user_id]


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
       
