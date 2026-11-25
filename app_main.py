import os, json, threading, hashlib, secrets, socket, urllib.request, urllib.parse, time, html, webbrowser, base64, hmac, re
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.audio import SoundLoader
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle

BASE = Path(__file__).resolve().parent

def resolve_data_root():
    try:
        from kivy.utils import platform
        if platform == 'android':
            from jnius import autoclass
            activity = autoclass('org.kivy.android.PythonActivity').mActivity
            return Path(str(activity.getFilesDir().getAbsolutePath())) / 'amad_support'
        if platform == 'win':
            return Path(os.environ.get('APPDATA', str(Path.home()))) / 'AmadSupport'
        if platform == 'macosx':
            return Path.home() / 'Library' / 'Application Support' / 'AmadSupport'
    except Exception:
        pass
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share'))) / 'amad_support'

DATA = resolve_data_root() / 'data'
AUDIO = DATA / 'noheh'
REPORTS = DATA / 'reports'
for _p in (DATA, AUDIO, REPORTS):
    try:
        _p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

# ---------- boot stage logger (diagnosing black-screen-on-startup) ----------
def boot_log(stage):
    try:
        with open(DATA / 'boot.log', 'a', encoding='utf-8') as fh:
            fh.write(now() + '  ' + stage + '\n')
    except Exception:
        pass


# ---------- crash reporter ----------
import sys as _sys, traceback as _tb

def _crash_text():
    return ''.join(_tb.format_exception(*_sys.exc_info()))

def _log_crash():
    try:
        (DATA / 'crash.log').write_text(now() + '\n' + _crash_text(), encoding='utf-8')
    except Exception:
        pass

try:
    from kivy.core.window import Window as _W
except Exception:
    _W = None

def _show_crash_screen(text):
    try:
        from kivy.app import App as _App
        _a=_App.get_running_app()
        if _a is not None and getattr(_a,'root',None) is not None:
            try: _log_crash()
            except Exception: pass
            return
    except Exception:
        pass
    # IMPORTANT: must work even when the App crashed inside build()
    # (no running app, no root widget). Never rely on get_running_app().
    try:
        from kivy.core.window import Window
        Window.clearcolor = (0.10, 0.10, 0.11, 1)
    except Exception:
        pass
    try:
        from kivy.uix.scrollview import ScrollView as _SV
        from kivy.uix.label import Label as _L
        from kivy.base import runTouchApp as _RTA
        lb = _L(text=text[-4000:], font_name='Roboto', font_size='11sp',
                halign='left', valign='top', size_hint_y=None,
                color=(1, 0.4, 0.4, 1), padding=(12, 12))
        lb.bind(width=lambda i, v: setattr(lb, 'text_size', (v, None)))
        lb.bind(texture_size=lambda i, v: setattr(lb, 'height', v[1]))
        sv = _SV(size=_W.size)
        sv.add_widget(lb)
        _W.add_widget(sv)
        _RTA(sv)   # own event loop: shows the traceback even if App.run died
    except Exception as e:
        try:
            _log_crash()
        except Exception:
            pass

def _excepthook(etype, value, tb):
    _sys.__excepthook__(etype, value, tb)
    _log_crash()
    _show_crash_screen(''.join(_tb.format_exception(etype, value, tb)))
    # keep window alive so the user can read/screenshot the error
    import time as _t
    while True:
        _t.sleep(1)

_sys.excepthook = _excepthook

from kivy.base import ExceptionManager as _EM
def _em_handler(exc):
    _log_crash()
    _show_crash_screen(_crash_text())
    raise exc
_EM.add_handler(_em_handler)
# ------------------------------------

DB = DATA / 'db.json'
FONT = str((BASE / 'assets' / 'NotoNaskhArabic-Regular.ttf') if (BASE / 'assets' / 'NotoNaskhArabic-Regular.ttf').exists() else (BASE / 'NotoNaskhArabic-Regular.ttf'))
FONT_B = str((BASE / 'assets' / 'NotoNaskhArabic-Bold.ttf') if (BASE / 'assets' / 'NotoNaskhArabic-Bold.ttf').exists() else (BASE / 'NotoNaskhArabic-Bold.ttf'))
try:
    LabelBase.register(name='NotoFA', fn_regular=FONT, fn_bold=FONT_B)
except Exception:
    pass


def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def hashpw(p, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt, hashlib.pbkdf2_hmac('sha256', p.encode(), salt.encode(), 120000).hex()
def verify(p, salt, digest): return hmac.compare_digest(hashpw(p, salt)[1], digest)

def valid_password(password): return isinstance(password, str) and len(password) >= 10

def valid_username(username): return bool(re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{2,31}', str(username or '')))

def load_db():
    if DB.exists():
        try: return json.loads(DB.read_text('utf-8'))
        except Exception: pass
    salt, digest = hashpw('Admin1234')
    return {'users':[{'username':'admin','name':'مدیر سامانه','role':'admin','salt':salt,'password':digest,'active':True}],
            'chant_index':0,'chants':[],'repairs':[],'equipment':[],'created':now()}

def save_db(db):
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), 'utf-8')

def local_ips():
    ips=[]
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); ips.append(s.getsockname()[0]); s.close()
    except Exception: pass
    return ips or ['127.0.0.1']

try:
    DBDATA = load_db()
    try:
        save_db(DBDATA)
    except Exception:
        pass
except Exception:
    DBDATA = {'users':[],'chant_index':0,'chants':[],'repairs':[],'equipment':[],'created':now()}
