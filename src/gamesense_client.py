"""Cliente GameSense con errores y respuestas HTTP observables."""
import json
import os
from pathlib import Path
import requests
from PIL import Image

PROFILES = {'gamedac': (128,52), 'arctis_pro_wireless': (128,48)}

def prepare_image(image, profile='gamedac'):
    if profile not in PROFILES:
        raise ValueError('Unknown display profile')
    if image.mode != '1' or image.size != (128,52):
        raise ValueError('Expected a monochrome 128x52 source frame')
    size=PROFILES[profile]
    return image if image.size==size else image.resize(size,Image.Resampling.NEAREST)
def bitmap(image):
    if image.mode != '1' or image.size not in PROFILES.values():
        raise ValueError('Expected a monochrome 128x52 or 128x48 image')
    return list(image.tobytes())

def response_summary(value):
    if isinstance(value, dict):
        return {k: (f'<{len(v)} bytes>' if k.startswith('image-data') and isinstance(v, list)
                    else response_summary(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [response_summary(v) for v in value]
    return value

class GameSense:
    GAME = 'DAC_PIXEL_APP'
    EVENT = 'PIXEL_IMAGE'

    def __init__(self, debug=False, profile='gamedac'):
        if profile not in PROFILES: raise ValueError('Unknown display profile')
        self.profile=profile
        self.width,self.height=PROFILES[profile]
        self.debug = debug
        self.sent = 0
        path = Path(os.environ['PROGRAMDATA']) / 'SteelSeries/SteelSeries Engine 3/coreProps.json'
        address = json.loads(path.read_text(encoding='utf-8-sig'))['address']
        host, port = address.rsplit(':', 1)
        if host not in ('127.0.0.1', 'localhost', '::1', '[::1]'):
            raise ValueError('GameSense server must be local')
        self.server = f'http://127.0.0.1:{int(port)}'
        self.session = requests.Session()
        self.session.trust_env = False

    def post(self, endpoint, payload):
        try:
            response = self.session.post(f'{self.server}/{endpoint}', json=payload, timeout=2)
        except requests.RequestException as exc:
            raise RuntimeError(f'GameSense {endpoint} at {self.server}: {exc}. Restart GG to refresh coreProps.json.') from exc
        if not response.ok:
            raise RuntimeError(f'GameSense {endpoint}: HTTP {response.status_code}: {response.text[:1000]}')
        try:
            body = response.json()
        except ValueError:
            body = None
        if self.debug:
            summary = json.dumps(response_summary(body), ensure_ascii=False) if body is not None else response.text[:1000] or '(empty body)'
            print(f'GameSense {endpoint}: HTTP {response.status_code}; {summary}', flush=True)
        if isinstance(body, dict) and (body.get('error') or body.get('errorMessage')):
            raise RuntimeError(f'GameSense {endpoint}: {body}')
        return response

    def bind(self, image):
        image=prepare_image(image,self.profile)
        print(f'GameSense: {self.server}; {self.GAME}/{self.EVENT}; {self.width}x{self.height}, {len(bitmap(image))} bytes.', flush=True)
        self.post('game_metadata', {'game': self.GAME, 'game_display_name': 'DAC Pixel Eyes', 'developer': 'Personal Project'})
        self.post('bind_game_event', {'game': self.GAME, 'event': self.EVENT, 'value_optional': True,
            'handlers': [{'device-type': f'screened-{self.width}x{self.height}', 'zone': 'one', 'mode': 'screen',
                          'datas': [{'has-text': False, 'image-data': bitmap(image)}]}]})

    def send(self, image):
        image=prepare_image(image,self.profile)
        self.post('game_event', {'game': self.GAME, 'event': self.EVENT,
            'data': {'frame': {f'image-data-{self.width}x{self.height}': bitmap(image)}}})
        self.sent += 1
        if self.sent == 1:
            print('First frame accepted by HTTP. Check the physical OLED to confirm display output.', flush=True)

    def close(self):
        self.session.close()
