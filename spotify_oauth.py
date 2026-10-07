"""Spotify Authorization Code with PKCE for the loopback AIRI app.

Only the browser is redirected to Spotify. Tokens stay in the local AIRI data
directory and are never returned to JavaScript.
"""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

REDIRECT_URI = 'http://127.0.0.1:8766/spotify/callback'
AUTHORIZE_URL = 'https://accounts.spotify.com/authorize'
TOKEN_URL = 'https://accounts.spotify.com/api/token'
API_URL = 'https://api.spotify.com/v1'
SCOPES = (
    'user-read-currently-playing user-read-playback-state '
    'user-modify-playback-state user-read-playback-position user-read-private'
)
LOCK = threading.RLock()


def redirect_uri(app):
    return 'http://127.0.0.1:%d/spotify/callback' % int(app.PORT)


def _paths(app):
    folder = app.DATA / 'spotify'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(folder, 0o700)
    return folder / 'oauth.json', folder / 'pending.json'


def _read(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False))
    os.chmod(temp, 0o600)
    os.replace(temp, path)
    os.chmod(path, 0o600)


def _client_id(app):
    value = app.settings().get('spotify_client_id', '')
    if isinstance(value, str) and value.strip():
        return value.strip()
    # Older AIRI builds stored the Spotify Client ID in the API registry.
    # Reuse only a tool explicitly named Spotify or pointing at Spotify's
    # dashboard; never scan or expose arbitrary API credentials.
    try:
        for tool in app.rows('SELECT id,name,url FROM api_tools'):
            name = str(tool.get('name', '')).lower()
            host = urllib.parse.urlsplit(str(tool.get('url', '')).strip()).hostname or ''
            if 'spotify' not in name and host not in ('developer.spotify.com', 'accounts.spotify.com'):
                continue
            candidate = (app.DATA / 'api-keys' / str(tool['id'])).read_text().strip()
            if candidate and len(candidate) <= 128 and all(ch.isalnum() or ch in '-_' for ch in candidate):
                return candidate
    except (AttributeError, OSError, ValueError):
        pass
    return ''


def configure(app, client_id):
    if not isinstance(client_id, str) or not client_id.strip() or len(client_id.strip()) > 128:
        raise ValueError('Spotify Client ID를 입력하세요.')
    client_id = client_id.strip()
    if not all(ch.isalnum() or ch in '-_' for ch in client_id):
        raise ValueError('Spotify Client ID 형식이 올바르지 않습니다.')
    with app.db() as connection:
        connection.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', ('spotify_client_id', json.dumps(client_id)))
    return status(app)


def status(app):
    token_path, _ = _paths(app)
    token = _read(token_path)
    return {
        'configured': bool(_client_id(app)),
        'client_id_source': 'settings_or_spotify_api_registration' if _client_id(app) else None,
        'connected': bool(token.get('refresh_token') or token.get('access_token')),
        'scopes': token.get('scope', SCOPES),
        'track': None,
        'artist': None,
        'album_art': None,
        'playing': False,
        'progress_ms': 0,
        'duration_ms': 0,
        'device': None,
        'device_id': None,
        'devices': [],
        'audio_output': __import__('bluetooth_audio').status(),
        'can_control': False,
        'error': None,
        'redirect_uri': redirect_uri(app),
    }


def disconnect(app):
    """Remove the locally persisted Spotify token without removing the Client ID."""
    token_path, pending_path = _paths(app)
    with LOCK:
        for path in (token_path, pending_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    return status(app)


def _request(url, data=None, headers=None, method=None):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=12) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode()) if raw else {}


def begin(app):
    client_id = _client_id(app)
    if not client_id:
        raise ValueError('먼저 Spotify Client ID를 저장하세요.')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    _, pending_path = _paths(app)
    with LOCK:
        _write(pending_path, {'state': state, 'verifier': verifier, 'created': time.time()})
    query = urllib.parse.urlencode({
        'client_id': client_id,
        'response_type': 'code',
        'redirect_uri': redirect_uri(app),
        'state': state,
        'scope': SCOPES,
        'code_challenge_method': 'S256',
        'code_challenge': challenge,
    })
    return AUTHORIZE_URL + '?' + query