SERVER = None
SESSIONS = {}
LOGIN_FAILURES = {}

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self, obj, code=200):
        b=json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def read_json(self):
        n=int(self.headers.get('Content-Length','0'))
        if n > 8_000_000: raise ValueError('request too large')
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}
    def session_user(self):
        token=self.headers.get('Authorization','').strip()
        if token.startswith('Bearer '): token=token[len('Bearer '):].strip()
        session=SESSIONS.get(token)
        if not session: return None
        if session.get('expires_at',0) < time.time():
            SESSIONS.pop(token,None)
            return None
        return session
    def require_user(self, admin=False):
        user=self.session_user()
        if not user:
            self.send_json({'ok':False,'error':'ورود معتبر لازم است'},401)
            return None
        if admin and user.get('role') != 'admin':
            self.send_json({'ok':False,'error':'دسترسی مدیر لازم است'},403)
            return None
        return user
    def do_GET(self):
        if self.path=='/api/info': return self.send_json({'ok':True,'name':'سامانه آماد و پشتیبانی','version':'5.0.3'})
        if self.path.startswith('/audio/'):
            if not self.require_user(): return
            name=os.path.basename(urllib.parse.unquote(self.path.split('/audio/',1)[1])); f=AUDIO/name
            if not f.exists(): return self.send_json({'ok':False,'error':'not found'},404)
            mime={'.mp3':'audio/mpeg','.wav':'audio/wav','.m4a':'audio/mp4'}.get(f.suffix.lower(),'application/octet-stream')
            self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Length',str(f.stat().st_size)); self.end_headers()
            with open(f,'rb') as h:
                while True:
                    chunk=h.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
            return
        if self.path.startswith('/api/photo/'):
            if not self.require_user(): return
            name=os.path.basename(urllib.parse.unquote(self.path.split('/api/photo/',1)[1]))
            f=REPORTS/name
            if not f.exists() or f.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                return self.send_json({'ok':False,'error':'تصویر پیدا نشد'},404)
            self.send_response(200); self.send_header('Content-Type',{'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[f.suffix.lower()]); self.send_header('Content-Length',str(f.stat().st_size)); self.end_headers()
            with open(f,'rb') as h:
                while True:
                    chunk=h.read(65536)
                    if not chunk: break
                    self.wfile.write(chunk)
            return
        self.send_json({'ok':False,'error':'not found'},404)
    def do_POST(self):
        global DBDATA
        try: data=self.read_json()
        except Exception: return self.send_json({'ok':False,'error':'bad json'},400)
        if self.path=='/api/login':
            u=data.get('username',''); p=data.get('password','')
            attempt_key=(self.client_address[0],str(u).lower())
            attempt=LOGIN_FAILURES.get(attempt_key,{})
            if attempt.get('blocked_until',0)>time.time():
                return self.send_json({'ok':False,'error':'به‌دلیل تلاش‌های ناموفق، ورود موقتاً مسدود شده است'},429)
            user=next((x for x in DBDATA['users'] if x['username']==u and x.get('active',True)),None)
            if not user or not verify(p,user['salt'],user['password']):
                failures=attempt.get('count',0)+1
                LOGIN_FAILURES[attempt_key]={'count':failures,'blocked_until':time.time()+900 if failures>=5 else 0}
                return self.send_json({'ok':False,'error':'نام کاربری یا گذرواژه نادرست است'},401)
            LOGIN_FAILURES.pop(attempt_key,None)
            track=None
            if DBDATA['chants']:
                track=DBDATA['chants'][DBDATA['chant_index'] % len(DBDATA['chants'])]; DBDATA['chant_index']=(DBDATA['chant_index']+1)%len(DBDATA['chants']); save_db(DBDATA)
            token=secrets.token_urlsafe(32)
            SESSIONS[token]={'username':user['username'],'name':user['name'],'role':user['role'],'expires_at':time.time()+8*60*60}
            return self.send_json({'ok':True,'name':user['name'],'role':user['role'],'token':token,'chant':track,'time':now(),'must_change_password':bool(user.get('must_change_password', user['username']=='admin' and user.get('password')==hashpw('Admin1234',user['salt'])[1]))})
        if self.path=='/api/logout':
            user=self.require_user()
            if not user: return
            token=self.headers.get('Authorization','').replace('Bearer ','').strip()
            SESSIONS.pop(token,None)
            return self.send_json({'ok':True})
        if self.path=='/api/change_password':
            user=self.require_user()
            if not user: return
            password=data.get('password','')
            if not valid_password(password): return self.send_json({'ok':False,'error':'گذرواژه باید دست‌کم ۱۰ نویسه داشته باشد'},400)
            account=next((x for x in DBDATA['users'] if x['username']==user['username']),None)
            if not account: return self.send_json({'ok':False,'error':'کاربر یافت نشد'},404)
            salt,digest=hashpw(password); account.update(salt=salt,password=digest,must_change_password=False); save_db(DBDATA)
            return self.send_json({'ok':True})
        if self.path=='/api/add_log':
            if not self.require_user(): return
            typ=data.get('type'); entry=data.get('entry',{})
            if typ not in ('repairs','equipment') or not isinstance(entry,dict): return self.send_json({'ok':False},400)
            if typ=='equipment' and data.get('photo_data'):
                try:
                    raw=base64.b64decode(data['photo_data'],validate=True)
                    if len(raw)>5*1024*1024: return self.send_json({'ok':False,'error':'حجم تصویر بیش از حد مجاز است'},400)
                    ext=Path(str(data.get('photo_name',''))).suffix.lower()
                    if ext not in ('.png','.jpg','.jpeg','.webp'): return self.send_json({'ok':False,'error':'قالب تصویر مجاز نیست'},400)
                    photo_name='handover_'+secrets.token_hex(12)+ext
                    photo_path=REPORTS/photo_name; photo_path.write_bytes(raw)
                    entry['photo_path']=str(photo_path)
                except Exception: return self.send_json({'ok':False,'error':'بارگذاری تصویر ناموفق بود'},400)
            entry.pop('photo_data',None)
            entry['timestamp']=now()
            DBDATA[typ].append(entry); save_db(DBDATA); return self.send_json({'ok':True,'timestamp':entry['timestamp']})
        if self.path=='/api/users':
            if not self.require_user(admin=True): return
            if data.get('action')=='list': return self.send_json({'ok':True,'users':[{k:v for k,v in u.items() if k not in ('salt','password')} for u in DBDATA['users']]})
            if data.get('action') in ('add','reset'):
                username=data.get('username','').strip(); password=data.get('password','')
                if not valid_username(username): return self.send_json({'ok':False,'error':'نام کاربری باید لاتین و ۳ تا ۳۲ نویسه باشد'},400)
                if not valid_password(password): return self.send_json({'ok':False,'error':'گذرواژه باید دست‌کم ۱۰ نویسه داشته باشد'},400)
                if data['action']=='add' and any(u['username']==username for u in DBDATA['users']): return self.send_json({'ok':False,'error':'این نام کاربری پیش‌تر ثبت شده است'},400)
                salt,digest=hashpw(password)
                if data['action']=='reset':
                    u=next((x for x in DBDATA['users'] if x['username']==username),None)
                    if not u: return self.send_json({'ok':False,'error':'کاربر یافت نشد'},404)
                    u.update(salt=salt,password=digest,must_change_password=True)
                    for token,session in list(SESSIONS.items()):
                        if session.get('username')==username: SESSIONS.pop(token,None)
                else: DBDATA['users'].append({'username':username,'name':data.get('name',username),'role':data.get('role','user'),'salt':salt,'password':digest,'active':True,'must_change_password':True})
                save_db(DBDATA); return self.send_json({'ok':True})
        if self.path=='/api/reports':
            if not self.require_user(): return
            equipment=[]
            for row in DBDATA.get('equipment',[]):
                item=dict(row)
                if item.get('photo_path'): item['photo_path']=os.path.basename(item['photo_path'])
                equipment.append(item)
            return self.send_json({'ok':True,'repairs':DBDATA.get('repairs',[]),'equipment':equipment})
        if self.path=='/api/chants':
            if not self.require_user(admin=True): return
            if data.get('action')=='list': return self.send_json({'ok':True,'chants':DBDATA['chants']})
            if data.get('action')=='reorder':
                order=data.get('chants',[])
                if not isinstance(order,list) or len(order)!=len(set(order)) or set(order)!=set(DBDATA['chants']):
                    return self.send_json({'ok':False,'error':'ترتیب نوحه‌ها معتبر نیست'},400)
                DBDATA['chants']=order; DBDATA['chant_index']=0; save_db(DBDATA)
                return self.send_json({'ok':True})
            if data.get('action')=='delete':
                name=os.path.basename(str(data.get('name','')))
                if name not in DBDATA['chants']: return self.send_json({'ok':False,'error':'نوحه پیدا نشد'},404)
                DBDATA['chants'].remove(name)
                DBDATA['chant_index']=DBDATA['chant_index']%max(1,len(DBDATA['chants']))
                target=AUDIO/name
                if target.exists(): target.unlink()
                save_db(DBDATA); return self.send_json({'ok':True})
            if data.get('action')=='upload':
                name=os.path.basename(str(data.get('name','')))
                if Path(name).suffix.lower() not in ('.mp3','.wav','.m4a'):
                    return self.send_json({'ok':False,'error':'قالب فایل صوتی مجاز نیست'},400)
                try: raw=base64.b64decode(data.get('content',''),validate=True)
                except Exception: return self.send_json({'ok':False,'error':'فایل فرستاده‌شده معتبر نیست'},400)
                if not raw or len(raw)>20*1024*1024:
                    return self.send_json({'ok':False,'error':'حجم فایل باید کمتر از ۲۰ مگابایت باشد'},400)
                dst=AUDIO/name
                dst.write_bytes(raw)
                if name not in DBDATA['chants']: DBDATA['chants'].append(name)
                save_db(DBDATA)
                return self.send_json({'ok':True,'name':name})
        return self.send_json({'ok':False,'error':'unknown'},404)

class ServerThread(threading.Thread):
    daemon=True
    def run(self):
        global SERVER
        SERVER=ThreadingHTTPServer(('0.0.0.0',8765),APIHandler); SERVER.serve_forever()


def fa(s):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(str(s)))
    except Exception: return str(s)

class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw); self.padding=dp(12); self.spacing=dp(8)
        with self.canvas.before:
            Color(0.93,0.95,0.95,1); self.bg=RoundedRectangle(pos=self.pos,size=self.size,radius=[dp(14)])
        self.bind(pos=self._upd,size=self._upd)
    def _upd(self,*a): self.bg.pos=self.pos; self.bg.size=self.size

