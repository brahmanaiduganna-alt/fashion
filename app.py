import os, re, base64, hashlib, sqlite3, requests, traceback
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "styleai_hackathon_2024"
CORS(app, supports_credentials=True)

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

# ── ONLY safe way on Windows Python 3.14 ─────────────────────────
try:
    os.mkdir(UPLOAD_FOLDER)
except FileExistsError:
    pass   # already exists — this is fine, continue
except Exception as e:
    print(f"mkdir warning: {e}")

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
ALLOWED = {"png", "jpg", "jpeg", "webp", "gif"}

# ── Groq ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    pass

GROQ_KEY    = os.environ.get("GROQ_API_KEY", "")
GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_TEXT   = "llama-3.3-70b-versatile"
GROQ_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"

print("=" * 55)
print("  StyleAI — Hackathon Edition")
print(f"  API Key  : {'SET ✅' if GROQ_KEY else 'MISSING ⚠️  add to .env'}")
print(f"  Uploads  : {UPLOAD_FOLDER}")
print(f"  Folder   : {'EXISTS ✅' if os.path.isdir(UPLOAD_FOLDER) else 'MISSING ❌'}")
print("=" * 55)

# ── Database ──────────────────────────────────────────────────────
DB = os.path.join(BASE_DIR, "fashion_ai.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, phone TEXT UNIQUE, email TEXT UNIQUE,
            password TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS fashion_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, gender TEXT, age INTEGER, size TEXT,
            culture_style TEXT, dress_style TEXT, photo_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, profile_id INTEGER,
            request_type TEXT, input_data TEXT, ai_response TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    print("  DB       : Ready ✅")

init_db()

# ── Helpers ───────────────────────────────────────────────────────
def hashpw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def ok_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in ALLOWED

def strip_md(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    return text.strip()

def save_rec(uid, pid, rtype, idata, resp):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO ai_recommendations (user_id,profile_id,request_type,input_data,ai_response) VALUES (?,?,?,?,?)",
            (uid, pid, rtype, str(idata), resp)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB error: {e}")

def call_text(prompt):
    if not GROQ_KEY:
        return "⚠️ GROQ_API_KEY not set. Add it to your .env file and restart."
    try:
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_TEXT,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7},
            timeout=45)
        r.raise_for_status()
        return strip_md(r.json()["choices"][0]["message"]["content"])
    except requests.Timeout:
        return "Request timed out. Please try again."
    except Exception as e:
        return f"API Error: {e}"

def call_vision(prompt, img_path):
    if not GROQ_KEY:
        return "⚠️ GROQ_API_KEY not set. Add it to your .env file and restart."
    try:
        ext  = img_path.rsplit(".", 1)[-1].lower()
        mime = {"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                "webp":"image/webp","gif":"image/gif"}.get(ext, "image/jpeg")
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        r = requests.post(GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={
                "model": GROQ_VISION,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt}
                ]}],
                "temperature": 0.7,
                "max_tokens": 1200
            },
            timeout=90)
        r.raise_for_status()
        return strip_md(r.json()["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"Vision failed ({e}), falling back to text")
        return call_text(prompt)

# ── Routes ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"ok": True, "key": bool(GROQ_KEY),
                    "uploads_exist": os.path.isdir(UPLOAD_FOLDER)})

# Auth
@app.route("/signup", methods=["POST"])
def signup():
    d     = request.get_json(force=True, silent=True) or {}
    name  = d.get("name","").strip()
    phone = d.get("phone","").strip()
    email = d.get("email","").strip()
    pw    = d.get("password","")
    if not (phone or email):
        return jsonify({"success": False, "message": "Phone or email required"}), 400
    if not pw:
        return jsonify({"success": False, "message": "Password required"}), 400
    try:
        conn = get_db()
        cur  = conn.execute(
            "INSERT INTO users (name,phone,email,password) VALUES (?,?,?,?)",
            (name, phone or None, email or None, hashpw(pw))
        )
        uid = cur.lastrowid
        conn.commit(); conn.close()
        session["user_id"] = uid; session["user_name"] = name
        return jsonify({"success": True, "name": name})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Phone/email already registered"}), 400

@app.route("/login", methods=["POST"])
def login():
    d     = request.get_json(force=True, silent=True) or {}
    ident = d.get("identifier","").strip()
    pw    = d.get("password","")
    conn  = get_db()
    user  = conn.execute(
        "SELECT * FROM users WHERE (phone=? OR email=?) AND password=?",
        (ident, ident, hashpw(pw))
    ).fetchone()
    conn.close()
    if user:
        session["user_id"]   = user["id"]
        session["user_name"] = user["name"] or ident
        return jsonify({"success": True, "name": user["name"]})
    return jsonify({"success": False, "message": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/me")
def api_me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"logged_in": False})
    conn = get_db()
    u    = conn.execute(
        "SELECT id,name,phone,email,created_at FROM users WHERE id=?", (uid,)
    ).fetchone()
    conn.close()
    return jsonify({"logged_in": True, "user": dict(u)}) if u else jsonify({"logged_in": False})

