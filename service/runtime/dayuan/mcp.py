"""MCP stdio adapter; native privileges stay in the local broker."""
import json
import sys
from .broker import request
from . import __version__

TOOLS = [
    {'name': 'dayuan_status', 'description': 'Check local bridge and existing WeCom assistant session.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
     'annotations': {'readOnlyHint': True, 'idempotentHint': True}},
    {'name': 'dayuan_submit', 'description': 'Submit a read-only task to the current Dayuan conversation. Returns a job ID; do not blindly resubmit on timeouts.',
     'inputSchema': {'type': 'object', 'properties': {'task': {'type': 'string', 'minLength': 1, 'maxLength': 20000}}, 'required': ['task'], 'additionalProperties': False},
     'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False}},
    {'name': 'dayuan_result', 'description': 'Poll an existing job without resubmitting. running means incomplete; complete includes Markdown text.',
     'inputSchema': {'type': 'object', 'properties': {'job_id': {'type': 'string'}, 'wait_seconds': {'type': 'number', 'minimum': 0, 'maximum': 30}}, 'required': ['job_id'], 'additionalProperties': False},
     'annotations': {'readOnlyHint': True, 'idempotentHint': True}},
]


def dispatch(message, call=request):
    if 'id' not in message:
        return None
    ident = message['id']; method = message.get('method'); params = message.get('params', {})
    def result(value):
        return {'jsonrpc': '2.0', 'id': ident, 'result': value}
    if method == 'initialize':
        versions = ('2024-11-05', '2025-03-26', '2025-06-18')
        version = params.get('protocolVersion')
        return result({'protocolVersion': version if version in versions else versions[-1],
                       'capabilities': {'tools': {}}, 'serverInfo': {'name': 'dayuan-local', 'version': __version__}})
    if method == 'ping':
        return result({})
    if method == 'tools/list':
        return result({'tools': TOOLS})
    if method == 'tools/call':
        args = params.get('arguments', {}); name = params.get('name')
        try:
            if not isinstance(args, dict):
                raise ValueError('Tool arguments must be an object')
            if name == 'dayuan_status':
                payload = {'method': 'status'}
            elif name == 'dayuan_submit':
                payload = {'method': 'submit', 'task': args.get('task')}
            elif name == 'dayuan_result':
                payload = {'method': 'result', 'job_id': args.get('job_id'), 'wait_seconds': args.get('wait_seconds', 0)}
            else:
                raise ValueError('UNKNOWN_TOOL')
            value = call(payload)
            return result({'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]})
        except Exception as exc:
            return result({'isError': True, 'content': [{'type': 'text', 'text': str(exc)}]})
    return {'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Method not found'}}


def serve_stdio(source=None, sink=None):
    source = source or sys.stdin; sink = sink or sys.stdout
    for line in source:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError('Expected JSON object')
            response = dispatch(message)
        except Exception:
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid JSON-RPC message'}}
        if response is not None:
            sink.write(json.dumps(response, ensure_ascii=True) + '\n');sink.flush()