def callback(app, query):
    token_path, pending_path = _paths(app)
    pending = _read(pending_path)
    state = query.get('state', [''])[0]
    if not state or not secrets.compare_digest(state, str(pending.get('state', ''))):
        raise ValueError('Spotify OAuth state가 일치하지 않습니다.')
    if time.time() - float(pending.get('created', 0)) > 600:
        raise ValueError('Spotify OAuth 요청이 만료되었습니다. 다시 연결하세요.')
    if query.get('error'):
        raise ValueError('Spotify 인증이 취소되었습니다.')
    code = query.get('code', [''])[0]
    if not code:
        raise ValueError('Spotify 인증 코드가 없습니다.')
    form = urllib.parse.urlencode({
        'client_id': _client_id(app),
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri(app),
        'code_verifier': pending['verifier'],
    }).encode()
    _, token = _request(TOKEN_URL, form, {'Content-Type': 'application/x-www-form-urlencoded'}, 'POST')
    token['expires_at'] = time.time() + int(token.get('expires_in', 3600)) - 60
    with LOCK:
        _write(token_path, token)
        try: pending_path.unlink()
        except FileNotFoundError: pass
    return token


def _refresh(app, token):
    refresh_token = token.get('refresh_token')
    if not refresh_token:
        raise ValueError('Spotify refresh token이 없습니다. 다시 연결하세요.')
    form = urllib.parse.urlencode({
        'client_id': _client_id(app),
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }).encode()
    _, updated = _request(TOKEN_URL, form, {'Content-Type': 'application/x-www-form-urlencoded'}, 'POST')
    updated['refresh_token'] = updated.get('refresh_token', refresh_token)
    updated['scope'] = updated.get('scope', token.get('scope', SCOPES))
    updated['expires_at'] = time.time() + int(updated.get('expires_in', 3600)) - 60
    token_path, _ = _paths(app)
    with LOCK: _write(token_path, updated)
    return updated


def _access_token(app):
    token_path, _ = _paths(app)
    token = _read(token_path)
    if not token.get('access_token'):
        raise ValueError('Spotify 계정을 먼저 연결하세요.')
    if float(token.get('expires_at', 0)) <= time.time():
        token = _refresh(app, token)
    return token


def _api(app, path, method='GET', payload=None, query=None, retry=True):
    token = _access_token(app)
    url = API_URL + path
    if query: url += '?' + urllib.parse.urlencode(query)
    body = None if payload is None else json.dumps(payload).encode()
    headers = {'Authorization': 'Bearer ' + token['access_token'], 'Content-Type': 'application/json'}
    try:
        return _request(url, body, headers, method)[1]
    except urllib.error.HTTPError as error:
        if error.code == 401 and retry:
            _refresh(app, token)
            return _api(app, path, method, payload, query, False)
        if error.code == 204: return {}
        raise


def refresh(app):
    result = status(app)
    if not result['connected']: return result
    try:
        player = _api(app, '/me/player')
        item = player.get('item') or {}
        artists = item.get('artists') or []
        devices = _api(app, '/me/player/devices').get('devices') or []
        result.update({
            'track': item.get('name'), 'artist': ', '.join(a.get('name', '') for a in artists if a.get('name')),
            'album_art': ((item.get('album') or {}).get('images') or [{}])[0].get('url'),
            'playing': bool(player.get('is_playing')), 'progress_ms': player.get('progress_ms') or 0,
            'duration_ms': item.get('duration_ms') or 0,
            'device': (player.get('device') or {}).get('name') or (devices[0].get('name') if devices else None),
            'device_id': (player.get('device') or {}).get('id'),
            'devices': [{k: d.get(k) for k in ('id','name','type','is_active','is_restricted')} for d in devices],
            'can_control': bool((player.get('device') or {}).get('id')) and not (player.get('device') or {}).get('is_restricted', False),
        })
        if not item:
            result['error'] = '재생 기기를 선택하거나 Spotify 앱에서 음악을 재생하세요.' if devices else 'Spotify 앱을 열고 음악을 재생하세요. 현재 사용 가능한 기기가 없습니다.'
    except Exception as error:
        result['error'] = error_message(error)
        if isinstance(error, urllib.error.HTTPError) and error.code in (400,401):
            result['connected'] = False
    return result