@app.route("/api/history")
def api_history():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"success": False, "message": "Not logged in"}), 401
    conn = get_db()
    rows = conn.execute(
        "SELECT id,request_type,input_data,ai_response,created_at "
        "FROM ai_recommendations WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify({"success": True, "history": [dict(r) for r in rows]})

# AI Tools
@app.route("/get_recommendation", methods=["POST"])
def get_recommendation():
    try:
        uid           = session.get("user_id")
        gender        = request.form.get("gender",        "Not specified")
        age           = request.form.get("age",           "25")
        size          = request.form.get("size",          "M")
        culture_style = request.form.get("culture_style", "Universal")
        dress_style   = request.form.get("dress_style",   "Casual")

        # Photo — save directly, no mkdir
        photo_path = ""
        has_photo  = False
        photo = request.files.get("photo")
        if photo and photo.filename and ok_file(photo.filename):
            fname      = secure_filename(photo.filename)
            photo_path = os.path.join(UPLOAD_FOLDER, fname)
            photo.save(photo_path)
            has_photo  = True

        # Save profile
        profile_id = None
        if uid:
            conn = get_db()
            cur  = conn.execute(
                "INSERT INTO fashion_profiles "
                "(user_id,gender,age,size,culture_style,dress_style,photo_path) "
                "VALUES (?,?,?,?,?,?,?)",
                (uid, gender, age, size, culture_style, dress_style, photo_path)
            )
            profile_id = cur.lastrowid
            conn.commit(); conn.close()

        prompt = f"""You are an expert fashion stylist with deep knowledge of global trends.
{"Carefully study the uploaded photo — note skin tone, body type, hair, and current style." if has_photo else ""}

Customer Profile:
- Gender: {gender}
- Age: {age}
- Size: {size}
- Cultural Style: {culture_style}
- Desired Style: {dress_style}

Provide a complete personalised styling report:

1. OUTFIT RECOMMENDATIONS (5 outfits):
   Name, description of top/bottom/shoes, and why it suits this person.

2. COLOUR PALETTE (3 combinations):
   Primary, secondary, accent — and why they work for this profile.

3. ACCESSORIES (2 suggestions):
   Specific items with brands if possible.

4. STYLING TIP:
   One powerful personalised tip{"based on the photo" if has_photo else ""}.

Be warm, specific, and encouraging."""

        result = call_vision(prompt, photo_path) if has_photo else call_text(prompt)

        save_rec(uid, profile_id, "outfit",
                 {"gender":gender,"age":age,"size":size,"style":dress_style,"photo":has_photo},
                 result)

        return jsonify({"result": result, "photo_analyzed": has_photo})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"result": f"Error: {str(e)}. Please try again."}), 200


@app.route("/generate_pitch", methods=["POST"])
def generate_pitch():
    uid      = session.get("user_id")
    product  = request.form.get("product", "").strip()
    customer = request.form.get("customer","").strip()
    if not product:
        return jsonify({"result": "Please enter an outfit or collection description."})
    prompt = f"""You are a luxury fashion copywriter.
Outfit/Collection: {product}
Target Customer: {customer or 'Fashion-forward individuals'}

Write a compelling fashion pitch:
1. ELEVATOR PITCH: 2-3 vivid sentences.
2. VALUE PROPOSITION: Why this is perfect for this customer.
3. KEY DIFFERENTIATORS: 3 standout features.
4. CALL TO ACTION: A warm, motivating closing line."""
    result = call_text(prompt)
    save_rec(uid, None, "pitch", {"product": product, "customer": customer}, result)
    return jsonify({"result": result})


@app.route("/lead_score", methods=["POST"])
def lead_score():
    uid     = session.get("user_id")
    name    = request.form.get("name",    "Customer")
    budget  = request.form.get("budget",  "Not specified")
    need    = request.form.get("need",    "Not specified")
    urgency = request.form.get("urgency", "Not specified")
    prompt = f"""You are an AI fashion consultant.
Customer: {name} | Budget: {budget} | Occasion: {need} | Timeline: {urgency}

Give a STYLE FIT SCORE (0-100):
1. Budget Fit (0-25 pts)
2. Occasion Fit (0-25 pts)
3. Urgency Score (0-25 pts)
4. Personalisation (0-25 pts)

Include:
- TOTAL SCORE: X / 100
- One-sentence reasoning per dimension
- TIER: HOT (90-100) / WARM (75-89) / MODERATE (60-74) / COLD (below 60)
- Match probability: X%
- One personalised styling suggestion"""
    result = call_text(prompt)
    save_rec(uid, None, "lead_score", {"name":name,"budget":budget,"need":need}, result)
    return jsonify({"result": result})


@app.route("/generate_campaign", methods=["POST"])
def generate_campaign():
    uid      = session.get("user_id")
    product  = request.form.get("product", "").strip()
    audience = request.form.get("audience","").strip()
    platform = request.form.get("platform","Instagram").strip()
    if not product:
        return jsonify({"result": "Please enter a product or collection name."})
    prompt = f"""You are a fashion marketing strategist.
Product: {product} | Audience: {audience or 'Fashion enthusiasts'} | Platform: {platform}

Create a full marketing campaign:
1. CAMPAIGN OBJECTIVE
2. 5 CONTENT IDEAS for {platform}
3. 3 AD COPIES (Emotional / Trend-focused / Urgency-driven)
4. 3 CALL-TO-ACTION options
5. HASHTAGS: 6-8 targeted hashtags"""
    result = call_text(prompt)
    save_rec(uid, None, "campaign", {"product":product,"audience":audience,"platform":platform}, result)
    return jsonify({"result": result})


# ── Run ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n  ▶  Open: http://127.0.0.1:5000\n")
    app.run(debug=True, host="127.0.0.1", port=5000, use_reloader=False)