"""Dubai Mediation Workspace: local-testing MVP.
Install: python -m pip install 'Flask>=3.1,<4'
Run: python dubai_mediator.py
Open: http://127.0.0.1:5000
Not production-ready; no government, payment, AI or signature integrations.
"""
import os
import re
import json
import time
import hmac
import secrets
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from functools import wraps
from collections import defaultdict, deque
from flask import Flask, request, session, redirect, url_for, abort, flash, g, render_template_string
from werkzeug.security import generate_password_hash, check_password_hash

HOME = Path(os.environ.get('MEDIATOR_DATA', './mediator_data')).resolve()
HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
secret_path = HOME / 'session.key'
if not secret_path.exists():
    try:
        fd = os.open(str(secret_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
app = Flask(__name__)
app.config.update(SECRET_KEY=secret_path.read_text().strip(),
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('MEDIATOR_HTTPS') == '1',
    PERMANENT_SESSION_LIFETIME=3600, MAX_CONTENT_LENGTH=64 * 1024)
DB_PATH = HOME / 'workspace.sqlite3'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
 password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('landlord','tenant')));
CREATE TABLE IF NOT EXISTS cases (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, property TEXT NOT NULL,
 category TEXT NOT NULL, statement TEXT NOT NULL, creator INTEGER NOT NULL REFERENCES users(id),
 counterpart INTEGER REFERENCES users(id), invite_email TEXT NOT NULL,
 invite_hash TEXT UNIQUE, invite_expires INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'awaiting_counterparty', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
 author INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
 body TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offers (
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
 author INTEGER NOT NULL REFERENCES users(id), terms TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS acceptances (
 offer_id INTEGER NOT NULL REFERENCES offers(id), user_id INTEGER NOT NULL REFERENCES users(id),
 created TEXT NOT NULL, PRIMARY KEY(offer_id,user_id));
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
 actor INTEGER NOT NULL REFERENCES users(id), action TEXT NOT NULL, created TEXT NOT NULL);
'''
with sqlite3.connect(DB_PATH) as con:
    con.executescript(SCHEMA)
try:
    os.chmod(DB_PATH, 0o600)
except OSError:
    pass

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(error):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def text(name, limit=4000):
    value = request.form.get(name, '').strip()
    if not value or len(value) > limit:
        abort(400, description=f'{name}: required; maximum {limit} characters.')
    return value

def email_value(name):
    value = text(name, 254).lower()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        abort(400, description='Enter a valid email address.')
    return value

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped

def get_case(cid):
    case = db().execute('SELECT * FROM cases WHERE id=? AND (creator=? OR counterpart=?)',
        (cid, g.user['id'], g.user['id'])).fetchone()
    if case is None:
        abort(404)
    return case

def audit(cid, action):
    db().execute('INSERT INTO events(case_id,actor,action,created) VALUES(?,?,?,?)',
        (cid, g.user['id'], action, now()))

def active(case):
    if case['status'] != 'active':
        abort(409, description='This case is not active.')

attempts = defaultdict(deque)
def throttle():
    # Local single-process safeguard, not a production distributed limiter.
    key = request.remote_addr or 'local'
    queue = attempts[key]
    stamp = time.monotonic()
    while queue and queue[0] < stamp - 300:
        queue.popleft()
    if len(queue) >= 30:
        abort(429, description='Too many attempts; wait five minutes.')
    queue.append(stamp)

@app.before_request
def prepare():
    session.setdefault('csrf', secrets.token_urlsafe(32))
    g.user = db().execute('SELECT id,email,role FROM users WHERE id=?',
        (session.get('uid'),)).fetchone()
    if request.method == 'POST':
        supplied = request.form.get('csrf', '')
        if not hmac.compare_digest(supplied, session['csrf']):
            abort(400, description='Form expired. Reload the page.')

@app.after_request
def secure_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response

BASE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }} | Dubai Mediation Workspace</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#17283e;font:16px/1.6 system-ui,sans-serif}
header{background:#132c45;color:white;padding:20px max(5vw,20px)}main{max-width:960px;margin:25px auto;padding:0 20px}
a{color:#09645f}header a{color:white}nav{display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.card,article{background:white;padding:22px;margin:18px 0;border:1px solid #d4dde7;border-radius:10px}
.notice{background:#fff3cf;padding:16px;border-left:4px solid #916200}
label{display:block;margin-top:14px;font-weight:600}input,select,textarea{display:block;width:100%;padding:10px;border:1px solid #7c8b9c;border-radius:5px;font:inherit}
textarea{min-height:100px}button{background:#08645e;color:white;border:0;border-radius:5px;padding:11px 16px;margin-top:14px;font:inherit;cursor:pointer}
button.danger{background:#883932}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid #b47600;outline-offset:3px}
.inline{display:inline}.inline button{margin:0}.muted,small{color:#4c5e73}.content{white-space:pre-wrap;overflow-wrap:anywhere}
code{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #d4dde7}h1,h2,h3{line-height:1.3}
</style></head><body><header><strong>Dubai Mediation Workspace</strong>
<nav><a href="{{ url_for('index') }}">Cases</a>{% if g.user %}<a href="{{ url_for('new_case') }}">New case</a>
<span>{{ g.user.email }} · {{ g.user.role }}</span><form class="inline" method="post" action="{{ url_for('logout') }}">{{ csrf() }}<button>Sign out</button></form>
{% else %}<a href="{{ url_for('login') }}">Sign in</a><a href="{{ url_for('register') }}">Register</a>{% endif %}</nav></header>
<main><p class="notice"><strong>Local-testing MVP — Dubai only.</strong> Voluntary negotiation workspace, not a government service, lawyer, court, or certified human mediator. Do not enter real personal data. No legal deadlines are paused. No emergency response is provided.</p>
{% for message in get_flashed_messages() %}<p class="notice" role="status">{{ message }}</p>{% endfor %}
<h1>{{ title }}</h1>{{ body|safe }}<footer class="card"><strong>Dubai scope and limits</strong><p>Dubai residential tenancy discussions only. DIFC, commercial leases and uncertain jurisdiction require separate human review. The app does not validate jurisdiction or determine legal rights. For official information start with <a href="https://dubailand.gov.ae/" target="_blank" rel="noopener noreferrer">Dubai Land Department</a>. There is no DLD, Ejari, RDC or payment connection.</p>
<p>Safety, harassment, eviction threats and urgent habitability issues need appropriate professional or emergency help outside this app. Agreements recorded here are not automatically legally binding or court orders.</p></footer></main></body></html>'''

from markupsafe import Markup, escape
@app.context_processor
def helpers():
    def csrf():
        return Markup('<input type="hidden" name="csrf" value="{}">').format(escape(session['csrf']))
    return {'csrf': csrf}

def page(title, template, **values):
    body = render_template_string(template, **values)
    return render_template_string(BASE, title=title, body=body)

AUTH = '''<form class="card" method="post">{{ csrf() }}
<label>Email<input name="email" type="email" required maxlength="254" autocomplete="email"></label>
<label>Password<input name="password" type="password" required minlength="12" maxlength="128" autocomplete="{{ 'new-password' if registration else 'current-password' }}"></label>
{% if registration %}<label>Role<select name="role"><option value="tenant">Tenant</option><option value="landlord">Landlord</option></select></label>
<p>Use fictitious test details. Emails and roles are self-asserted, not verified.</p>{% endif %}<button>{{ 'Create test account' if registration else 'Sign in' }}</button></form>'''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        throttle()
        email = email_value('email')
        password = text('password', 128)
        role = text('role', 20)
        if len(password) < 12 or role not in ('tenant', 'landlord'):
            abort(400, description='Use at least 12 password characters and an allowed role.')
        try:
            with db():
                db().execute('INSERT INTO users(email,password,role) VALUES(?,?,?)',
                    (email, generate_password_hash(password), role))
        except sqlite3.IntegrityError:
            flash('Account could not be created. Try signing in.')
            return redirect(url_for('register'))
        flash('Test account created. Sign in to continue.')
        return redirect(url_for('login'))
    return page('Create account', AUTH, registration=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        throttle()
        email = email_value('email')
        password = text('password', 128)
        user = db().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if user and check_password_hash(user['password'], password):
            session.clear()
            session['uid'] = user['id']
            session['csrf'] = secrets.token_urlsafe(32)
            session.permanent = True
            return redirect(url_for('index'))
        flash('Incorrect email or password.')
    return page('Sign in', AUTH, registration=False)

@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.get('/')
@login_required
def index():
    cases = db().execute('SELECT * FROM cases WHERE creator=? OR counterpart=? ORDER BY id DESC',
        (g.user['id'], g.user['id'])).fetchall()
    return page('Your Dubai cases', '''<p>Access is limited to the two participating accounts. All case messages and evidence notes are shared with both participants.</p>
<a href="{{ url_for('new_case') }}">Open a case</a><section class="card"><table><tr><th>Case</th><th>Status</th></tr>
{% for c in cases %}<tr><td><a href="{{ url_for('case_detail', cid=c.id) }}">#{{ c.id }} {{ c.title }}</a></td><td>{{ c.status|replace('_',' ') }}</td></tr>
{% else %}<tr><td colspan="2">No cases yet.</td></tr>{% endfor %}</table></section>''', cases=cases)

@app.route('/cases/new', methods=['GET', 'POST'])
@login_required
def new_case():
    if request.method == 'POST':
        title = text('title', 140)
        property_name = text('property', 300)
        statement = text('statement', 6000)
        category = text('category', 40)
        email = email_value('invite_email')
        if category not in ('Repairs', 'Rent discussion', 'Deposit discussion', 'Other'):
            abort(400)
        if email == g.user['email']:
            abort(400, description='Invite a different person.')
        if request.form.get('consent') != 'yes' or request.form.get('scope') != 'yes':
            abort(400, description='Voluntary participation and Dubai scope confirmation required.')
        token = secrets.token_urlsafe(32)
        import hashlib
        with db():
            cursor = db().execute('''INSERT INTO cases(title,property,category,statement,creator,invite_email,invite_hash,invite_expires,created)
                VALUES(?,?,?,?,?,?,?,?,?)''', (title, property_name, category, statement, g.user['id'], email,
                hashlib.sha256(token.encode()).hexdigest(), int(time.time()) + 7*86400, now()))
            cid = cursor.lastrowid
            audit(cid, 'Creator consented; invitation created (7-day expiry).')
        return page('Case created — share invitation privately', '''<section class="card"><p>The invitation is shown once. Copy it now and share with the intended participant using a trusted channel. No email has been sent.</p>
<p>Recipient must register/sign in with <strong>{{ email }}</strong> before opening this link.</p>
<p class="content">{{ link }}</p><p>Expires in seven days. No real identity or email ownership verification is implemented.</p><a href="{{ url_for('case_detail',cid=cid) }}">Open case</a></section>''',
            email=email, link=url_for('join_case', token=token, _external=True), cid=cid)
    return page('Open a Dubai case', '''<form method="post" class="card">{{ csrf() }}
<label>Case title<input name="title" maxlength="140" required></label>
<label>Dubai property reference (test data only)<input name="property" maxlength="300" required></label>
<label>Category<select name="category"><option>Repairs</option><option>Rent discussion</option><option>Deposit discussion</option><option>Other</option></select></label>
<label>Other participant email<input name="invite_email" type="email" required maxlength="254"></label>
<label>Your account of events<textarea name="statement" required maxlength="6000"></textarea></label>
<label><input type="checkbox" name="scope" value="yes" required>I confirm this test concerns Dubai residential tenancy, outside DIFC, not a commercial lease.</label>
<label><input type="checkbox" name="consent" value="yes" required>I voluntarily participate and understand the other participant can see all case content. This is not legal advice or emergency help.</label>
<button>Create case and private invitation</button></form>''')

@app.route('/join/<token>', methods=['GET', 'POST'])
@login_required
def join_case(token):
    import hashlib
    case = db().execute('SELECT * FROM cases WHERE invite_hash=?',
        (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not case or case['invite_email'] != g.user['email'] or case['invite_expires'] < time.time():
        abort(404, description='Invitation unavailable, expired, or for another account.')
    creator = db().execute('SELECT role FROM users WHERE id=?', (case['creator'],)).fetchone()
    if creator['role'] == g.user['role']:
        abort(403, description='This MVP requires one landlord and one tenant.')
    if request.method == 'POST':
        decision = text('decision', 20)
        if decision not in ('join', 'decline'):
            abort(400)
        with db():
            db().execute('BEGIN IMMEDIATE')
            fresh = db().execute('SELECT * FROM cases WHERE id=?', (case['id'],)).fetchone()
            if fresh['status'] != 'awaiting_counterparty' or fresh['invite_hash'] != case['invite_hash'] or fresh['invite_expires'] < time.time():
                abort(409)
            db().execute('UPDATE cases SET counterpart=?,status=?,invite_hash=NULL WHERE id=?',
                (g.user['id'], 'active' if decision == 'join' else 'declined', case['id']))
            audit(case['id'], 'Counterparty consented.' if decision == 'join' else 'Invitation declined.')
        return redirect(url_for('case_detail', cid=case['id']))
    return page('Private invitation', '''<section class="card"><h2>{{ c.title }}</h2><p>By joining, you voluntarily agree to share case messages, evidence notes and proposals with the inviting participant. You can withdraw. No confidentiality privilege or suspension of deadlines is promised.</p>
<form method="post">{{ csrf() }}<button name="decision" value="join">Consent and join</button> <button class="danger" name="decision" value="decline">Decline</button></form></section>''', c=case)

CASE_TEMPLATE = '''<section class="card"><strong>{{ c.status|replace('_',' ') }}</strong><p>{{ c.property }} · {{ c.category }}</p><h2>Opening account — unverified</h2><div class="content">{{ c.statement }}</div>
<p><a href="{{ url_for('export_case',cid=c.id) }}">Export shared case record (JSON)</a></p></section>
{% if c.status == 'awaiting_counterparty' %}<p>Waiting for voluntary participation. Invitations expire after seven days. If the link is lost or expires, withdraw this test case and create another.</p>{% endif %}
<h2>Shared conversation and evidence notes</h2>
{% for m in messages %}<article><small>{{ m.email }} · {{ m.kind }} · {{ m.created }}</small><div class="content">{{ m.body }}</div></article>{% else %}<p>No entries.</p>{% endfor %}
{% if c.status == 'active' %}<form class="card" method="post" action="{{ url_for('message_case',cid=c.id) }}">{{ csrf() }}
<label>Entry type<select name="kind"><option value="message">Message</option><option value="evidence_note">Evidence note (not a verified document)</option></select></label>
<label>Shared text<textarea name="body" required maxlength="6000"></textarea></label><button>Share with both participants</button></form>{% endif %}
<h2>Settlement proposals</h2><p>These are immutable proposed terms, not legal recommendations. Posting counts as the author's acceptance. The other participant must explicitly accept the same version. Any new proposal supersedes pending ones. No qualified electronic signature is collected.</p>
{% for o in offers %}<article><small>Version #{{ o.id }} · {{ o.email }} · {{ o.state }} · {{ o.created }}</small><div class="content">{{ o.terms }}</div>
{% if c.status == 'active' and o.state == 'pending' and o.author != g.user.id %}<form method="post" action="{{ url_for('accept_offer',cid=c.id,oid=o.id) }}">{{ csrf() }}<label><input name="consent" type="checkbox" value="yes" required>I have read and accept exactly these terms voluntarily.</label><button>Record my acceptance</button></form>{% endif %}</article>{% endfor %}
{% if c.status == 'active' %}<form class="card" method="post" action="{{ url_for('propose',cid=c.id) }}">{{ csrf() }}<label>Proposed terms — include responsibilities, amounts in AED if any, dates and review arrangements<textarea name="terms" maxlength="8000" required></textarea></label><label><input name="consent" type="checkbox" value="yes" required>I accept my proposed wording; this replaces any pending proposal.</label><button>Submit and accept this proposal</button></form>{% endif %}
{% if c.status in ['active','awaiting_counterparty'] %}<form class="card" method="post" action="{{ url_for('withdraw',cid=c.id) }}">{{ csrf() }}<label><input name="confirm" type="checkbox" value="yes" required>I understand withdrawal ends negotiation, not legal duties or deadlines.</label><button class="danger">Withdraw from this case</button></form>{% endif %}
<h2>Shared activity log</h2><table><tr><th>Time (UTC)</th><th>Event</th></tr>{% for e in events %}<tr><td>{{ e.created }}</td><td>{{ e.action }}</td></tr>{% endfor %}</table>'''

@app.get('/cases/<int:cid>')
@login_required
def case_detail(cid):
    case = get_case(cid)
    messages = db().execute('SELECT m.*,u.email FROM messages m JOIN users u ON u.id=m.author WHERE case_id=? ORDER BY m.id', (cid,)).fetchall()
    offers = db().execute('SELECT o.*,u.email FROM offers o JOIN users u ON u.id=o.author WHERE case_id=? ORDER BY o.id DESC', (cid,)).fetchall()
    events = db().execute('SELECT * FROM events WHERE case_id=? ORDER BY id', (cid,)).fetchall()
    return page(case['title'], CASE_TEMPLATE, c=case, messages=messages, offers=offers, events=events)

@app.post('/cases/<int:cid>/messages')
@login_required
def message_case(cid):
    body = text('body', 6000)
    kind = text('kind', 30)
    if kind not in ('message', 'evidence_note'):
        abort(400)
    with db():
        db().execute('BEGIN IMMEDIATE')
        active(get_case(cid))
        db().execute('INSERT INTO messages(case_id,author,kind,body,created) VALUES(?,?,?,?,?)',
            (cid, g.user['id'], kind, body, now()))
        audit(cid, 'Shared ' + kind + ' added.')
    return redirect(url_for('case_detail', cid=cid))

@app.post('/cases/<int:cid>/offers')
@login_required
def propose(cid):
    terms = text('terms', 8000)
    if request.form.get('consent') != 'yes':
        abort(400)
    with db():
        db().execute('BEGIN IMMEDIATE')
        active(get_case(cid))
        db().execute("UPDATE offers SET state='superseded' WHERE case_id=? AND state='pending'", (cid,))
        cursor = db().execute('INSERT INTO offers(case_id,author,terms,created) VALUES(?,?,?,?)',
            (cid, g.user['id'], terms, now()))
        oid = cursor.lastrowid
        db().execute('INSERT INTO acceptances VALUES(?,?,?)', (oid, g.user['id'], now()))
        audit(cid, f'Proposal #{oid} created and accepted by its author.')
    return redirect(url_for('case_detail', cid=cid))

@app.post('/cases/<int:cid>/offers/<int:oid>/accept')
@login_required
def accept_offer(cid, oid):
    if request.form.get('consent') != 'yes':
        abort(400)
    with db():
        db().execute('BEGIN IMMEDIATE')
        case = get_case(cid)
        offer = db().execute('SELECT * FROM offers WHERE id=? AND case_id=?', (oid, cid)).fetchone()
        if not offer:
            abort(404)
        accepted = db().execute('SELECT 1 FROM acceptances WHERE offer_id=? AND user_id=?',
            (oid, g.user['id'])).fetchone()
        if offer['state'] == 'agreed' and accepted:
            return redirect(url_for('case_detail', cid=cid))
        active(case)
        if offer['state'] != 'pending' or offer['author'] == g.user['id']:
            abort(409, description='Proposal is no longer available for acceptance.')
        db().execute('INSERT OR IGNORE INTO acceptances VALUES(?,?,?)', (oid, g.user['id'], now()))
        ids = {r['user_id'] for r in db().execute('SELECT user_id FROM acceptances WHERE offer_id=?', (oid,))}
        if ids != {case['creator'], case['counterpart']}:
            abort(409)
        db().execute("UPDATE offers SET state='agreed' WHERE id=?", (oid,))
        db().execute("UPDATE cases SET status='agreement_recorded' WHERE id=?", (cid,))
        audit(cid, f'Both participants accepted proposal #{oid}; agreement recorded, not judicially validated.')
    flash('Mutual acceptance recorded. Seek qualified advice on execution and enforceability. Performance is not verified by this app.')
    return redirect(url_for('case_detail', cid=cid))

@app.post('/cases/<int:cid>/withdraw')
@login_required
def withdraw(cid):
    if request.form.get('confirm') != 'yes':
        abort(400)
    with db():
        db().execute('BEGIN IMMEDIATE')
        case = get_case(cid)
        if case['status'] not in ('active', 'awaiting_counterparty'):
            abort(409)
        db().execute("UPDATE cases SET status='withdrawn',invite_hash=NULL WHERE id=?", (cid,))
        db().execute("UPDATE offers SET state='withdrawn' WHERE case_id=? AND state='pending'", (cid,))
        audit(cid, 'Participation withdrawn. Legal duties and deadlines are unaffected.')
    return redirect(url_for('case_detail', cid=cid))

@app.get('/cases/<int:cid>/export')
@login_required
def export_case(cid):
    with db():
        db().execute('BEGIN')
        case = dict(get_case(cid))
        case.pop('invite_hash', None)
        result = {'notice': 'Shared negotiation record, not a court order or legal opinion.',
            'jurisdiction': 'Dubai residential tenancy; self-declared scope only', 'exported_at': now(), 'case': case}
        for table in ('messages', 'offers', 'events'):
            result[table] = [dict(r) for r in db().execute(f'SELECT * FROM {table} WHERE case_id=? ORDER BY id', (cid,))]
        result['acceptances'] = [dict(r) for r in db().execute('SELECT a.* FROM acceptances a JOIN offers o ON o.id=a.offer_id WHERE o.case_id=?', (cid,))]
    response = app.response_class(json.dumps(result, ensure_ascii=False, indent=2), mimetype='application/json')
    response.headers['Content-Disposition'] = f'attachment; filename=dubai-case-{cid}.json'
    return response

@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(413)
@app.errorhandler(429)
def friendly_error(error):
    return page('Request could not be completed', '<section class="card"><p>{{ explanation }}</p><a href="{{ url_for(\'index\') }}">Back to cases</a></section>',
        explanation=error.description), error.code

# Optional isolated integration smoke tests: python dubai_mediator.py --self-test
# These tests are supplied with the source; they were not executed by the authoring assistant.
def self_test():
    import tempfile
    import hashlib
    global DB_PATH
    old_path = DB_PATH
    with tempfile.TemporaryDirectory() as tmp:
        DB_PATH = Path(tmp) / 'test.sqlite3'
        with sqlite3.connect(DB_PATH) as con:
            con.executescript(SCHEMA)
            for email, role in [('owner@example.test','landlord'), ('renter@example.test','tenant'), ('outsider@example.test','tenant')]:
                con.execute('INSERT INTO users(email,password,role) VALUES(?,?,?)', (email, generate_password_hash('test-password-1234'), role))
        owner, tenant, outsider = [app.test_client() for _ in range(3)]
        def post(client, path, **data):
            client.get('/login')
            with client.session_transaction() as s:
                data['csrf'] = s['csrf']
            return client.post(path, data=data)
        for client, email in [(owner,'owner@example.test'),(tenant,'renter@example.test'),(outsider,'outsider@example.test')]:
            assert post(client, '/login', email=email, password='test-password-1234').status_code == 302
        assert owner.post('/cases/new', data={}).status_code == 400
        made = post(owner, '/cases/new', title='Repair discussion', property='Test Dubai home', category='Repairs',
            statement='A disputed repair.', invite_email='renter@example.test', consent='yes', scope='yes')
        assert made.status_code == 200
        token = re.search(r'/join/([A-Za-z0-9_-]+)', made.get_data(as_text=True)).group(1)
        assert outsider.get('/cases/1').status_code == 404
        assert outsider.get('/cases/1/export').status_code == 404
        assert outsider.get('/join/' + token).status_code == 404
        assert post(tenant, '/join/' + token, decision='join').status_code == 302
        assert post(tenant, '/join/' + token, decision='join').status_code == 404
        assert post(outsider, '/cases/1/messages', kind='message', body='Not allowed').status_code == 404
        assert post(tenant, '/cases/1/messages', kind='evidence_note', body='<script>alert(1)</script>').status_code == 302
        assert '&lt;script&gt;' in owner.get('/cases/1').get_data(as_text=True)
        assert post(owner, '/cases/1/offers', terms='Initial version.', consent='yes').status_code == 302
        assert post(tenant, '/cases/1/offers', terms='Revised terms.', consent='yes').status_code == 302
        assert post(tenant, '/cases/1/offers/1/accept', consent='yes').status_code == 409
        assert post(owner, '/cases/1/offers/2/accept', consent='yes').status_code == 302
        assert post(owner, '/cases/1/offers/2/accept', consent='yes').status_code == 302
        exported = tenant.get('/cases/1/export').get_json()
        assert exported['case']['status'] == 'agreement_recorded'
        assert 'invite_hash' not in exported['case']
        assert len(exported['acceptances']) == 3
        assert post(tenant, '/cases/1/messages', kind='message', body='Closed').status_code == 409
        assert post(owner, '/cases/1/withdraw', confirm='yes').status_code == 409
        assert post(owner, '/logout').status_code == 302
        assert owner.get('/cases/1').status_code == 302
        DB_PATH = old_path
    print('Smoke tests passed: CSRF, access isolation, invitation, XSS escaping, proposal versioning, mutual acceptance, export and closure.')

if __name__ == '__main__':
    import sys
    if '--self-test' in sys.argv:
        self_test()
    else:
        print('Dubai local-testing MVP: http://127.0.0.1:5000')
        print('Do not expose this development server to the Internet. Use fictitious data only.')
        app.run(host='127.0.0.1', port=5000, debug=False)