def lbl(text, size=16, bold=False): return Label(text=fa(text),font_name='NotoFA',font_size=dp(size),bold=bold,halign='center',valign='middle')

def btn(text, cb, h=48):
    b=Button(text=fa(text),font_name='NotoFA',font_size=dp(16),size_hint_y=None,height=dp(h)); b.bind(on_release=cb); return b

class Login(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(18),spacing=dp(12))
        # portraits: top-right pair (Imam Khomeini + Ayatollah Khamenei), top-left (Seyyed Mojtaba)
        from kivy.uix.image import Image as KImage
        def portrait(fname):
            img=KImage(source=str(BASE/'assets'/fname), allow_stretch=True, keep_ratio=True,
                       size_hint=(None,None), size=(dp(96),dp(112)))
            return img
        portraits=BoxLayout(orientation='horizontal', size_hint=(1,None), height=dp(112))
        right_pair=BoxLayout(orientation='horizontal', size_hint=(None,1), width=dp(196), spacing=dp(4))
        right_pair.add_widget(portrait('khomeini.jpg')); right_pair.add_widget(portrait('khamenei.jpg'))
        portraits.add_widget(right_pair)
        portraits.add_widget(Widget())          # flexible space keeps pair on the right
        portraits.add_widget(portrait('mojtaba.jpg'))
        root.add_widget(portraits)
        # centered base emblem in the سامانه title frame
        from kivy.uix.anchorlayout import AnchorLayout
        anchor=AnchorLayout(anchor_x='center', anchor_y='center', size_hint=(1,None), height=dp(128))
        logo=KImage(source=str(BASE/'assets'/'emblem.png'), allow_stretch=True, keep_ratio=True,
                    size_hint=(None,None), size=(dp(128),dp(128)))
        anchor.add_widget(logo)
        root.add_widget(anchor)
        root.add_widget(lbl('سامانه آماد و پشتیبانی',30,True))
        root.add_widget(lbl('پایگاه شهید صیاد شیرازی',21))
        root.add_widget(lbl('بسم‌الله الرحمن الرحیم\nبسیج، لشکر مخلص خداست (امام خمینی، ره)\nبسیجی یعنی علی که تمام وجودش وقف اسلام بود (امام شهید، ره)',18))
        self.user=TextInput(hint_text=fa('نام کاربری (به حروف لاتین) را وارد کنید'),multiline=False)
        self.pw=TextInput(hint_text=fa('گذرواژه را وارد کنید'),password=True,multiline=False)
        self.url=TextInput(text=self._load_server_url(),multiline=False)
        self.url.bind(text=lambda inst,v:self._save_server_url(v))
        root.add_widget(self.user); root.add_widget(self.pw)
        root.add_widget(btn('ورود به سامانه',self.login))
        root.add_widget(btn('تنظیمات اتصال به سرور',self.connection_settings,36))
        self.add_widget(root)
    def _settings_path(self): return DATA/'server_url.txt'
    def _load_server_url(self):
        try: return self._settings_path().read_text(encoding='utf-8').strip() or 'http://127.0.0.1:8765'
        except Exception: return 'http://127.0.0.1:8765'
    def _save_server_url(self,v):
        try:
            DATA.mkdir(parents=True,exist_ok=True)
            self._settings_path().write_text(v.strip(),encoding='utf-8')
        except Exception: pass
    def connection_settings(self,*a):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
        box.add_widget(lbl('نشانی سرور (مثال: http://192.168.1.10:8765)',15))
        inp=TextInput(text=self.url.text,multiline=False)
        box.add_widget(inp)
        box.add_widget(btn('ذخیرهٔ نشانی',lambda b:self._apply_url(inp),46))
        box.add_widget(btn('راه‌اندازی سرور روی این تلفن',self.server_mode,46))
        Popup(title=fa('تنظیمات اتصال به سرور'),content=box,size_hint=(.92,.46)).open()
    def _apply_url(self,inp):
        self.url.text=inp.text.strip() or 'http://127.0.0.1:8765'
    def login(self,*a):
        try:
            data=json.dumps({'username':self.user.text.strip(),'password':self.pw.text}).encode(); req=urllib.request.Request(self.url.text.rstrip('/')+'/api/login',data=data,headers={'Content-Type':'application/json'}); r=json.loads(urllib.request.urlopen(req,timeout=5).read().decode())
            if not r.get('ok'): raise Exception(r.get('error','خطا'))
            App.get_running_app().state.update(user=r,server_url=self.url.text.rstrip('/'))
            if r.get('must_change_password'):
                self.prompt_password_change()
            else:
                self.manager.current='home'
                if r.get('chant'): App.get_running_app().play_chant(r['chant'])
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),16),size_hint=(.9,.35)).open()
    def prompt_password_change(self):
        box=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
        new=TextInput(hint_text=fa('گذرواژهٔ تازه (دست‌کم ۱۰ نویسه)'),password=True,multiline=False)
        confirm=TextInput(hint_text=fa('تکرار گذرواژهٔ تازه'),password=True,multiline=False)
        box.add_widget(lbl('برای ادامه، گذرواژهٔ اولیه را تغییر دهید.',15)); box.add_widget(new); box.add_widget(confirm)
        pop=Popup(title=fa('تغییر اجباری گذرواژه'),content=box,size_hint=(.9,.48),auto_dismiss=False)
        def submit(*args):
            if len(new.text)<10 or new.text!=confirm.text:
                Popup(title=fa('بررسی گذرواژه'),content=lbl('گذرواژه باید دست‌کم ۱۰ نویسه داشته باشد و دو ورودی یکسان باشند.',14),size_hint=(.9,.3)).open(); return
            try:
                app=App.get_running_app(); payload=json.dumps({'password':new.text}).encode()
                req=urllib.request.Request(app.state['server_url']+'/api/change_password',data=payload,headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state['user']['token']})
                result=json.loads(urllib.request.urlopen(req,timeout=8).read().decode('utf-8'))
                if not result.get('ok'): raise Exception(result.get('error','تغییر گذرواژه ناموفق بود'))
                pop.dismiss(); app.state['user']['must_change_password']=False; self.manager.current='home'
                if app.state['user'].get('chant'): app.play_chant(app.state['user']['chant'])
            except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()
        box.add_widget(btn('ثبت گذرواژهٔ تازه',submit,48)); pop.open()
    def server_mode(self,*a):
        # Starting the local server must never grant an administrator session.
        # The operator must authenticate through the same login endpoint as every other user.
        if SERVER is None:
            ServerThread().start()
            time.sleep(0.15)
        self.url.text='http://127.0.0.1:8765'
        Popup(title=fa('سرور محلی راه‌اندازی شد'),
              content=lbl('سرور این تلفن همراه فعال شد. برای ورود، نام کاربری و رمز عبور معتبر مدیر را وارد کنید. راه‌اندازی سرور به‌تنهایی دسترسی مدیریتی ایجاد نمی‌کند.',15),
              size_hint=(.92,.38)).open()

