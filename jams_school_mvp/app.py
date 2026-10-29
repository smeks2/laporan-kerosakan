import os, csv, sqlite3, uuid, secrets
from pathlib import Path
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE=Path(__file__).resolve().parent
DB=Path(os.getenv('JAMS_DB',str(BASE/'jams.db')))
UPLOAD=Path(os.getenv('JAMS_UPLOAD',str(BASE/'uploads')))
UPLOAD.mkdir(parents=True,exist_ok=True)
app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY',secrets.token_hex(32))
app.config['MAX_CONTENT_LENGTH']=12*1024*1024
STATUSES=['BARU','DALAM_PEMERIKSAAN','MENUNGGU_KELULUSAN','DILULUSKAN','DALAM_PEMBAIKAN','SIAP_UNTUK_SEMAKAN','DITUTUP','PERLU_MAKLUMAT','DITOLAK']
ROLES=['PELAPOR','PEMERIKSA','GURU_PEMBANGUNAN','PENTADBIR']

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c

def init_db():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, roles TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS location_types(id INTEGER PRIMARY KEY, zone TEXT NOT NULL, source_no INTEGER NOT NULL, name TEXT NOT NULL, quantity INTEGER NOT NULL, UNIQUE(zone,source_no));
  CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY, type_id INTEGER NOT NULL REFERENCES location_types(id), code TEXT NOT NULL UNIQUE, label TEXT NOT NULL, block TEXT DEFAULT '', floor TEXT DEFAULT '', verified INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS reports(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, reporter_id INTEGER NOT NULL REFERENCES users(id), location_id INTEGER REFERENCES locations(id), manual_location TEXT, asset TEXT, description TEXT NOT NULL, priority TEXT NOT NULL, status TEXT NOT NULL, assigned_to INTEGER REFERENCES users(id), inspection TEXT DEFAULT '', estimated_cost REAL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS photos(id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES reports(id), filename TEXT NOT NULL, uploader_id INTEGER NOT NULL REFERENCES users(id));
  CREATE TABLE IF NOT EXISTS history(id INTEGER PRIMARY KEY, report_id INTEGER NOT NULL REFERENCES reports(id), user_id INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL, note TEXT, at TEXT NOT NULL);
  CREATE INDEX IF NOT EXISTS idx_report_status ON reports(status); CREATE INDEX IF NOT EXISTS idx_report_assigned ON reports(assigned_to);''')
  with open(BASE/'data'/'locations.csv',encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    zone=r['zon'].strip(); no=int(r['bil_asal']); name=r['jenis_lokasi'].strip(); qty=int(r['kuantiti'])
    c.execute('INSERT INTO location_types(zone,source_no,name,quantity) VALUES(?,?,?,?) ON CONFLICT(zone,source_no) DO UPDATE SET name=excluded.name,quantity=excluded.quantity',(zone,no,name,qty))
    tid=c.execute('SELECT id FROM location_types WHERE zone=? AND source_no=?',(zone,no)).fetchone()['id']
    for i in range(1,qty+1):
     code=f'{zone[:3]}-{no:03d}-{i:03d}'
     c.execute('INSERT OR IGNORE INTO locations(type_id,code,label) VALUES(?,?,?)',(tid,code,f'{name} #{i} (belum disahkan)'))
  if not c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
   email=os.getenv('ADMIN_EMAIL','admin@localhost'); password=os.getenv('ADMIN_PASSWORD')
   if not password: password=secrets.token_urlsafe(12); print('\nINITIAL ADMIN PASSWORD:',password,'\n')
   c.execute('INSERT INTO users(name,email,password,roles) VALUES(?,?,?,?)',('Pentadbir Permulaan',email,generate_password_hash(password),'PELAPOR,PEMERIKSA,GURU_PEMBANGUNAN,PENTADBIR'))

def current_user():
 if 'uid' not in session:return None
 with db() as c:return c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()

def roles(user):return set(user['roles'].split(',')) if user else set()
def privileged(user):return bool(roles(user)&{'PENTADBIR','GURU_PEMBANGUNAN'})
def login_required(fn):
 @wraps(fn)
 def wrapped(*a,**kw):
  if not current_user():return redirect(url_for('login'))
  return fn(*a,**kw)
 return wrapped

def accessible(c,r,u):return privileged(u) or r['reporter_id']==u['id'] or (r['assigned_to']==u['id'] and 'PEMERIKSA' in roles(u))
@app.context_processor
def ctx():return dict(me=current_user(),roles=roles,STATUSES=STATUSES)
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  with db() as c:u=c.execute('SELECT * FROM users WHERE email=?',(request.form.get('email','').lower().strip(),)).fetchone()
  if u and check_password_hash(u['password'],request.form.get('password','')):session.clear();session['uid']=u['id'];return redirect(url_for('index'))
  flash('E-mel atau kata laluan tidak tepat.','error')
 return render_template('login.html')
@app.route('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.route('/')
@login_required
def index():
 u=current_user()
 with db() as c:
  where='1=1' if privileged(u) else '(r.reporter_id=? OR r.assigned_to=?)'
  params=[] if privileged(u) else [u['id'],u['id']]
  reports=c.execute(f'''SELECT r.*,l.label location_label,t.zone,us.name reporter_name,ass.name assignee_name FROM reports r LEFT JOIN locations l ON r.location_id=l.id LEFT JOIN location_types t ON l.type_id=t.id LEFT JOIN users us ON r.reporter_id=us.id LEFT JOIN users ass ON r.assigned_to=ass.id WHERE {where} ORDER BY r.id DESC''',params).fetchall()
 counts={s:sum(r['status']==s for r in reports) for s in STATUSES}
 return render_template('index.html',reports=reports,counts=counts)
@app.route('/report/new',methods=['GET','POST'])
@login_required
def new_report():
 u=current_user()
 with db() as c:
  locations=c.execute('SELECT l.*,t.zone,t.name type_name FROM locations l JOIN location_types t ON l.type_id=t.id ORDER BY t.zone,t.source_no,l.id').fetchall()
  if request.method=='POST':
   desc=request.form.get('description','').strip(); manual=request.form.get('manual_location','').strip(); loc=request.form.get('location_id')
   if not desc or (not loc and not manual):flash('Nyatakan lokasi dan kerosakan.','error');return render_template('new.html',locations=locations)
   if loc and not c.execute('SELECT 1 FROM locations WHERE id=?',(loc,)).fetchone():abort(400)
   now=datetime.now().isoformat(timespec='seconds');ref='JAMS-'+datetime.now().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:6].upper()
   cur=c.execute('INSERT INTO reports(ref,reporter_id,location_id,manual_location,asset,description,priority,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(ref,u['id'],int(loc) if loc else None,manual,request.form.get('asset','').strip(),desc,request.form.get('priority','SEDERHANA'),'BARU',now,now));rid=cur.lastrowid
   for photo in request.files.getlist('photos')[:5]:
    if not photo or not photo.filename:continue
    ext=Path(secure_filename(photo.filename)).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}:continue
    # Validate file signature, not extension alone
    head=photo.stream.read(16);photo.stream.seek(0)
    valid=(head.startswith(b'\xff\xd8\xff') if ext in {'.jpg','.jpeg'} else head.startswith(b'\x89PNG\r\n\x1a\n') if ext=='.png' else head.startswith(b'RIFF') and head[8:12]==b'WEBP')
    if not valid:continue
    name=uuid.uuid4().hex+ext;photo.save(UPLOAD/name)
    c.execute('INSERT INTO photos(report_id,filename,uploader_id) VALUES(?,?,?)',(rid,name,u['id']))
   c.execute('INSERT INTO history(report_id,user_id,action,note,at) VALUES(?,?,?,?,?)',(rid,u['id'],'LAPORAN_BARU','',now))
   flash('Laporan berjaya direkodkan.');return redirect(url_for('detail',rid=rid))
 return render_template('new.html',locations=locations)
@app.route('/report/<int:rid>')
@login_required
def detail(rid):
 u=current_user()
 with db() as c:
  r=c.execute('''SELECT r.*,l.label location_label,us.name reporter_name FROM reports r LEFT JOIN locations l ON l.id=r.location_id JOIN users us ON us.id=r.reporter_id WHERE r.id=?''',(rid,)).fetchone()
  if not r:abort(404)
  if not accessible(c,r,u):abort(403)
  photos=c.execute('SELECT * FROM photos WHERE report_id=?',(rid,)).fetchall()
  history=c.execute('SELECT h.*,u.name actor FROM history h JOIN users u ON u.id=h.user_id WHERE report_id=? ORDER BY h.id DESC',(rid,)).fetchall()
  inspectors=c.execute("SELECT id,name,roles FROM users ORDER BY name").fetchall()
 return render_template('detail.html',r=r,photos=photos,history=history,inspectors=[x for x in inspectors if 'PEMERIKSA' in roles(x)])
@app.route('/report/<int:rid>/update',methods=['POST'])
@login_required
def update(rid):
 u=current_user()
 with db() as c:
  r=c.execute('SELECT * FROM reports WHERE id=?',(rid,)).fetchone()
  if not r:abort(404)
  if not accessible(c,r,u):abort(403)
  newstatus=request.form.get('status',r['status']);note=request.form.get('note','').strip()[:3000]
  if newstatus not in STATUSES:abort(400)
  if not privileged(u) and not (r['assigned_to']==u['id'] and 'PEMERIKSA' in roles(u) and newstatus in {'DALAM_PEMERIKSAAN','MENUNGGU_KELULUSAN','PERLU_MAKLUMAT'}):abort(403)
  assigned=request.form.get('assigned_to') if privileged(u) else None
  assignee=r['assigned_to']
  if assigned is not None:
   if assigned:
    candidate=c.execute('SELECT * FROM users WHERE id=?',(assigned,)).fetchone()
    if not candidate or 'PEMERIKSA' not in roles(candidate):abort(400)
    assignee=candidate['id']
   else:assignee=None
  cost=request.form.get('estimated_cost',r['estimated_cost']);cost=float(cost or 0)
  now=datetime.now().isoformat(timespec='seconds')
  c.execute('UPDATE reports SET status=?,assigned_to=?,inspection=?,estimated_cost=?,updated_at=? WHERE id=?',(newstatus,assignee,note or r['inspection'],cost,now,rid))
  c.execute('INSERT INTO history(report_id,user_id,action,note,at) VALUES(?,?,?,?,?)',(rid,u['id'],'STATUS: '+newstatus,note,now))
 flash('Rekod tindakan dikemas kini.');return redirect(url_for('detail',rid=rid))
@app.route('/photo/<int:pid>')
@login_required
def photo(pid):
 u=current_user()
 with db() as c:
  p=c.execute('SELECT p.*,r.reporter_id,r.assigned_to FROM photos p JOIN reports r ON p.report_id=r.id WHERE p.id=?',(pid,)).fetchone()
  if not p:abort(404)
  if not accessible(c,p,u):abort(403)
 return send_from_directory(UPLOAD,p['filename'])
@app.route('/locations')
@login_required
def locations():
 with db() as c:items=c.execute('SELECT l.*,t.zone,t.name type_name FROM locations l JOIN location_types t ON l.type_id=t.id ORDER BY t.zone,t.source_no,l.id').fetchall()
 return render_template('locations.html',items=items)
@app.route('/locations/<int:lid>/edit',methods=['POST'])
@login_required
def edit_location(lid):
 if not privileged(current_user()):abort(403)
 with db() as c:c.execute('UPDATE locations SET label=?,block=?,floor=?,verified=1 WHERE id=?',(request.form.get('label','').strip(),request.form.get('block','').strip(),request.form.get('floor','').strip(),lid))
 flash('Lokasi disahkan.');return redirect(url_for('locations'))
@app.route('/users',methods=['GET','POST'])
@login_required
def users():
 if 'PENTADBIR' not in roles(current_user()):abort(403)
 with db() as c:
  if request.method=='POST':
   name=request.form.get('name','').strip();email=request.form.get('email','').lower().strip();password=request.form.get('password','');selected=[r for r in ROLES if r in request.form.getlist('roles')]
   if not name or '@' not in email or len(password)<10 or not selected:flash('Isi maklumat, kata laluan sekurang-kurangnya 10 aksara dan peranan.','error')
   else:
    try:c.execute('INSERT INTO users(name,email,password,roles) VALUES(?,?,?,?)',(name,email,generate_password_hash(password),','.join(selected)));flash('Pengguna ditambah.')
    except sqlite3.IntegrityError:flash('E-mel sudah wujud.','error')
  items=c.execute('SELECT id,name,email,roles FROM users ORDER BY id').fetchall()
 return render_template('users.html',items=items,ROLES=ROLES)
@app.route('/health')
def health():return {'status':'ok'}
init_db()
if __name__=='__main__':app.run(host='127.0.0.1',port=int(os.getenv('PORT','5000')),debug=False)
