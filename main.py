import os, json, threading, hashlib, secrets, socket, urllib.request, urllib.parse, time, html, webbrowser
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
from kivy.graphics import Color, RoundedRectangle

BASE = Path(__file__).resolve().parent
DATA = Path(App.user_data_dir) / 'data'
AUDIO = DATA / 'noheh'
REPORTS = DATA / 'reports'
for p in (DATA, AUDIO, REPORTS): p.mkdir(parents=True, exist_ok=True)
DB = DATA / 'db.json'
FONT = str((BASE / 'assets' / 'NotoNaskhArabic-Regular.ttf') if (BASE / 'assets' / 'NotoNaskhArabic-Regular.ttf').exists() else (BASE / 'NotoNaskhArabic-Regular.ttf'))
FONT_B = str((BASE / 'assets' / 'NotoNaskhArabic-Bold.ttf') if (BASE / 'assets' / 'NotoNaskhArabic-Bold.ttf').exists() else (BASE / 'NotoNaskhArabic-Bold.ttf'))
LabelBase.register(name='NotoFA', fn_regular=FONT, fn_bold=FONT_B)


def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def hashpw(p, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt, hashlib.pbkdf2_hmac('sha256', p.encode(), salt.encode(), 120000).hex()
def verify(p, salt, digest): return hashpw(p, salt)[1] == digest

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

DBDATA = load_db(); save_db(DBDATA)
SERVER = None
SESSIONS = {}

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self, obj, code=200):
        b=json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def read_json(self):
        n=int(self.headers.get('Content-Length','0'))
        if n > 1_000_000: raise ValueError('request too large')
        return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}
    def session_user(self):
        token=self.headers.get('Authorization','').removeprefix('Bearer ').strip()
        return SESSIONS.get(token)
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
        if self.path=='/api/info': return self.send_json({'ok':True,'name':'سامانه آماد و پشتیبانی','version':'5.0'})
        if self.path.startswith('/audio/'):
            name=urllib.parse.unquote(self.path.split('/audio/',1)[1]); f=AUDIO / os.path.basename(name)
            if not f.exists(): return self.send_json({'ok':False,'error':'not found'},404)
            self.send_response(200); self.send_header('Content-Type','audio/mpeg'); self.send_header('Content-Length',str(f.stat().st_size)); self.end_headers();
            with open(f,'rb') as h:
                while True:
                    c=h.read(65536)
                    if not c: break
                    self.wfile.write(c)
            return
        self.send_json({'ok':False,'error':'not found'},404)
    def do_POST(self):
        global DBDATA
        try: data=self.read_json()
        except Exception: return self.send_json({'ok':False,'error':'bad json'},400)
        if self.path=='/api/login':
            u=data.get('username',''); p=data.get('password',''); user=next((x for x in DBDATA['users'] if x['username']==u and x.get('active',True)),None)
            if not user or not verify(p,user['salt'],user['password']): return self.send_json({'ok':False,'error':'نام کاربری یا رمز عبور نادرست است'},401)
            track=None
            if DBDATA['chants']:
                track=DBDATA['chants'][DBDATA['chant_index'] % len(DBDATA['chants'])]; DBDATA['chant_index']=(DBDATA['chant_index']+1)%len(DBDATA['chants']); save_db(DBDATA)
            token=secrets.token_urlsafe(32)
            SESSIONS[token]={'username':user['username'],'name':user['name'],'role':user['role']}
            return self.send_json({'ok':True,'name':user['name'],'role':user['role'],'token':token,'chant':track,'time':now()})
        if self.path=='/api/add_log':
            if not self.require_user(): return
            typ=data.get('type'); entry=data.get('entry',{}); entry['timestamp']=now();
            if typ not in ('repairs','equipment'): return self.send_json({'ok':False},400)
            DBDATA[typ].append(entry); save_db(DBDATA); return self.send_json({'ok':True})
        if self.path=='/api/users':
            if not self.require_user(admin=True): return
            if data.get('action')=='list': return self.send_json({'ok':True,'users':[{k:v for k,v in u.items() if k not in ('salt','password')} for u in DBDATA['users']]})
            if data.get('action') in ('add','reset'):
                username=data.get('username','').strip(); password=data.get('password','')
                if data['action']=='add' and any(u['username']==username for u in DBDATA['users']): return self.send_json({'ok':False,'error':'نام کاربری تکراری'},400)
                salt,digest=hashpw(password)
                if data['action']=='reset':
                    u=next((x for x in DBDATA['users'] if x['username']==username),None)
                    if not u: return self.send_json({'ok':False,'error':'کاربر یافت نشد'},404)
                    u.update(salt=salt,password=digest)
                else: DBDATA['users'].append({'username':username,'name':data.get('name',username),'role':data.get('role','user'),'salt':salt,'password':digest,'active':True})
                save_db(DBDATA); return self.send_json({'ok':True})
        if self.path=='/api/chants':
            if not self.require_user(admin=True): return
            if data.get('action')=='list': return self.send_json({'ok':True,'chants':DBDATA['chants']})
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
        root.add_widget(lbl('سامانه آماد و پشتیبانی',30,True))
        root.add_widget(lbl('پایگاه شهید صیاد شیرازی',21))
        root.add_widget(lbl('بسم الله الرحمن الرحیم\nبسیج لشکر مخلص خداست (امام خمینی ره)\nبسیجی یعنی علی که تمام وجودش وقف اسلام بود (امام شهید ره)',18))
        self.user=TextInput(hint_text=fa('متن خود را بنویسید: نام کاربری لاتین'),multiline=False)
        self.pw=TextInput(hint_text=fa('متن خود را بنویسید: رمز عبور'),password=True,multiline=False)
        self.url=TextInput(text='http://127.0.0.1:8765',hint_text=fa('متن خود را بنویسید: آدرس سرور'),multiline=False)
        root.add_widget(self.user); root.add_widget(self.pw); root.add_widget(self.url)
        root.add_widget(btn('ورود به سرور',self.login))
        root.add_widget(btn('اجرای این گوشی به عنوان سرور',self.server_mode))
        self.add_widget(root)
    def login(self,*a):
        try:
            data=json.dumps({'username':self.user.text.strip(),'password':self.pw.text}).encode(); req=urllib.request.Request(self.url.text.rstrip('/')+'/api/login',data=data,headers={'Content-Type':'application/json'}); r=json.loads(urllib.request.urlopen(req,timeout=5).read().decode())
            if not r.get('ok'): raise Exception(r.get('error','خطا'))
            App.get_running_app().state.update(user=r,server_url=self.url.text.rstrip('/')); self.manager.current='home'
            if r.get('chant'): App.get_running_app().play_chant(r['chant'])
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),16),size_hint=(.9,.35)).open()
    def server_mode(self,*a):
        if SERVER is None: ServerThread().start()
        token=secrets.token_urlsafe(32); SESSIONS[token]={'username':'admin','name':'مدیر سامانه','role':'admin'}
        App.get_running_app().state.update(user={'name':'مدیر سامانه','role':'admin','token':token},server_url='http://127.0.0.1:8765'); self.manager.current='home'

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
        items=[('تعمیرات','repairs'),('تحویل و عودت تجهیزات','equipment'),('گزارشات','reports')]
        if user.get('role')=='admin': items += [('مدیریت کاربران','users'),('مدیریت نوحه (فقط مدیر)','chants'),('تنظیمات سرور','server')]
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
        try: self.clock.cancel()
        except: pass
        self.manager.current='login'