class Home(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        root.add_widget(lbl('سامانه آماد و پشتیبانی',28,True))
        root.add_widget(lbl(datetime.now().strftime('%Y/%m/%d   %H:%M:%S'),20,True))
        self.clock=Clock.schedule_interval(self.tick,1)
        grid=GridLayout(cols=2,spacing=dp(8),size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        user=App.get_running_app().state.get('user',{})
        items=[('تعمیرات','repairs'),('تحویل و عودت تجهیزات','equipment'),('گزارش‌ها','reports'),('تغییر گذرواژه','change_password')]
        if user.get('role')=='admin': items += [('مدیریت کاربران','users'),('مدیریت نوحه‌ها (ویژهٔ مدیر)','chants'),('تنظیمات سرور','server')]
        for t,screen in items:
            grid.add_widget(btn(t,lambda b,s=screen:self.go(s),60))
        root.add_widget(grid)
        root.add_widget(btn('خروج',lambda b:self.logout(),48))
        self.add_widget(root)
    def tick(self,*a):
        for w in self.children:
            if isinstance(w,BoxLayout):
                for x in w.children:
                    if isinstance(x,Label) and ':' in x.text and '/' in x.text: x.text=datetime.now().strftime('%Y/%m/%d   %H:%M:%S')
    def go(self,s):
        if s in ('users','chants','server') and App.get_running_app().state.get('user',{}).get('role')!='admin':
            Popup(title=fa('عدم دسترسی'),content=lbl('این بخش فقط برای مدیر سامانه است',16),size_hint=(.8,.3)).open(); return
        self.manager.current=s
    def logout(self):
        try:
            app=App.get_running_app()
            if app.state.get('server_url') and app.state.get('user',{}).get('token'):
                req=urllib.request.Request(app.state['server_url']+'/api/logout',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state['user']['token']})
                urllib.request.urlopen(req,timeout=3).read()
        except Exception: pass
        try: self.clock.cancel()
        except: pass
        App.get_running_app().state={}
        self.manager.current='login'

class SimpleLog(Screen):
    typ='repairs'; title=''
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl(self.title,24,True)); self.person=TextInput(hint_text=fa('نام یا واحد مربوط را وارد کنید'),multiline=False); self.desc=TextInput(hint_text=fa('شرح رویداد را وارد کنید'),multiline=False); root.add_widget(self.person); root.add_widget(self.desc); root.add_widget(btn('ثبت رویداد با تاریخ و ساعت دقیق',self.save)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def save(self,*a):
        try:
            data={'type':self.typ,'entry':{'person':self.person.text,'description':self.desc.text}}; req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/add_log',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+App.get_running_app().state.get('user',{}).get('token','')}); urllib.request.urlopen(req,timeout=5); Popup(title=fa('ثبت شد'),content=lbl(now(),18),size_hint=(.8,.3)).open(); self.person.text=''; self.desc.text=''
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),16),size_hint=(.9,.3)).open()

class EquipmentScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(7))
        root.add_widget(lbl('ثبت تحویل و عودت تجهیزات',23,True))
        scroll=ScrollView()
        form=BoxLayout(orientation='vertical',padding=dp(4),spacing=dp(7),size_hint_y=None)
        form.bind(minimum_height=form.setter('height'))
        self.first=TextInput(hint_text=fa('نام را وارد کنید'),multiline=False,size_hint_y=None,height=dp(46))
        self.last=TextInput(hint_text=fa('نام خانوادگی را وارد کنید'),multiline=False,size_hint_y=None,height=dp(46))
        self.father=TextInput(hint_text=fa('نام پدر را وارد کنید'),multiline=False,size_hint_y=None,height=dp(46))
        self.national=TextInput(hint_text=fa('کد ملی را وارد کنید'),multiline=False,size_hint_y=None,height=dp(46))
        self.phone=TextInput(hint_text=fa('شمارهٔ تلفن را وارد کنید'),multiline=False,size_hint_y=None,height=dp(46))
        self.equipment=TextInput(hint_text=fa('مشخصات تجهیزات، تعداد و کد آن‌ها را وارد کنید'),multiline=True,size_hint_y=None,height=dp(90))
        self.signature=TextInput(hint_text=fa('نام یا توضیح امضای تحویل‌گیرنده (اختیاری)'),multiline=False,size_hint_y=None,height=dp(46))
        for field in (self.first,self.last,self.father,self.national,self.phone,self.equipment,self.signature):
            form.add_widget(field)
        form.add_widget(btn('افزودن تصویر مأمور',self.pick_photo,46))
        self.photo_label=lbl('تصویری انتخاب نشده است',14)
        form.add_widget(self.photo_label)
        scroll.add_widget(form); root.add_widget(scroll)
        root.add_widget(btn('ثبت تحویل تجهیزات و آماده‌سازی کارت',lambda b:self.save_handover('تحویل تجهیزات'),50))
        root.add_widget(btn('ثبت عودت تجهیزات و آماده‌سازی کارت',lambda b:self.save_handover('عودت تجهیزات'),50))
        root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'),44))
        self.add_widget(root)
        self.photo_path=''

    def pick_photo(self,*a):
        start='/storage/emulated/0/Download' if os.path.isdir('/storage/emulated/0/Download') else str(Path.home())
        fc=FileChooserListView(path=start,filters=['*.png','*.jpg','*.jpeg','*.webp'])
        box=BoxLayout(orientation='vertical',spacing=dp(6))
        box.add_widget(fc)
        pop=Popup(title=fa('انتخاب تصویر مأمور'),content=box,size_hint=(.95,.9))
        box.add_widget(btn('انتخاب عکس',lambda b:self._copy_photo(fc.selection,pop),44))
        self.photo_popup=pop; pop.open()

    def _copy_photo(self,selection,popup):
        if not selection:
            Popup(title=fa('توجه'),content=lbl('ابتدا یک تصویر انتخاب کنید',15),size_hint=(.8,.3)).open()
            return
        src=Path(selection[0])
        safe_name='officer_'+str(int(time.time()))+src.suffix.lower()
        dst=REPORTS/safe_name
        try:
            dst.write_bytes(src.read_bytes())
            self.photo_path=str(dst)
            self.photo_label.text=fa('تصویر پیوست شد: '+src.name)
            popup.dismiss()
        except Exception as e:
            Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()

    def save_handover(self,record_type='تحویل تجهیزات'):
        first=self.first.text.strip(); last=self.last.text.strip()
        equipment=self.equipment.text.strip()
        if not first or not last or not equipment:
            Popup(title=fa('اطلاعات ناقص'),content=lbl('نام، نام خانوادگی و مشخصات تجهیزات را وارد کنید',15),size_hint=(.9,.3)).open()
            return
        entry={
            'first_name':first,'last_name':last,'father_name':self.father.text.strip(),
            'national_id':self.national.text.strip(),'phone':self.phone.text.strip(),
            'equipment_details':equipment,'signature':self.signature.text.strip(),
            'photo_path':self.photo_path,'timestamp':now(),'record_type':record_type
        }
        try:
            data={'type':'equipment','entry':dict(entry)}
            if self.photo_path and Path(self.photo_path).exists():
                data['photo_data']=base64.b64encode(Path(self.photo_path).read_bytes()).decode('ascii')
                data['photo_name']=Path(self.photo_path).name
                data['entry'].pop('photo_path',None)
            req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/add_log',
                data=json.dumps(data,ensure_ascii=False).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+App.get_running_app().state.get('user',{}).get('token','')})
            response=json.loads(urllib.request.urlopen(req,timeout=20).read().decode('utf-8'))
            if not response.get('ok'): raise Exception(response.get('error','ثبت اطلاعات ناموفق بود'))
            entry['timestamp']=response.get('timestamp',entry['timestamp'])
            card_path=make_handover_card(entry)
            notice=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
            notice.add_widget(lbl('اطلاعات ثبت شد. کارت برای چاپ آماده است. برای فرستادن مشخصات به پیام‌رسان‌های نصب‌شده، گزینهٔ ارسال را انتخاب کنید.',14))
            notice.add_widget(btn('ارسال از طریق ایتا، روبیکا، سروش یا بله',lambda b:share_handover_entry(entry),48))
            notice.add_widget(btn('بستن',lambda b:result_popup.dismiss(),42))
            result_popup=Popup(title=fa('ثبت و آماده‌سازی کارت'),content=notice,size_hint=(.95,.48))
            result_popup.open()
            for field in (self.first,self.last,self.father,self.national,self.phone,self.equipment,self.signature):
                field.text=''
            self.photo_path=''; self.photo_label.text=fa('تصویری انتخاب نشده است')
        except Exception as e:
            Popup(title=fa('خطا در ثبت'),content=lbl(str(e),14),size_hint=(.9,.35)).open()

