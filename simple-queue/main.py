#!/usr/bin/env python3

import sys
import time
import logging

from flask import Flask, request
from flask_cors import CORS

from simple_queue import SimpleQueue

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
app.config.from_prefixed_env()
CORS(app, resources={r"/queue/*": {"origins": "*"}})

persist_prefix = None
persist_prefix_var_name = 'PERSIST_PREFIX'
if persist_prefix_var_name in app.config:
    persist_prefix = app.config[persist_prefix_var_name]
queue = SimpleQueue(app.logger, app.config['DRAFT_DURATION'], app.config['SESSION_DURATION'], app.config['MAX_ACTIVE_USERS'], persist_prefix)


@app.route('/queue/join', methods=['POST'])
def join():
    params = request.get_json()
    user_id = params['user_id']
    app.logger.debug(f'-> join({user_id})')
    queue.join(user_id)
    queue.idle()
    status = queue.status(user_id)
    if status is None:
        return { 'reason': f'Unknown user {user_id}' }
    return {
        'position': status['position']
    }


@app.route('/queue/status/<user_id>', methods=['GET'])
def status(user_id: str):
    app.logger.debug(f'-> status({user_id})')
    out = queue.status(user_id)

    if out is None:
        return { 'detail': f'Unknown user {user_id}' }

    return out


@app.route('/queue/confirm', methods=['POST'])
def confirm():
    params = request.get_json()
    user_id = str(params['user_id'])
    app.logger.debug(f'-> confirm({user_id})')

    session_duration, now = queue.confirm(user_id)
    if session_duration is None:
        return { 'reason': f'Unknown user {user_id}' }

    token = ' '.join([str(now), user_id])
    signature = None
    return {
        'status': 'connected',
        'session_duration': session_duration,
        'token': token,
        'signature': signature   # TODO
    }


@app.route('/queue/leave', methods=['POST'])
def leave():
    params = request.get_json()
    user_id = str(params['user_id'])
    app.logger.debug(f'-> leave({user_id})')

    queue.leave(user_id)

    return {}


@app.route('/queue/idle', methods=['POST'])
def idle():
    queue.idle()
    return {}


@app.route('/queue/metrics', methods=['GET'])
def metrics():
    return queue.metrics()