def error_message(error):
    if isinstance(error, urllib.error.HTTPError):
        return {400:'Spotify 인증 또는 재생 요청이 유효하지 않습니다. 연결 설정을 확인하세요.',
                401:'Spotify 인증이 만료되었습니다. Connect Spotify로 다시 연결하세요.',
                403:'Spotify가 재생 제어를 거부했습니다. Premium 계정, 앱 사용자 등록과 재생 권한을 확인하세요.',
                404:'활성 Spotify 기기가 없습니다. 재생 기기를 선택하거나 Spotify 앱에서 곡을 먼저 재생하세요.',
                429:'Spotify 요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.'}.get(error.code,'Spotify 요청 실패 · HTTP '+str(error.code))
    return str(error) if isinstance(error,ValueError) else 'Spotify 응답을 받지 못했습니다. 인터넷 연결을 확인하세요.'


def command(app, action, body=None):
    try:
        return _command(app, action, body)
    except urllib.error.HTTPError as error:
        raise ValueError(error_message(error)) from error


def _command(app, action, body=None):
    body = body or {}
    if action in ('audio_output','bluetooth_settings'):
        import bluetooth_audio
        if action == 'audio_output': bluetooth_audio.select(body.get('output_id'))
        else: bluetooth_audio.open_settings()
        return refresh(app)
    device_id = body.get('device_id')
    if device_id is not None and (not isinstance(device_id,str) or not device_id or len(device_id)>256):
        raise ValueError('Spotify 재생 기기를 확인하세요.')
    if action == 'transfer':
        devices = _api(app, '/me/player/devices').get('devices') or []
        device = next((d for d in devices if d.get('id')==device_id and device_id), None)
        if not device or device.get('is_restricted'):
            raise ValueError('이 기기는 사용할 수 없습니다. Spotify 앱에서 기기를 다시 확인하세요.')
        _api(app, '/me/player', 'PUT', {'device_ids':[device_id], 'play':False})
        return refresh(app)
    query = {'device_id':device_id} if device_id else None
    paths = {'play': ('/me/player/play', 'PUT'), 'pause': ('/me/player/pause', 'PUT'), 'next': ('/me/player/next', 'POST'), 'previous': ('/me/player/previous', 'POST')}
    if action in paths:
        _api(app, paths[action][0], paths[action][1], query=query)
    elif action == 'seek':
        _api(app, '/me/player/seek', 'PUT', query={'position_ms': int(body.get('position_ms', 0))})
    elif action == 'volume':
        _api(app, '/me/player/volume', 'PUT', query={'volume_percent': max(0, min(100, int(body.get('volume_percent', 50))))})
    elif action == 'shuffle':
        _api(app, '/me/player/shuffle', 'PUT', query={'state': 'true' if body.get('state') else 'false'})
    elif action == 'repeat':
        mode = body.get('state', 'context')
        if mode not in ('track', 'context', 'off'): raise ValueError('repeat state가 올바르지 않습니다.')
        _api(app, '/me/player/repeat', 'PUT', query={'state': mode})
    else: raise ValueError('지원하지 않는 Spotify 동작입니다.')
    return refresh(app)


def callback_page(message, ok=False):
    title = 'Spotify Connected' if ok else 'Spotify 연결 실패'
    return ('<!doctype html><meta charset="utf-8"><title>%s</title><p>%s</p>'
            '<script>setTimeout(()=>location.replace("/?spotify=%s"),700)</script>' %
            (html.escape(title), html.escape(message), 'connected' if ok else 'error')).encode()