class ChangePassword(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(9))
        root.add_widget(lbl('تغییر گذرواژه',24,True))
        self.new=TextInput(hint_text=fa('گذرواژهٔ تازه (دست‌کم ۱۰ نویسه)'),password=True,multiline=False)
        self.confirm=TextInput(hint_text=fa('تکرار گذرواژهٔ تازه'),password=True,multiline=False)
        root.add_widget(self.new); root.add_widget(self.confirm)
        root.add_widget(btn('ثبت گذرواژهٔ تازه',self.save)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home')))
        self.add_widget(root)
    def save(self,*a):
        if len(self.new.text)<10 or self.new.text!=self.confirm.text:
            Popup(title=fa('بررسی گذرواژه'),content=lbl('گذرواژه باید دست‌کم ۱۰ نویسه داشته باشد و دو ورودی یکسان باشند.',14),size_hint=(.9,.3)).open(); return
        try:
            app=App.get_running_app(); payload=json.dumps({'password':self.new.text}).encode()
            req=urllib.request.Request(app.state['server_url']+'/api/change_password',data=payload,headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state['user']['token']})
            result=json.loads(urllib.request.urlopen(req,timeout=8).read().decode('utf-8'))
            if not result.get('ok'): raise Exception(result.get('error','تغییر گذرواژه ناموفق بود'))
            Popup(title=fa('انجام شد'),content=lbl('گذرواژه با موفقیت تغییر کرد.',14),size_hint=(.8,.3)).open()
            self.new.text=''; self.confirm.text=''; app.state['user']['must_change_password']=False
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()


class Users(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        root.add_widget(lbl('مدیریت کاربران',24,True))
        self.u=TextInput(hint_text=fa('نام کاربری (به حروف لاتین) را وارد کنید'),multiline=False)
        self.first=TextInput(hint_text=fa('نام کاربر را وارد کنید'),multiline=False)
        self.last=TextInput(hint_text=fa('نام خانوادگی کاربر را وارد کنید'),multiline=False)
        root.add_widget(self.u); root.add_widget(self.first); root.add_widget(self.last)
        root.add_widget(lbl('گذرواژهٔ اولیه به‌صورت خودکار ساخته می‌شود: حرف نخست نام + رشتهٔ تصادفی + حرف نخست نام خانوادگی.',13))
        root.add_widget(btn('ایجاد کاربر',self.add)); root.add_widget(btn('بازنشانی گذرواژهٔ کاربر',self.reset))
        root.add_widget(btn('نمایش فهرست کاربران',self.list_users))
        self.user_list=lbl('',14); root.add_widget(self.user_list)
        root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home')))
        self.add_widget(root)
    def call(self,action):
        first=self.first.text.strip(); last=self.last.text.strip()
        if not first or not last: raise ValueError('نام و نام خانوادگی را وارد کنید')
        password=first[0].upper()+secrets.token_hex(5)+last[0].lower()
        self.generated_password=password
        data={'action':action,'username':self.u.text.strip(),'name':first+' '+last,'password':password}
        req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/users',data=json.dumps(data,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+App.get_running_app().state.get('user',{}).get('token','')})
        return json.loads(urllib.request.urlopen(req,timeout=8).read().decode())
    def list_users(self,*a):
        try:
            data={'action':'list'}
            app=App.get_running_app()
            req=urllib.request.Request(app.state['server_url']+'/api/users',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state.get('user',{}).get('token','')})
            result=json.loads(urllib.request.urlopen(req,timeout=8).read().decode('utf-8'))
            if not result.get('ok'): raise Exception(result.get('error','دریافت فهرست کاربران ناموفق بود'))
            rows=[]
            for user in result.get('users',[]):
                status='فعال' if user.get('active',True) else 'غیرفعال'
                role='مدیر' if user.get('role')=='admin' else 'کاربر'
                rows.append(f"{user.get('username','')} — {user.get('name','')} — {role} — {status}")
            self.user_list.text=fa('\n'.join(rows)) if rows else fa('کاربری ثبت نشده است')
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()
    def add(self,*a):
        try: r=self.call('add'); Popup(title=fa('نتیجه'),content=lbl(('کاربر ایجاد شد. گذرواژهٔ اولیه (فقط این بار نمایش داده می‌شود): '+self.generated_password) if r.get('ok') else r.get('error'),16),size_hint=(.8,.3)).open()
        except Exception as e: Popup(title=fa('خطا'),content=lbl(e,16)).open()
    def reset(self,*a):
        try: r=self.call('reset'); Popup(title=fa('نتیجه'),content=lbl(('گذرواژه بازنشانی شد. گذرواژهٔ تازه (فقط این بار نمایش داده می‌شود): '+self.generated_password) if r.get('ok') else r.get('error'),16),size_hint=(.8,.3)).open()
        except Exception as e: Popup(title=fa('خطا'),content=lbl(e,16)).open()

