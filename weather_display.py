"""Dated Configured location weather, fetched directly; no language-model tool loop."""
import copy
import os
import datetime as dt
import json
import math
import re
import threading
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

_lock = threading.Lock()
_cache = None
_cached_at = 0
_retry_at = 0
ZONE = ZoneInfo(os.environ.get('AIRI_TIMEZONE','UTC'))
CITY = os.environ.get('AIRI_WEATHER_CITY','')


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('날씨 수치를 확인하지 못했어.')
    return round(value, 1)


def condition(code):
    return ({0: '맑음', 1: '대체로 맑음', 2: '구름 조금', 3: '흐림',
             45: '안개', 48: '안개', 51: '약한 이슬비', 53: '이슬비', 55: '강한 이슬비',
             61: '약한 비', 63: '비', 65: '강한 비', 71: '약한 눈', 73: '눈', 75: '강한 눈',
             77: '눈 알갱이', 80: '소나기', 81: '소나기', 82: '강한 소나기',
             85: '눈 소나기', 86: '강한 눈 소나기', 95: '뇌우', 96: '우박·뇌우', 99: '우박·뇌우'}
            .get(code, '강수' if code in (56, 57, 66, 67) else '날씨 정보'))


def open_meteo():
    if not CITY or not os.environ.get('AIRI_WEATHER_LAT') or not os.environ.get('AIRI_WEATHER_LON'):
        raise ValueError('Set AIRI_WEATHER_CITY, AIRI_WEATHER_LAT and AIRI_WEATHER_LON to enable weather.')
    latitude=float(os.environ['AIRI_WEATHER_LAT']);longitude=float(os.environ['AIRI_WEATHER_LON'])
    if not -90<=latitude<=90 or not -180<=longitude<=180:raise ValueError('Invalid weather coordinates.')
    params = {'latitude': latitude, 'longitude': longitude,
              'current': 'temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m,is_day',
              'daily': 'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code',
              'timezone': str(ZONE), 'forecast_days': 3, 'timeformat': 'unixtime'}
    url = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'AIRI-Weather/1'})
    with urllib.request.urlopen(req, timeout=7) as response:
        data = json.loads(response.read(300000))
    current, daily = data['current'], data['daily']
    forecast = [{'date': dt.datetime.fromtimestamp(t, ZONE).date().isoformat(),
                 'high_c': number(daily['temperature_2m_max'][i]),
                 'low_c': number(daily['temperature_2m_min'][i]),
                 'rain_percent': number(daily['precipitation_probability_max'][i]),
                 'condition': condition(daily['weather_code'][i])} for i, t in enumerate(daily['time'])]
    return {'city': CITY, 'timezone': str(ZONE), 'source': 'Open-Meteo',
            'source_url': 'https://open-meteo.com/', 'data_kind': '기상 모델 추정',
            'as_of': dt.datetime.fromtimestamp(current['time'], dt.timezone.utc).isoformat(),
            'temp_c': number(current['temperature_2m']), 'feels_c': number(current['apparent_temperature']),
            'wind_kph': number(current['wind_speed_10m']), 'humidity': number(current['relative_humidity_2m']),
            'condition': condition(current['weather_code']), 'is_day': bool(current['is_day']), 'forecast': forecast}


def existing_provider(app):
    if not CITY:raise ValueError('Set AIRI_WEATHER_CITY to enable weather.')
    import providers
    tools = [t for t in app.automation.public_tools(app) if t['enabled'] and providers.kind(t) == 'weather']
    if not tools:
        return open_meteo()
    data = providers.weather(app, tools[0], {'location': CITY, 'days': 3})
    c = data['current']
    return {'city': CITY, 'timezone': str(ZONE), 'source': 'WeatherAPI',
            'source_url': 'https://www.weatherapi.com/', 'data_kind': '현재 날씨',
            'as_of': dt.datetime.fromtimestamp(c['last_updated_epoch'], dt.timezone.utc).isoformat(),
            'temp_c': number(c['temp_c']), 'feels_c': number(c['feelslike_c']),
            'wind_kph': number(c['wind_kph']), 'humidity': number(c['humidity']),
            'condition': str(c['condition']['text'])[:80], 'is_day': bool(c['is_day']),
            'forecast': [{'date': d['date'], 'high_c': number(d['day']['maxtemp_c']),
                          'low_c': number(d['day']['mintemp_c']), 'rain_percent': number(d['day']['daily_chance_of_rain']),
                          'condition': str(d['day']['condition']['text'])[:80]} for d in data['forecast']]}