class SimpleLog(Screen):
    typ='repairs'; title=''
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl(self.title,24,True)); self.person=TextInput(hint_text=fa('متن خود را بنویسید: نام / واحد'),multiline=False); self.desc=TextInput(hint_text=fa('متن خود را بنویسید: شرح'),multiline=False); root.add_widget(self.person); root.add_widget(self.desc); root.add_widget(btn('ثبت رویداد همراه با تاریخ و ساعت دقیق',self.save)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
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
        self.first=TextInput(hint_text=fa('متن خود را بنویسید: نام'),multiline=False,size_hint_y=None,height=dp(46))
        self.last=TextInput(hint_text=fa('متن خود را بنویسید: نام خانوادگی'),multiline=False,size_hint_y=None,height=dp(46))
        self.father=TextInput(hint_text=fa('متن خود را بنویسید: نام پدر'),multiline=False,size_hint_y=None,height=dp(46))
        self.national=TextInput(hint_text=fa('متن خود را بنویسید: کد ملی'),multiline=False,size_hint_y=None,height=dp(46))
        self.phone=TextInput(hint_text=fa('متن خود را بنویسید: شماره تلفن'),multiline=False,size_hint_y=None,height=dp(46))
        self.equipment=TextInput(hint_text=fa('متن خود را بنویسید: مشخصات تجهیزات تحویلی، تعداد و کد'),multiline=True,size_hint_y=None,height=dp(90))
        self.signature=TextInput(hint_text=fa('متن خود را بنویسید: نام/توضیح امضای دریافت‌کننده (اختیاری)'),multiline=False,size_hint_y=None,height=dp(46))
        for field in (self.first,self.last,self.father,self.national,self.phone,self.equipment,self.signature):
            form.add_widget(field)
        form.add_widget(btn('الحاق عکس مأمور',self.pick_photo,46))
        self.photo_label=lbl('عکسی انتخاب نشده است',14)
        form.add_widget(self.photo_label)
        scroll.add_widget(form); root.add_widget(scroll)
        root.add_widget(btn('ثبت اطلاعات و آماده‌سازی کارت چاپ',self.save_handover,52))
        root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'),44))
        self.add_widget(root)
        self.photo_path=''

    def pick_photo(self,*a):
        start='/storage/emulated/0/Download' if os.path.isdir('/storage/emulated/0/Download') else str(Path.home())
        fc=FileChooserListView(path=start,filters=['*.png','*.jpg','*.jpeg','*.webp'])
        box=BoxLayout(orientation='vertical',spacing=dp(6))
        box.add_widget(fc)
        pop=Popup(title=fa('انتخاب عکس مأمور'),content=box,size_hint=(.95,.9))
        box.add_widget(btn('انتخاب عکس',lambda b:self._copy_photo(fc.selection,pop),44))
        self.photo_popup=pop; pop.open()

    def _copy_photo(self,selection,popup):
        if not selection:
            Popup(title=fa('توجه'),content=lbl('ابتدا یک عکس انتخاب کنید',15),size_hint=(.8,.3)).open()
            return
        src=Path(selection[0])
        safe_name='officer_'+str(int(time.time()))+src.suffix.lower()
        dst=REPORTS/safe_name
        try:
            dst.write_bytes(src.read_bytes())
            self.photo_path=str(dst)
            self.photo_label.text=fa('عکس پیوست شد: '+src.name)
            popup.dismiss()
        except Exception as e:
            Popup(title=fa('خطا'),content=lbl(str(e),14),size_hint=(.9,.3)).open()

    def save_handover(self,*a):
        first=self.first.text.strip(); last=self.last.text.strip()
        equipment=self.equipment.text.strip()
        if not first or not last or not equipment:
            Popup(title=fa('اطلاعات ناقص'),content=lbl('نام، نام خانوادگی و مشخصات تجهیزات را وارد کنید',15),size_hint=(.9,.3)).open()
            return
        entry={
            'first_name':first,'last_name':last,'father_name':self.father.text.strip(),
            'national_id':self.national.text.strip(),'phone':self.phone.text.strip(),
            'equipment_details':equipment,'signature':self.signature.text.strip(),
            'photo_path':self.photo_path,'timestamp':now(),'record_type':'تحویل تجهیزات'
        }
        try:
            data={'type':'equipment','entry':entry}
            req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/add_log',
                data=json.dumps(data,ensure_ascii=False).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+App.get_running_app().state.get('user',{}).get('token','')})
            urllib.request.urlopen(req,timeout=5).read()
            # Keep a local copy as well so the card can be prepared on this device.
            if App.get_running_app().state.get('server_url') not in ('http://127.0.0.1:8765','http://localhost:8765'):
                DBDATA.setdefault('equipment',[]).append(entry); save_db(DBDATA)
            card_path=make_handover_card(entry)
            notice=BoxLayout(orientation='vertical',padding=dp(10),spacing=dp(8))
            notice.add_widget(lbl('اطلاعات ثبت شد. کارت برای چاپ آماده است. برای ارسال مشخصات به پیام‌رسان‌های نصب‌شده، اشتراک‌گذاری را انتخاب کنید.',14))
            notice.add_widget(btn('اشتراک‌گذاری در ایتا، روبیکا، سروش یا بله',lambda b:share_handover_entry(entry),48))
            notice.add_widget(btn('بستن',lambda b:result_popup.dismiss(),42))
            result_popup=Popup(title=fa('ثبت و آماده‌سازی کارت'),content=notice,size_hint=(.95,.48))
            result_popup.open()
            for field in (self.first,self.last,self.father,self.national,self.phone,self.equipment,self.signature):
                field.text=''
            self.photo_path=''; self.photo_label.text=fa('عکسی انتخاب نشده است')
        except Exception as e:
            Popup(title=fa('خطا در ثبت'),content=lbl(str(e),14),size_hint=(.9,.35)).open()