class Chants(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        root.add_widget(lbl('مدیریت نوحه‌ها — ویژهٔ مدیر سامانه',22,True))
        root.add_widget(btn('افزودن فایل نوحه',self.pick))
        root.add_widget(btn('به‌روزرسانی فهرست',self.load_chants))
        self.list_box=BoxLayout(orientation='vertical',spacing=dp(5),size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        scroll=ScrollView(); scroll.add_widget(self.list_box); root.add_widget(scroll)
        root.add_widget(lbl('ترتیب این فهرست، ترتیب پخش نوحه‌ها هنگام ورود کاربران است.',13))
        root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home')))
        self.add_widget(root); self.load_chants()
    def api(self,payload):
        app=App.get_running_app()
        req=urllib.request.Request(app.state['server_url']+'/api/chants',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state.get('user',{}).get('token','')})
        result=json.loads(urllib.request.urlopen(req,timeout=15).read().decode('utf-8'))
        if not result.get('ok'): raise Exception(result.get('error','درخواست ناموفق بود'))
        return result
    def load_chants(self,*a):
        try:
            names=self.api({'action':'list'}).get('chants',[])
            self.chant_names=list(names); self.list_box.clear_widgets()
            if not names: self.list_box.add_widget(lbl('هنوز نوحه‌ای بارگذاری نشده است',14)); return
            for index,name in enumerate(names):
                row=BoxLayout(size_hint_y=None,height=dp(48),spacing=dp(4))
                row.add_widget(lbl(f'{index+1}. {name}',13))
                row.add_widget(btn('بالا',lambda b,i=index:self.move_chant(i,-1),38))
                row.add_widget(btn('پایین',lambda b,i=index:self.move_chant(i,1),38))
                row.add_widget(btn('حذف',lambda b,n=name:self.delete_chant(n),38))
                self.list_box.add_widget(row)
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()
    def move_chant(self,index,delta):
        target=index+delta
        if target<0 or target>=len(self.chant_names): return
        names=list(self.chant_names); names[index],names[target]=names[target],names[index]
        try: self.api({'action':'reorder','chants':names}); self.load_chants()
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()
    def delete_chant(self,name):
        box=BoxLayout(orientation='vertical',padding=dp(8),spacing=dp(8))
        box.add_widget(lbl('آیا از حذف این نوحه اطمینان دارید؟',14))
        pop=Popup(title=fa('تأیید حذف'),content=box,size_hint=(.85,.32))
        def confirm(*args):
            try: self.api({'action':'delete','name':name}); pop.dismiss(); self.load_chants()
            except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()
        box.add_widget(btn('حذف نوحه',confirm,42)); box.add_widget(btn('انصراف',lambda b:pop.dismiss(),40)); pop.open()
    def pick(self,*a):
        start='/storage/emulated/0/Download' if os.path.isdir('/storage/emulated/0/Download') else str(Path.home())
        fc=FileChooserListView(path=start,filters=['*.mp3','*.wav','*.m4a'])
        box=BoxLayout(orientation='vertical'); box.add_widget(fc)
        box.add_widget(btn('انتخاب',lambda b:self.copy(fc.selection),48))
        p=Popup(title=fa('انتخاب نوحه'),content=box,size_hint=(.95,.9)); self.pop=p; p.open()
    def copy(self,sel):
        if not sel: return
        try:
            src=Path(sel[0])
            payload={'action':'upload','name':src.name,'content':base64.b64encode(src.read_bytes()).decode('ascii')}
            self.api(payload); self.pop.dismiss(); self.load_chants()
            Popup(title=fa('ثبت شد'),content=lbl(src.name+'\nفایل روی سرور ذخیره شد.',16),size_hint=(.85,.32)).open()
        except Exception as e: Popup(title=fa('خطا در بارگذاری'),content=lbl(str(e),14),size_hint=(.9,.35)).open()

class Reports(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('گزارش‌ها',24,True)); root.add_widget(btn('دریافت فایل Word',lambda b:self.export('docx'))); root.add_widget(btn('دریافت فایل PDF',lambda b:self.export('pdf'))); root.add_widget(btn('تهیهٔ کارت چاپی برای آخرین تحویل',self.export_latest_card)); root.add_widget(btn('ارسال آخرین کارت در پیام‌رسان‌ها',self.share_latest_card)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def get_records(self):
        app=App.get_running_app()
        req=urllib.request.Request(app.state['server_url']+'/api/reports',data=b'{}',
            headers={'Content-Type':'application/json','Authorization':'Bearer '+app.state.get('user',{}).get('token','')})
        result=json.loads(urllib.request.urlopen(req,timeout=10).read().decode('utf-8'))
        if not result.get('ok'): raise Exception(result.get('error','دریافت گزارش ناموفق بود'))
        for item in result.get('equipment',[]):
            photo=item.get('photo_path','')
            if photo and not Path(photo).exists():
                photo_req=urllib.request.Request(app.state['server_url']+'/api/photo/'+urllib.parse.quote(photo),headers={'Authorization':'Bearer '+app.state.get('user',{}).get('token','')})
                try:
                    raw=urllib.request.urlopen(photo_req,timeout=10).read()
                    local_photo=REPORTS/photo
                    local_photo.write_bytes(raw)
                    item['photo_path']=str(local_photo)
                except Exception: item['photo_path']=''
        return result
    def export_latest_card(self,*a):
        try: records=self.get_records().get('equipment',[])
        except Exception as e:
            Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.35)).open(); return
        if not records:
            Popup(title=fa('گزارش‌ها'),content=lbl('هنوز اطلاعاتی دربارهٔ تحویل تجهیزات ثبت نشده است',15),size_hint=(.85,.3)).open(); return
        path=make_handover_card(records[-1])
        try: webbrowser.open(Path(path).resolve().as_uri())
        except Exception: pass
        Popup(title=fa('کارت آمادهٔ چاپ'),content=lbl('کارت HTML در این مسیر ذخیره شد:\n'+str(path)+'\nآن را در مرورگر باز و چاپ کنید.',14),size_hint=(.95,.45)).open()

    def share_latest_card(self,*a):
        try: records=self.get_records().get('equipment',[])
        except Exception as e:
            Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.35)).open(); return
        if not records:
            Popup(title=fa('گزارش‌ها'),content=lbl('هنوز اطلاعاتی دربارهٔ تحویل تجهیزات ثبت نشده است',15),size_hint=(.85,.3)).open(); return
        share_handover_entry(records[-1])

    def export(self,kind):
        try:
            records=self.get_records()
            text=format_report(records)
            if kind=='docx': path=REPORTS/'report.docx'; make_docx(path,text)
            else: path=REPORTS/'report.pdf'; make_pdf(path,text)
            Popup(title=fa('گزارش آماده شد'),content=lbl(str(path),14),size_hint=(.95,.4)).open()
        except Exception as e:
            Popup(title=fa('خطا در تهیه گزارش'),content=lbl(str(e),14),size_hint=(.9,.35)).open()

class ServerScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(8))
        root.add_widget(lbl('تنظیمات سرور',24,True))
        root.add_widget(lbl('درگاه: ۸۷۶۵',18))
        root.add_widget(lbl('\n'.join('نشانی این تلفن در شبکه: http://'+ip+':8765' for ip in local_ips()),16))
        login=App.get_running_app().root.get_screen('login') if App.get_running_app().root else None
        current=login.url.text if login else 'http://127.0.0.1:8765'
        root.add_widget(lbl('نشانی سروری که این دستگاه به آن متصل می‌شود:',16))
        self.url_inp=TextInput(text=current,hint_text=fa('مثال: http://192.168.1.10:8765'),multiline=False,size_hint_y=None,height=dp(46))
        root.add_widget(self.url_inp)
        root.add_widget(btn('ذخیرهٔ نشانی',self.save_url,46))
        root.add_widget(lbl('سه تلفن همراه دیگر می‌توانند با همین نشانی و در همان شبکه به سرور متصل شوند.',15))
        root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'),44))
        self.add_widget(root)
    def save_url(self,*a):
        login=App.get_running_app().root.get_screen('login')
        login.url.text=self.url_inp.text.strip() or 'http://127.0.0.1:8765'
        Popup(title=fa('ذخیره شد'),content=lbl('نشانی سرور به‌روزرسانی شد',15),size_hint=(.8,.28)).open()

def share_handover_entry(entry):
    """Open Android's native share chooser with the handover-card details as text."""
    lines=[
        'کارت تحویل تجهیزات - پایگاه شهید صیاد شیرازی',
        'نام: '+str(entry.get('first_name','')),
        'نام خانوادگی: '+str(entry.get('last_name','')),
        'نام پدر: '+str(entry.get('father_name','')),
        'کد ملی: '+str(entry.get('national_id','')),
        'شماره تلفن: '+str(entry.get('phone','')),
        'مشخصات تجهیزات: '+str(entry.get('equipment_details','')),
        'تاریخ و ساعت تحویل: '+str(entry.get('timestamp','')),
        'امضای تحویل‌گیرنده: '+str(entry.get('signature','')),
    ]
    payload='\n'.join(lines)
    try:
        from jnius import autoclass
        Intent=autoclass('android.content.Intent')
        String=autoclass('java.lang.String')
        PythonActivity=autoclass('org.kivy.android.PythonActivity')
        activity=PythonActivity.mActivity
        intent=Intent(Intent.ACTION_SEND)
        intent.setType('text/plain')
        intent.putExtra(Intent.EXTRA_SUBJECT,String('کارت تحویل تجهیزات'))
        intent.putExtra(Intent.EXTRA_TEXT,String(payload))
        chooser=Intent.createChooser(intent,String('ارسال کارت از طریق پیام‌رسان'))
        activity.startActivity(chooser)
        return True
    except Exception as e:
        Popup(title=fa('ارسال'),content=lbl('ارسال مستقیم فقط در نسخهٔ اندروید امکان‌پذیر است.\n'+str(e),14),size_hint=(.92,.4)).open()
        return False

def make_handover_card(entry):
    """Create a printer-friendly ID-card-sized HTML file for an equipment handover."""
    photo=entry.get('photo_path','')
    photo_html=''
    if photo and Path(photo).exists():
        photo_uri=Path(photo).resolve().as_uri()
        photo_html=f'<img class="photo" src="{html.escape(photo_uri, quote=True)}" alt="تصویر مأمور">'
    def value(key):
        return html.escape(str(entry.get(key,'') or '—'))
    timestamp=value('timestamp')
    card=f'''<!doctype html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>کارت تحویل تجهیزات</title>
<style>
@page {{ size: 85.6mm 54mm; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font-family: Tahoma, Arial, sans-serif; }}
.card {{ width: 85.6mm; height: 54mm; border: 1px solid #333; padding: 3mm; position: relative; overflow: hidden; direction: rtl; }}
.photo {{ position: absolute; top: 3mm; left: 3mm; width: 19mm; height: 22mm; object-fit: cover; border: 1px solid #555; }}
h3 {{ text-align: center; font-size: 10pt; margin: 0 20mm 2mm 20mm; }}
.row {{ font-size: 7.5pt; margin: 1.1mm 0; line-height: 1.2; }}
.details {{ height: 10mm; overflow: hidden; white-space: pre-wrap; }}
.sign {{ position: absolute; bottom: 3mm; right: 3mm; left: 3mm; border-top: 1px solid #777; padding-top: 1.5mm; font-size: 7pt; }}
@media screen {{ body {{ background: #eee; padding: 10mm; }} .card {{ background: white; margin: auto; }} }}
</style></head><body><section class="card">
{photo_html}<h3>کارت تحویل تجهیزات</h3>
<div class="row">نام: {value('first_name')}　 نام خانوادگی: {value('last_name')}</div>
<div class="row">نام پدر: {value('father_name')}　 کد ملی: {value('national_id')}</div>
<div class="row">شماره تلفن: {value('phone')}</div>
<div class="row">مشخصات تجهیزات: <span class="details">{value('equipment_details')}</span></div>
<div class="row">تاریخ و ساعت تحویل: {timestamp}</div>
<div class="sign">امضای تحویل‌گیرنده: {value('signature')}　　امضای تحویل‌دهنده: __________________</div>
</section><script>window.onload=()=>{{if(new URLSearchParams(location.search).has('print')) window.print();}}</script></body></html>'''
    target=REPORTS/('handover_card_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.html')
    target.write_text(card,encoding='utf-8')
    return target

def format_report(records):
    lines=['گزارش سامانه آماد و پشتیبانی پایگاه شهید صیاد شیرازی','تاریخ و ساعت تهیه گزارش: '+now(),'']
    sections=[
        ('گزارش تعمیرات',records.get('repairs',[]),'repairs'),
        ('گزارش تحویل و عودت تجهیزات',records.get('equipment',[]),'equipment')
    ]
    for title,items,kind in sections:
        lines.extend([title,'تعداد موارد ثبت‌شده: '+str(len(items)),''])
        if not items:
            lines.append('موردی ثبت نشده است.'); lines.append('')
            continue
        for index,item in enumerate(items,1):
            lines.append('ردیف '+str(index))
            if kind=='repairs':
                lines.append('نام یا واحد: '+str(item.get('person','—')))
                lines.append('شرح تعمیرات: '+str(item.get('description','—')))
            else:
                lines.append('نوع رویداد: '+str(item.get('record_type','تحویل تجهیزات')))
                lines.append('نام: '+str(item.get('first_name','—')))
                lines.append('نام خانوادگی: '+str(item.get('last_name','—')))
                lines.append('نام پدر: '+str(item.get('father_name','—')))
                lines.append('کد ملی: '+str(item.get('national_id','—')))
                lines.append('شمارهٔ تلفن: '+str(item.get('phone','—')))
                lines.append('مشخصات تجهیزات: '+str(item.get('equipment_details','—')))
                lines.append('امضای تحویل‌گیرنده: '+str(item.get('signature','—')))
            lines.append('تاریخ و ساعت ثبت: '+str(item.get('timestamp','—')))
            lines.append('')
    return '\n'.join(lines)