def get(app):
    global _cache, _cached_at, _retry_at
    with _lock:
        now = time.monotonic()
        if _cache and now - _cached_at < 600:
            return copy.deepcopy(_cache)
        if now < _retry_at:
            if _cache:
                return {**copy.deepcopy(_cache), 'stale': True}
            raise ValueError('날씨 연결을 잠시 후 다시 확인할게.')
        try:
            try:
                data = existing_provider(app)
            except Exception:
                data = open_meteo()
            age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data['as_of'])).total_seconds()
            if age < -900 or age > 7200:
                raise ValueError('현재 시각과 날씨 자료 시각이 맞지 않아.')
            data.update(stale=age > 3600, fetched_at=dt.datetime.now(dt.timezone.utc).isoformat())
            _cache, _cached_at = data, now
            return copy.deepcopy(data)
        except Exception:
            _retry_at = time.monotonic() + 60
            if _cache:
                return {**copy.deepcopy(_cache), 'stale': True}
            raise ValueError('날씨를 가져오지 못했어. 잠시 후 새로고침해 줘.') from None


def requested(query):
    """Only a Configured location weather lookup; quoted examples and setup stay in chat."""
    if re.search(r'번역|뜻|예시|구현|코드|API|설정|위젯|고쳐|하지\s*마|translate|meaning|example|implement|widget', query, re.I):
        return False
    weather = bool(re.search(r'날씨|기온|우산|비\s*(?:와|올|오니)|\b(?:weather|temperature|rain|umbrella)\b', query, re.I))
    local = bool(re.search(r'설정한 지역|vancouver', query, re.I))
    default = bool(re.fullmatch(r'\s*(?:(?:아이리|AIRI)[, ]*)?(?:(?:오늘|지금|현재|내일|모레)\s*)?(?:날씨|기온)(?:가|는|좀)?\s*(?:어때|어때요|알려줘|알려\s*줘|보여줘|보여\s*줘)?[.!?\s]*', query, re.I))
    return weather and (local or default)


def answer(data, query):
    stamp = dt.datetime.fromisoformat(data['as_of']).astimezone(ZONE).strftime('%m월 %d일 %H:%M')
    forecast = data['forecast']
    offset = 2 if re.search(r'모레|day after tomorrow', query, re.I) else 1 if re.search(r'내일|tomorrow', query, re.I) else 0
    date = (dt.datetime.now(ZONE).date() + dt.timedelta(days=offset)).isoformat()
    day = next((d for d in forecast if d['date'] == date), None)
    if offset and not day:
        return '그 날짜의 설정한 지역 예보를 아직 받지 못했어.'
    text = (f"설정한 지역 {date} 예보는 {day['condition']}이야. " if offset else
            f"설정한 지역는 {stamp} 기준 {data['temp_c']:g}도, {data['condition']}이야. 체감온도는 {data['feels_c']:g}도야. ")
    if day:
        text += f"{'그날' if offset else '오늘'} 최고 {day['high_c']:g}도, 최저 {day['low_c']:g}도고 강수 확률은 {day['rain_percent']:g}%야."
    if data['stale']:
        text += ' 최신 갱신이 늦어져서 표시한 시각의 자료야.'
    return text


def chat_reply(app, query):
    if not requested(query):
        return None
    try:
        data = get(app)
        app.event('weather', '설정한 지역 날씨 직접 조회 · ' + data['source'] + ' · ' + data['as_of'])
        return answer(data, query)
    except ValueError as error:
        return str(error)
