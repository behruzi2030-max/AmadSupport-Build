import os, json, threading, hashlib, secrets, socket, urllib.request, urllib.parse, time
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

class APIHandler(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def send_json(self, obj, code=200):
        b=json.dumps(obj, ensure_ascii=False).encode(); self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def read_json(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n).decode('utf-8')) if n else {}
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
            return self.send_json({'ok':True,'name':user['name'],'role':user['role'],'chant':track,'time':now()})
        if self.path=='/api/add_log':
            typ=data.get('type'); entry=data.get('entry',{}); entry['timestamp']=now();
            if typ not in ('repairs','equipment'): return self.send_json({'ok':False},400)
            DBDATA[typ].append(entry); save_db(DBDATA); return self.send_json({'ok':True})
        if self.path=='/api/users':
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
        self.user=TextInput(hint_text=fa('نام کاربری لاتین'),multiline=False)
        self.pw=TextInput(hint_text=fa('رمز عبور'),password=True,multiline=False)
        self.url=TextInput(text='http://127.0.0.1:8765',hint_text='آدرس سرور',multiline=False)
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
        App.get_running_app().state.update(user={'name':'مدیر سامانه','role':'admin'},server_url='http://127.0.0.1:8765'); self.manager.current='home'

class Home(Screen):
    def on_enter(self):
        self.clear_widgets()
        root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8))
        root.add_widget(lbl('سامانه آماد و پشتیبانی',28,True))
        root.add_widget(lbl(datetime.now().strftime('%Y/%m/%d   %H:%M:%S'),20,True))
        self.clock=Clock.schedule_interval(self.tick,1)
        grid=GridLayout(cols=2,spacing=dp(8),size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        for t,screen in [('تعمیرات','repairs'),('تحویل و عودت تجهیزات','equipment'),('گزارشات','reports'),('مدیریت کاربران','users'),('مدیریت نوحه (فقط مدیر)','chants'),('تنظیمات سرور','server')]:
            grid.add_widget(btn(t,lambda b,s=screen:self.go(s),60))
        root.add_widget(grid)
        root.add_widget(btn('خروج',lambda b:self.logout(),48))
        self.add_widget(root)
    def tick(self,*a):
        for w in self.children:
            if isinstance(w,BoxLayout):
                for x in w.children:
                    if isinstance(x,Label) and ':' in x.text and '/' in x.text: x.text=datetime.now().strftime('%Y/%m/%d   %H:%M:%S')
    def go(self,s): self.manager.current=s
    def logout(self):
        try: self.clock.cancel()
        except: pass
        self.manager.current='login'

class SimpleLog(Screen):
    typ='repairs'; title=''
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl(self.title,24,True)); self.person=TextInput(hint_text=fa('نام / واحد'),multiline=False); self.desc=TextInput(hint_text=fa('شرح'),multiline=False); root.add_widget(self.person); root.add_widget(self.desc); root.add_widget(btn('ثبت رویداد همراه با تاریخ و ساعت دقیق',self.save)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def save(self,*a):
        try:
            data={'type':self.typ,'entry':{'person':self.person.text,'description':self.desc.text}}; req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/add_log',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}); urllib.request.urlopen(req,timeout=5); Popup(title=fa('ثبت شد'),content=lbl(now(),18),size_hint=(.8,.3)).open(); self.person.text=''; self.desc.text=''
        except Exception as e: Popup(title=fa('خطا'),content=lbl(str(e),16),size_hint=(.9,.3)).open()

class Users(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('مدیریت کاربران',24,True)); self.u=TextInput(hint_text='نام کاربری لاتین',multiline=False); self.n=TextInput(hint_text=fa('نام کاربر'),multiline=False); self.p=TextInput(hint_text=fa('رمز عبور جدید'),password=True,multiline=False); root.add_widget(self.u); root.add_widget(self.n); root.add_widget(self.p); root.add_widget(btn('ایجاد کاربر',self.add)); root.add_widget(btn('بازنشانی رمز کاربر',self.reset)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def call(self,action):
        data={'action':action,'username':self.u.text,'name':self.n.text,'password':self.p.text}; req=urllib.request.Request(App.get_running_app().state['server_url']+'/api/users',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}); return json.loads(urllib.request.urlopen(req,timeout=5).read().decode())
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
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(12),spacing=dp(8)); root.add_widget(lbl('گزارشات',24,True)); root.add_widget(btn('خروجی Word',lambda b:self.export('docx'))); root.add_widget(btn('خروجی PDF',lambda b:self.export('pdf'))); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)
    def export(self,kind):
        text='گزارش سامانه آماد و پشتیبانی\nتاریخ تولید: '+now()+'\n\nتعمیرات:\n'+json.dumps(DBDATA.get('repairs',[]),ensure_ascii=False,indent=2)+'\n\nتحویل و عودت تجهیزات:\n'+json.dumps(DBDATA.get('equipment',[]),ensure_ascii=False,indent=2)
        if kind=='docx': path=REPORTS/'report.docx'; make_docx(path,text)
        else: path=REPORTS/'report.pdf'; make_pdf(path,text)
        Popup(title=fa('گزارش آماده شد'),content=lbl(str(path),14),size_hint=(.95,.4)).open()

