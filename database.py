import sqlite3
import hashlib

DATABASE = "fashion_ai.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT,
            phone      TEXT UNIQUE,
            email      TEXT UNIQUE,
            password   TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS fashion_profiles (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER,
            gender        TEXT,
            age           INTEGER,
            size          TEXT,
            culture_style TEXT,
            dress_style   TEXT,
            photo_path    TEXT,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ai_recommendations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            profile_id   INTEGER,
            request_type TEXT,
            input_data   TEXT,
            ai_response  TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)    REFERENCES users(id),
            FOREIGN KEY (profile_id) REFERENCES fashion_profiles(id)
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Database initialized.")


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def create_user(name, phone, email, password):
    try:
        conn = get_db()
        cur  = conn.execute(
            "INSERT INTO users (name,phone,email,password) VALUES (?,?,?,?)",
            (name, phone or None, email or None, hash_password(password))
        )
        uid = cur.lastrowid
        conn.commit()
        conn.close()
        return True, uid
    except sqlite3.IntegrityError as e:
        return False, "Phone or email already registered."


def get_user_by_login(identifier, password):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE (phone=? OR email=?) AND password=?",
        (identifier, identifier, hash_password(password))
    ).fetchone()
    conn.close()
    return dict(user) if user else None


def get_user_by_id(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


def save_fashion_profile(user_id, gender, age, size, culture_style, dress_style, photo_path=""):
    conn = get_db()
    cur  = conn.execute(
        "INSERT INTO fashion_profiles (user_id,gender,age,size,culture_style,dress_style,photo_path) VALUES (?,?,?,?,?,?,?)",
        (user_id, gender, age, size, culture_style, dress_style, photo_path)
    )
    profile_id = cur.lastrowid
    conn.commit()
    conn.close()
    return profile_id


def save_recommendation(user_id, profile_id, request_type, input_data, ai_response):
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO ai_recommendations (user_id,profile_id,request_type,input_data,ai_response) VALUES (?,?,?,?,?)",
            (user_id, profile_id, request_type, str(input_data), ai_response)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Save error: {e}")


def get_recommendations_by_user(user_id, limit=20):
    conn    = get_db()
    records = conn.execute(
        "SELECT * FROM ai_recommendations WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in records]


def get_user_stats(user_id):
    conn  = get_db()
    total = conn.execute("SELECT COUNT(*) as cnt FROM ai_recommendations WHERE user_id=?", (user_id,)).fetchone()["cnt"]
    by_type = conn.execute(
        "SELECT request_type, COUNT(*) as cnt FROM ai_recommendations WHERE user_id=? GROUP BY request_type",
        (user_id,)
    ).fetchall()
    profiles = conn.execute("SELECT COUNT(*) as cnt FROM fashion_profiles WHERE user_id=?", (user_id,)).fetchone()["cnt"]
    conn.close()
    return {
        "total_recommendations": total,
        "profiles_created": profiles,
        "by_type": {r["request_type"]: r["cnt"] for r in by_type}
    }


def get_platform_stats():
    conn  = get_db()
    users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
    recs  = conn.execute("SELECT COUNT(*) as cnt FROM ai_recommendations").fetchone()["cnt"]
    profs = conn.execute("SELECT COUNT(*) as cnt FROM fashion_profiles").fetchone()["cnt"]
    conn.close()
    return {"total_users": users, "total_recommendations": recs, "total_profiles": profs}


if __name__ == "__main__":
    print("🔧 Setting up database...")
    init_db()
    print("✅ Done! fashion_ai.db created.")