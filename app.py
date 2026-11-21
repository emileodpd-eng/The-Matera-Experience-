import os, re, secrets
from datetime import datetime, timedelta, timezone, date
from functools import wraps
from flask import Flask, jsonify, request, render_template, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, func, text
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY','dev-only-change-before-deploy'), SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL','sqlite:///matera_booking.db').replace('postgres://','postgresql://',1), SQLALCHEMY_TRACK_MODIFICATIONS=False, MAX_CONTENT_LENGTH=16384, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1')
if os.getenv('DEPLOY_ENV')=='production':
 if os.getenv('SECRET_KEY','') in ('','dev-only-change-before-deploy'):
  raise RuntimeError('SECRET_KEY sicura obbligatoria in produzione')
 if not os.getenv('DATABASE_URL','').startswith(('postgresql://','postgres://')):
  raise RuntimeError('PostgreSQL obbligatorio in produzione')
db=SQLAlchemy(app)
UTC=timezone.utc

def now(): return datetime.now(UTC)
def fail(msg,code=400): return jsonify(error=msg),code

class Operator(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 name=db.Column(db.String(120),nullable=False)
 email=db.Column(db.String(180),unique=True,nullable=False)
 password_hash=db.Column(db.String(255),nullable=False)
 active=db.Column(db.Boolean,default=True,nullable=False)
class Experience(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 operator_id=db.Column(db.Integer,db.ForeignKey('operator.id'),nullable=False)
 title=db.Column(db.String(180),nullable=False)
 description=db.Column(db.Text,default='',nullable=False)
 location=db.Column(db.String(180),default='Matera',nullable=False)
 category=db.Column(db.String(60),default='cultura',nullable=False)
 booking_mode=db.Column(db.String(16),default='request',nullable=False)
 price_cents=db.Column(db.Integer,default=2500,nullable=False)
 active=db.Column(db.Boolean,default=True,nullable=False)
 def public(self):return dict(id=self.id,title=self.title,description=self.description,location=self.location,category=self.category,booking_mode=self.booking_mode,price_cents=self.price_cents,active=self.active)
class Slot(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 experience_id=db.Column(db.Integer,db.ForeignKey('experience.id'),nullable=False,index=True)
 starts_at=db.Column(db.DateTime(timezone=True),nullable=False)
 capacity=db.Column(db.Integer,nullable=False)
 active=db.Column(db.Boolean,default=True,nullable=False)
 def public(self,remaining):return dict(id=self.id,experience_id=self.experience_id,starts_at=self.starts_at.replace(tzinfo=UTC).isoformat(),capacity=self.capacity,remaining=max(0,remaining))
class Booking(db.Model):
 id=db.Column(db.Integer,primary_key=True)
 reference=db.Column(db.String(32),unique=True,nullable=False)
 slot_id=db.Column(db.Integer,db.ForeignKey('slot.id'),nullable=False,index=True)
 name=db.Column(db.String(120),nullable=False)
 email=db.Column(db.String(180),nullable=False)
 guests=db.Column(db.Integer,nullable=False)
 amount_cents=db.Column(db.Integer,nullable=False)
 status=db.Column(db.String(20),nullable=False)
 expires_at=db.Column(db.DateTime(timezone=True))
 stripe_session_id=db.Column(db.String(255),unique=True)
 created_at=db.Column(db.DateTime(timezone=True),default=now,nullable=False)
 def public(self):return dict(id=self.id,reference=self.reference,slot_id=self.slot_id,name=self.name,email=self.email,guests=self.guests,amount_cents=self.amount_cents,status=self.status,created_at=self.created_at.isoformat())

# PostgreSQL uses SELECT FOR UPDATE on slots; SQLite serializes writes using BEGIN IMMEDIATE.
def lock_slot(slot_id):
 if db.engine.dialect.name=='sqlite': db.session.execute(text('BEGIN IMMEDIATE'))
 stmt=select(Slot).where(Slot.id==slot_id)
 if db.engine.dialect.name!='sqlite':stmt=stmt.with_for_update()
 return db.session.scalar(stmt)
def held_or_booked(slot_id):
 valid=['confirmed','pending_request','awaiting_payment']
 rows=db.session.scalars(select(Booking).where(Booking.slot_id==slot_id,Booking.status.in_(valid))).all()
 current=now().replace(tzinfo=None)
 return sum(b.guests for b in rows if b.status!='awaiting_payment' or (b.expires_at and b.expires_at.replace(tzinfo=None)>current))
def require_login(fn):
 @wraps(fn)
 def inner(*a,**kw):
  user=db.session.get(Operator,session.get('operator_id')) if session.get('operator_id') else None
  if not user or not user.active:return fail('Accesso richiesto',401)
  return fn(user,*a,**kw)
 return inner
@app.after_request
def headers(r):
 r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='strict-origin-when-cross-origin'
 return r
@app.get('/')
def home():return render_template('index.html')
@app.get('/prenota')
def booking_page():return render_template('booking.html')
@app.get('/operatori')
def operator_page():return render_template('operator.html')
@app.get('/health')
def health():return jsonify(status='ok')
@app.get('/api/experiences')
def experiences():return jsonify([e.public() for e in db.session.scalars(select(Experience).where(Experience.active==True)).all()])
@app.get('/api/experiences/<int:eid>/slots')
def slots(eid):
 e=db.session.get(Experience,eid)
 if not e or not e.active:return fail('Esperienza non trovata',404)
 from_date=request.args.get('from',date.today().isoformat())
 try:start=date.fromisoformat(from_date)
 except ValueError:return fail('Data non valida')
 if start<date.today():start=date.today()
 limit=datetime.combine(start+timedelta(days=61),datetime.min.time())
 rows=db.session.scalars(select(Slot).where(Slot.experience_id==eid,Slot.active==True,Slot.starts_at>=datetime.combine(start,datetime.min.time()),Slot.starts_at<limit).order_by(Slot.starts_at)).all()
 return jsonify([s.public(s.capacity-held_or_booked(s.id)) for s in rows])
@app.post('/api/bookings')
def create_booking():
 data=request.get_json(silent=True) or {}
 try: sid=int(data.get('slot_id',0));guests=int(data.get('guests',0))
 except (ValueError,TypeError):return fail('Partecipanti o orario non validi')
 name=str(data.get('name','')).strip();email=str(data.get('email','')).strip().lower()
 if not 2<=len(name)<=120 or len(email)>180 or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):return fail('Nome o email non validi')
 if not 1<=guests<=20 or data.get('privacy_ack') is not True:return fail('Partecipanti o presa visione privacy non validi')
 try:
  slot=lock_slot(sid)
  if not slot or not slot.active or slot.starts_at.replace(tzinfo=None)<=now().replace(tzinfo=None):db.session.rollback();return fail('Orario non disponibile',409)
  exp=db.session.get(Experience,slot.experience_id)
  if not exp or not exp.active:db.session.rollback();return fail('Esperienza non disponibile',409)
  if guests>slot.capacity-held_or_booked(sid):db.session.rollback();return fail('Posti insufficienti',409)
  status='pending_request' if exp.booking_mode=='request' else 'awaiting_payment'
  expiry=(now()+timedelta(minutes=35)).replace(tzinfo=None) if status=='awaiting_payment' else None
  b=Booking(reference='ME-'+secrets.token_hex(5).upper(),slot_id=sid,name=name,email=email,guests=guests,amount_cents=exp.price_cents*guests,status=status,expires_at=expiry)
  db.session.add(b);db.session.commit()
  return jsonify(reference=b.reference,booking_id=b.id,status=b.status,amount_cents=b.amount_cents,expires_at=expiry.isoformat() if expiry else None),201
 except Exception:
  db.session.rollback();app.logger.exception('booking failed');return fail('Impossibile completare la richiesta',500)
@app.post('/api/bookings/<int:bid>/checkout')
def checkout(bid):
 b=db.session.get(Booking,bid)
 # Public checkout requires an unguessable booking reference as bearer capability.
 if not b or not secrets.compare_digest(request.headers.get('X-Booking-Reference',''),b.reference):return fail('Prenotazione non trovata',404)
 if b.status!='awaiting_payment' or not b.expires_at or b.expires_at.replace(tzinfo=None)<=now().replace(tzinfo=None):return fail('Blocco posti scaduto',409)
 if not os.getenv('STRIPE_SECRET_KEY'):return fail('Pagamenti non configurati; nessun addebito eseguito',503)
 import stripe
 stripe.api_key=os.environ['STRIPE_SECRET_KEY']
 exp=db.session.get(Experience,db.session.get(Slot,b.slot_id).experience_id)
 base=os.getenv('PUBLIC_BASE_URL','http://localhost:5000').rstrip('/')
 try:
  checkout_session=stripe.checkout.Session.create(mode='payment',customer_email=b.email,client_reference_id=b.reference,metadata={'booking_id':str(b.id)},line_items=[{'price_data':{'currency':'eur','unit_amount':exp.price_cents,'product_data':{'name':exp.title}},'quantity':b.guests}],success_url=base+'/prenota?payment=return',cancel_url=base+'/prenota?payment=cancel',expires_at=int(b.expires_at.replace(tzinfo=UTC).timestamp()),idempotency_key='matera-'+b.reference)
  b.stripe_session_id=checkout_session.id;db.session.commit()
  return jsonify(url=checkout_session.url)
 except Exception:
  db.session.rollback();app.logger.exception('stripe checkout failed');return fail('Checkout temporaneamente non disponibile',502)
@app.post('/api/stripe/webhook')
def webhook():
 secret=os.getenv('STRIPE_WEBHOOK_SECRET')
 if not secret:return fail('Webhook non configurato',503)
 import stripe
 try:event=stripe.Webhook.construct_event(request.get_data(),request.headers.get('Stripe-Signature',''),secret)
 except (ValueError,stripe.error.SignatureVerificationError):return fail('Firma non valida')
 obj=event['data']['object']
 if event['type'] in ('checkout.session.completed','checkout.session.async_payment_succeeded') and obj.get('payment_status')=='paid':
  bid=int(obj.get('metadata',{}).get('booking_id',0));b=db.session.get(Booking,bid)
  if b and b.stripe_session_id==obj.get('id') and b.status=='awaiting_payment':
   b.status='confirmed';db.session.commit()
 if event['type']=='checkout.session.expired':
  b=db.session.scalar(select(Booking).where(Booking.stripe_session_id==obj.get('id')))
  if b and b.status=='awaiting_payment':b.status='expired';db.session.commit()
 return jsonify(received=True)
@app.post('/api/operator/login')
def login():
 d=request.get_json(silent=True) or {};u=db.session.scalar(select(Operator).where(Operator.email==str(d.get('email','')).lower()))
 if not u or not u.active or not check_password_hash(u.password_hash,str(d.get('password',''))):return fail('Credenziali non valide',401)
 session.clear();session['operator_id']=u.id;return jsonify(name=u.name)
@app.post('/api/operator/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/operator/me')
@require_login
def me(u):return jsonify(id=u.id,name=u.name,email=u.email)
@app.get('/api/operator/dashboard')
@require_login
def dashboard(u):
 exps=db.session.scalars(select(Experience).where(Experience.operator_id==u.id)).all()
 ids=[e.id for e in exps]
 sl=db.session.scalars(select(Slot).where(Slot.experience_id.in_(ids)).order_by(Slot.starts_at)).all() if ids else []
 bookings=db.session.scalars(select(Booking).where(Booking.slot_id.in_([s.id for s in sl])).order_by(Booking.id.desc())).all() if sl else []
 return jsonify(experiences=[e.public() for e in exps],slots=[dict(**s.public(s.capacity-held_or_booked(s.id)),experience_title=next(e.title for e in exps if e.id==s.experience_id)) for s in sl],bookings=[b.public() for b in bookings])
@app.post('/api/operator/experiences')
@require_login
def add_experience(u):
 d=request.get_json(silent=True) or {};title=str(d.get('title','')).strip();mode=d.get('booking_mode','request')
 try:price=int(d.get('price_cents',2500))
 except (ValueError,TypeError):return fail('Prezzo non valido')
 if len(title)<3 or len(title)>180 or mode not in ('request','direct') or not 0<=price<=10000000:return fail('Dati esperienza non validi')
 e=Experience(operator_id=u.id,title=title,description=str(d.get('description',''))[:3000],location=str(d.get('location','Matera'))[:180],booking_mode=mode,price_cents=price)
 db.session.add(e);db.session.commit();return jsonify(e.public()),201
@app.post('/api/operator/slots')
@require_login
def add_slot(u):
 d=request.get_json(silent=True) or {}
 try:eid=int(d.get('experience_id'));capacity=int(d.get('capacity'));starts=datetime.fromisoformat(str(d.get('starts_at')))
 except (ValueError,TypeError):return fail('Data, capienza o esperienza non validi')
 e=db.session.get(Experience,eid)
 if not e or e.operator_id!=u.id:return fail('Esperienza non autorizzata',403)
 if starts.tzinfo is None:return fail('Indica il fuso orario (es. +01:00)')
 starts=starts.astimezone(UTC).replace(tzinfo=None)
 if starts<=now().replace(tzinfo=None) or not 1<=capacity<=1000:return fail('Data passata o capienza non valida')
 s=Slot(experience_id=eid,starts_at=starts,capacity=capacity);db.session.add(s);db.session.commit();return jsonify(s.public(capacity)),201
@app.patch('/api/operator/bookings/<int:bid>')
@require_login
def change_booking(u,bid):
 b=db.session.get(Booking,bid)
 if not b:return fail('Prenotazione inesistente',404)
 sl=db.session.get(Slot,b.slot_id);exp=db.session.get(Experience,sl.experience_id)
 if exp.operator_id!=u.id:return fail('Non autorizzato',403)
 d=request.get_json(silent=True) or {};status=d.get('status')
 if b.status=='pending_request' and status in ('confirmed','declined'):
  b.status=status;db.session.commit();return jsonify(b.public())
 return fail('Transizione non consentita: i pagamenti si confermano solo tramite webhook',409)
@app.cli.command('init-demo')
def init_demo():
 with app.app_context():
  db.create_all()
  if not db.session.scalar(select(Operator).limit(1)):
   pwd=os.getenv('DEMO_OPERATOR_PASSWORD')
   if not pwd:raise RuntimeError('Imposta DEMO_OPERATOR_PASSWORD prima di eseguire init-demo')
   u=Operator(name='Operatore Matera Experience',email=os.getenv('DEMO_OPERATOR_EMAIL','operatore@example.com'),password_hash=generate_password_hash(pwd));db.session.add(u);db.session.flush()
   for title,mode in [('Tour dei Sassi di Matera','direct'),('Passeggiata panoramica','request')]:
    e=Experience(operator_id=u.id,title=title,booking_mode=mode,price_cents=2500);db.session.add(e);db.session.flush()
    for days in (3,4,5,7):db.session.add(Slot(experience_id=e.id,starts_at=(datetime.combine(date.today()+timedelta(days=days),datetime.min.time())+timedelta(hours=15,minutes=30)),capacity=12))
   db.session.commit();print('Demo creata; credenziali dall’ambiente')
  else:print('Operatori già presenti: nessuna modifica')
with app.app_context():db.create_all()
if __name__=='__main__':app.run(debug=False)