class ServerScreen(Screen):
    def on_enter(self): self.clear_widgets(); root=BoxLayout(orientation='vertical',padding=dp(14),spacing=dp(8)); root.add_widget(lbl('سرور این گوشی',24,True)); root.add_widget(lbl('پورت: 8765',18)); root.add_widget(lbl('\n'.join('آدرس: http://'+ip+':8765' for ip in local_ips()),18)); root.add_widget(lbl('سه گوشی دیگر می‌توانند با همین آدرس و روی یک شبکه به سرور وصل شوند.',16)); root.add_widget(btn('بازگشت',lambda b:setattr(self.manager,'current','home'))); self.add_widget(root)

def make_docx(path,text):
    import zipfile, html
    body=''.join(f'<w:p><w:r><w:t>{html.escape(line)}</w:t></w:r></w:p>' for line in text.splitlines())
    files={'[Content_Types].xml':'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>','_rels/.rels':'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>','word/document.xml':f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{body}<w:sectPr/></w:body></w:document>'}
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for n,c in files.items(): z.writestr(n,c)

def make_pdf(path,text):
    # Minimal valid PDF with Helvetica; Persian is stored as UTF-8 bytes and may not render in all viewers.
    lines=text.replace('\r','').splitlines(); content='BT /F1 10 Tf 40 800 Td '+''.join(f'({line.encode("latin-1","replace").decode("latin-1").replace("(","\\(").replace(")","\\)")}) Tj 0 -14 Td ' for line in lines)+'ET'
    objs=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',f'<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out=b'%PDF-1.4\n'; offs=[]
    for i,o in enumerate(objs,1): offs.append(len(out)); out+=f'{i} 0 obj\n{o}\nendobj\n'.encode()
    x=len(out); out+=f'xref\n0 {len(objs)+1}\n0000000000 65535 f \n'.encode()+b''.join(f'{q:010d} 00000 n \n'.encode() for q in offs)+f'trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF'.encode(); path.write_bytes(out)

class AmadApp(App):
    def build(self):
        self.state={}; sm=ScreenManager(); sm.add_widget(Login(name='login')); sm.add_widget(Home(name='home')); sm.add_widget(SimpleLog(name='repairs')); sm.get_screen('repairs').typ='repairs'; sm.get_screen('repairs').title='تعمیرات'; sm.add_widget(SimpleLog(name='equipment')); sm.get_screen('equipment').typ='equipment'; sm.get_screen('equipment').title='تحویل و عودت تجهیزات'; sm.add_widget(Reports(name='reports')); sm.add_widget(Users(name='users')); sm.add_widget(Chants(name='chants')); sm.add_widget(ServerScreen(name='server')); return sm
    def play_chant(self, name):
        url=self.state['server_url']+'/audio/'+urllib.parse.quote(name); local=AUDIO/name
        try:
            if not local.exists(): urllib.request.urlretrieve(url,local)
            s=SoundLoader.load(str(local));
            if s: s.play()
        except Exception: pass

if __name__=='__main__': AmadApp().run()