def make_docx(path,text):
    import zipfile, html
    body=''.join(f'<w:p><w:pPr><w:bidi/></w:pPr><w:r><w:rPr><w:rtl/><w:rFonts w:ascii="Noto Naskh Arabic" w:hAnsi="Noto Naskh Arabic" w:cs="Noto Naskh Arabic"/><w:lang w:val="fa-IR"/></w:rPr><w:t xml:space="preserve">{html.escape(line)}</w:t></w:r></w:p>' for line in text.splitlines())
    files={'[Content_Types].xml':'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>','_rels/.rels':'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>','word/document.xml':f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr/></w:body></w:document>'}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,c in files.items(): z.writestr(n,c)

def make_pdf(path,text):
    # Embed the application's Arabic-capable font and shape Persian text before layout.
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from xml.sax.saxutils import escape
    font_path=FONT if Path(FONT).exists() else FONT_B
    if not Path(font_path).exists():
        raise RuntimeError('قلم فارسی برای ساخت PDF پیدا نشد')
    if 'NotoFAReport' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('NotoFAReport',font_path))
    style=ParagraphStyle('Persian',fontName='NotoFAReport',fontSize=9,leading=16,
                         alignment=TA_RIGHT,wordWrap='RTL',spaceAfter=5)
    story=[]
    for line in text.replace('\r','').splitlines():
        if not line.strip():
            story.append(Spacer(1,5))
        else:
            shaped=fa(line)
            story.append(Paragraph(escape(shaped),style))
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=38,leftMargin=38,
                          topMargin=38,bottomMargin=38,title='گزارش سامانه آماد و پشتیبانی')
    doc.build(story)

class SplashBadge(Widget):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            Color(0.27, 0.34, 0.16, 1)
            self._circle = __import__('kivy.graphics', fromlist=['Ellipse']).Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_circle, size=self._sync_circle)

    def _sync_circle(self, *args):
        self._circle.pos = self.pos
        self._circle.size = self.size


class AmadApp(App):
    def on_start(self):
        try:
            from kivy.utils import platform
            if platform == 'android':
                from android.permissions import request_permissions, Permission
                permissions=[Permission.READ_EXTERNAL_STORAGE]
                for permission_name in ('READ_MEDIA_AUDIO','READ_MEDIA_IMAGES'):
                    permission=getattr(Permission,permission_name,None)
                    if permission: permissions.append(permission)
                request_permissions(permissions)
        except Exception:
            pass

    def build(self):
        boot_log('build(): entered')
        self.title = 'سامانه آماد و پشتیبانی پایگاه شهید صیاد شیرازی'
        self.state={}
        sm=ScreenManager()
        # --- splash as a Screen (no root swap -> fixes black screen) ---
        from kivy.uix.image import Image as _BadgeImage
        splash_screen = Screen(name='splash')
        splash = BoxLayout(orientation='vertical', padding=dp(28), spacing=dp(10))
        with splash.canvas.before:
            Color(0.063, 0.125, 0.227, 1)  # same navy as presplash #10203A
            self._splash_bg = RoundedRectangle(pos=splash.pos, size=splash.size, radius=[0])
        splash.bind(pos=lambda w, v: setattr(self._splash_bg, 'pos', v),
                    size=lambda w, v: setattr(self._splash_bg, 'size', v))
        splash.add_widget(Widget(size_hint=(1, None), height=dp(30)))
        badge_box = BoxLayout(orientation='vertical', size_hint=(1, None), height=dp(230),
                              padding=dp(10))
        # clean circular transparent emblem, fully inside circle
        emblem_src = str(BASE / 'assets' / 'emblem.png')
        try:
            import os as _os
            if not _os.path.exists(emblem_src):
                emblem_src = str(BASE / 'icon.png')
        except Exception:
            pass
        badge = _BadgeImage(source=emblem_src, allow_stretch=True, keep_ratio=True,
                            size_hint=(None, None), size=(dp(200), dp(200)),
                            pos_hint={'center_x': .5})
        badge_box.add_widget(badge)
        splash.add_widget(badge_box)
        splash.add_widget(Label(text=fa('سامانه آماد و پشتیبانی'),
                                font_name='NotoFA', font_size='25sp',
                                color=(0.92, 0.80, 0.36, 1), size_hint=(1, None), height=dp(52)))
        splash.add_widget(Label(text=fa('پایگاه شهید صیاد شیرازی'),
                                font_name='NotoFA', font_size='19sp',
                                color=(1, 1, 1, 1), size_hint=(1, None), height=dp(42)))
        splash.add_widget(Label(text=fa('در حال بارگذاری...'),
                                font_name='NotoFA', font_size='14sp',
                                color=(0.78, 0.78, 0.78, 1), size_hint=(1, None), height=dp(30)))
        splash.add_widget(Widget())
        splash_screen.add_widget(splash)
        sm.add_widget(splash_screen)
        try:
            from kivy.uix.screenmanager import NoTransition
            sm.transition=NoTransition()
        except Exception:
            pass
        def _safe_add(w):
            try:
                sm.add_widget(w)
                try: boot_log('add '+w.name+' OK')
                except: pass
            except Exception as e:
                try: boot_log('add '+getattr(w,'name','?')+' FAIL: %s'%e)
                except: pass
        _safe_add(Login(name='login')); _safe_add(Home(name='home'))
        try:
            _r=SimpleLog(name='repairs'); _r.typ='repairs'; _r.title='تعمیرات'; _safe_add(_r)
        except Exception as e:
            try: boot_log('repairs FAIL %s'%e)
            except: pass
        for _cls,_nm in [(EquipmentScreen,'equipment'),(Reports,'reports'),(Users,'users'),(Chants,'chants'),(ServerScreen,'server'),(ChangePassword,'change_password')]:
            try: _safe_add(_cls(name=_nm))
            except Exception as e:
                try: boot_log(_nm+' FAIL %s'%e)
                except: pass
        sm.current = 'splash'
        self._main_root = sm
        Clock.schedule_once(self._show_main, 3.0)
        boot_log('build(): returning ScreenManager with splash')
        return sm

    def _show_main(self, dt):
        boot_log('_show_main: switching splash -> login')
        try:
            if hasattr(self, '_main_root') and self._main_root is not None:
                self._main_root.current = 'login'
                boot_log('_show_main: switched to login OK')
        except Exception as e:
            boot_log('_show_main FAILED: %s' % e)

    def play_chant(self, name):
        url=self.state['server_url']+'/audio/'+urllib.parse.quote(name); local=AUDIO/name
        try:
            if not local.exists():
                req=urllib.request.Request(url,headers={'Authorization':'Bearer '+self.state.get('user',{}).get('token','')})
                with urllib.request.urlopen(req,timeout=15) as response:
                    local.write_bytes(response.read())
            s=SoundLoader.load(str(local))
            if s: s.play()
        except Exception: pass

def run_app():
    boot_log('run_app: entering')
    try:
        boot_log('run_app: AmadApp().run() starting')
        AmadApp().run()
        boot_log('run_app: App.run returned normally')
    except BaseException:
        text = _crash_text()
        _log_crash()
        boot_log('FATAL in run_app:\n' + text)
        _show_crash_screen(text)
        import time as _t
        while True:
            _t.sleep(1)