class Users(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('مدیریت کاربران',24,True)); self.u=TextInput(hint_text=fa('متن خود را بنویسید: نام کاربری لاتین'),multiline=False); self.n=TextInput(hint_text=fa('متن خود را بنویسید: نام کاربر'),multiline=False); self.p=TextInput(hint_text=fa('متن خود را بنویسید: رمز عبور جدید'),password=True,multiline=False); root.add_widget(self.u); root.add_widget(self.n); root.add_widget(self.p); root.add_widget(btn('ایجاد کاربر',self.add)); root.add_widget(btn('بازنشانی رمز کاربر',self.reset)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def call(self,action):
        data={'action':action,'username':self.u.text,'name':self.n.text,'password':self.p.text}; req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/users',data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+App.get_running_app().state.get('user',{}).get('token','')}); return json.loads(urllib.request.urlopen(req,timeout=5).read().decode())
    def add(self,*a):
        try: r=self.call('add'); Popup(title=fa('نتیجه'),content=lbl('کاربر ایجاد شد' if r.get('ok') else r.get('error'),16),size_hint=(.8,.3)).open()
        except Exception as e: Popup(title='Error',content=lbl(e,16)).open()
    def reset(self,*a):
        try: r=self.call('reset'); Popup(title=fa('نتیجه'),content=lbl('رمز بازنشانی شد' if r.get('ok') else r.get('error'),16),size_hint=(.8,.3)).open()
        except Exception as e: Popup(title='Error',content=lbl(e,16)).open()

class Chants(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('مدیریت نوحه — فقط مدیر سامانه',22,True)); root.add_widget(btn('افزودن فایل نوحه',self.pick)); root.add_widget(lbl('نوحه‌ها در پوشه خصوصی سامانه ذخیره و ترتیب پخش ورودها مدیریت می‌شود.',15)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def pick(self,*a):
        fc=FileChooserListView(path='/storage/emulated/0/Download',filters=['*.mp3','*.wav','*.m4a']); box=BoxLayout(orientation='vertical'); box.add_widget(fc); box.add_widget(btn('انتخاب',lambda b:self.copy(fc.selection),48)); p=Popup(title=fa('انتخاب نوحه'),content=box,size_hint=(.95,.9)); self.pop=p; p.open()
    def copy(self,sel):
        if not sel: return
        src=Path(sel[0]); dst=AUDIO/src.name; dst.write_bytes(src.read_bytes()); DBDATA['chants'].append(src.name); save_db(DBDATA); self.pop.dismiss(); Popup(title=fa('ثبت شد'),content=lbl(src.name,16),size_hint=(.8,.3)).open()

class Reports(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('گزارشات',24,True)); root.add_widget(btn('خروجی Word',lambda b:self.export('docx'))); root.add_widget(btn('خروجی PDF',lambda b:self.export('pdf'))); root.add_widget(btn('ساخت کارت چاپ برای آخرین تحویل',self.export_latest_card)); root.add_widget(btn('اشتراک‌گذاری آخرین کارت در پیام‌رسان‌ها',self.share_latest_card)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def export_latest_card(self,*a):
        records=DBDATA.get('equipment',[])
        if not records:
            Popup(title=fa('گزارشات'),content=lbl('هنوز اطلاعات تحویل تجهیزات ثبت نشده است',15),size_hint=(.85,.3)).open(); return
        path=make_handover_card(records[-1])
        try: webbrowser.open(Path(path).resolve().as_uri())
        except Exception: pass
        Popup(title=fa('کارت آماده چاپ'),content=lbl('کارت HTML در این مسیر ذخیره شد:\n'+str(path)+'\nآن را در مرورگر باز و چاپ کنید.',14),size_hint=(.95,.45)).open()

    def share_latest_card(self,*a):
        records=DBDATA.get('equipment',[])
        if not records:
            Popup(title=fa('گزارشات'),content=lbl('هنوز اطلاعات تحویل تجهیزات ثبت نشده است',15),size_hint=(.85,.3)).open(); return
        share_handover_entry(records[-1])

    def export(self,kind):
        text='گزارش سامانه آماد و پشتیبانی\nتاریخ تولید: '+now()+'\n\nتعمیرات:\n'+json.dumps(DBDATA.get('repairs',[]),ensure_ascii=False,indent=2)+'\n\nتحویل و عودت تجهیزات:\n'+json.dumps(DBDATA.get('equipment',[]),ensure_ascii=False,indent=2)
        if kind=='docx': path=REPORTS/'report.docx'; make_docx(path,text)
        else: path=REPORTS/'report.pdf'; make_pdf(path,text)
        Popup(title=fa('گزارش آماده شد'),content=lbl(str(path),14),size_hint=(.95,.4)).open()

class ServerScreen(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(8)); root.add_widget(lbl('سرور این گوشی',24,True)); root.add_widget(lbl('پورت: 8765',18)); root.add_widget(lbl('\n'.join('آدرس: http://'+ip+':8765' for ip in local_ips()),18)); root.add_widget(lbl('سه گوشی دیگر می‌توانند با همین آدرس و روی یک شبکه به سرور وصل شوند.',16)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)

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
        'امضای دریافت‌کننده: '+str(entry.get('signature','')),
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
        Popup(title=fa('اشتراک‌گذاری'),content=lbl('اشتراک‌گذاری مستقیم فقط در نسخه اندروید قابل اجراست.\n'+str(e),14),size_hint=(.92,.4)).open()
        return False

def make_handover_card(entry):
    """Create a printer-friendly ID-card-sized HTML file for an equipment handover."""
    photo=entry.get('photo_path','')
    photo_html=''
    if photo and Path(photo).exists():
        photo_uri=Path(photo).resolve().as_uri()
        photo_html=f'<img class="photo" src="{html.escape(photo_uri, quote=True)}" alt="عکس مأمور">'
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
<div class="sign">امضای دریافت‌کننده: {value('signature')}　　امضای تحویل‌دهنده: __________________</div>
</section><script>window.onload=()=>{{if(new URLSearchParams(location.search).has('print')) window.print();}}</script></body></html>'''
    target=REPORTS/('handover_card_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.html')
    target.write_text(card,encoding='utf-8')
    return target

def make_docx(path,text):
    import zipfile, html
    body=''.join(f'<w:p><w:r><w:t>{html.escape(line)}</w:t></w:r></w:p>' for line in text.splitlines())
    files={'[Content_Types].xml':'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>','_rels/.rels':'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>','word/document.xml':f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr/></w:body></w:document>'}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,c in files.items(): z.writestr(n,c)

def make_pdf(path,text):
    # Minimal valid PDF with Helvetica; Persian is stored as UTF-8 bytes and may not render in all viewers.
    lines=text.replace('\r','').splitlines()
    def pdf_escape(line):
        encoded=line.encode('latin-1','replace').decode('latin-1')
        return encoded.replace('\\\\','\\\\\\\\').replace('(','\\\\(').replace(')','\\\\)')
    content='BT /F1 10 Tf 40 800 Td '+''.join('('+pdf_escape(line)+') Tj 0 -14 Td ' for line in lines)+'ET'
    objs=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',f'<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out=b'%PDF-1.4\n'; offs=[]
    for i,o in enumerate(objs,1): offs.append(len(out)); out+=f'{i} 0 obj\n{o}\nendobj\n'.encode()
    x=len(out); out+=f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode()+b''.join(f'{q:010d} 00000 n \n'.encode() for q in offs)+f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF'.encode(); path.write_bytes(out)

class AmadApp(App):
    def build(self):
        self.state={}; sm=ScreenManager(); sm.add_widget(Login(name='login')); sm.add_widget(Home(name='home')); sm.add_widget(SimpleLog(name='repairs')); sm.get_screen('repairs').typ='repairs'; sm.get_screen('repairs').title='تعمیرات'; sm.add_widget(EquipmentScreen(name='equipment')); sm.add_widget(Reports(name='reports')); sm.add_widget(Users(name='users')); sm.add_widget(Chants(name='chants')); sm.add_widget(ServerScreen(name='server')); return sm
    def play_chant(self, name):
        url=self.state['server_url']+'/audio/'+urllib.parse.quote(name); local=AUDIO/name
        try:
            if not local.exists(): urllib.request.urlretrieve(url,local)
            s=SoundLoader.load(str(local));
            if s: s.play()
        except Exception: pass

if __name__=='__main__': AmadApp().run()
