import os
import sqlite3
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    jsonify
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from werkzeug.utils import secure_filename
from openai import OpenAI
from dotenv import load_dotenv
import markdown

# .env load
load_dotenv()
import os
print("OPENROUTER_API_KEY =", os.getenv("OPENROUTER_API_KEY"))
# OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY")
)

print("APP STARTED SUCCESSFULLY")

app = Flask(__name__)
app.secret_key = "study_secret_key"
app.config["UPLOAD_FOLDER"] = "static/uploads"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
DB = "study.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        mobile TEXT,
        designation TEXT,
        photo TEXT,
        password TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        question TEXT,
        answer TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)
    conn.commit()
    conn.close()

init_db()

# AI function (OpenRouter)
def ask_ai(prompt):
    if not client:
        return "Error: OPENROUTER_API_KEY missing hai .env file me"

    try:
        completion = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("AI ERROR:", e)
        return f"Error: {str(e)}"

@app.route("/")
def home():
    return "VERSION-12345"

@app.route("/ask", methods=["POST"])
def ask():
    if "user_id" not in session:
        return jsonify({"error": "Login required"})

    question = request.json.get("question")
    if not question:
        return jsonify({"error": "Question is empty"})

    answer = ask_ai(f"""
Act as a professional university professor.

Topic: {question}

Generate response in MARKDOWN format.

# Introduction
# Detailed Explanation
# Real World Example
# Advantages
# Disadvantages
# Applications
# Interview Questions
# Conclusion

Use proper headings, bullet points and formatting.
""")

    if "Error:" in answer:
        return jsonify({
            "answer": answer,
            "points": "Error loading answer",
            "mcq": "Error loading MCQs"
        })

    points = ask_ai(f"Give 5 important bullet points:\n{answer}")
    mcq = ask_ai(f"Create 5 MCQs with answers:\n{answer}")

    answer = markdown.markdown(answer)
    points = markdown.markdown(points)
    mcq = markdown.markdown(mcq)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO questions (user_id, question, answer) VALUES (?, ?, ?)",
        (session["user_id"], question, answer)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "answer": answer,
        "points": points,
        "mcq": mcq
    })


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        designation = request.form["designation"]
        password = request.form["password"]
        photo = request.files["photo"]

        filename = secure_filename(photo.filename)
        photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        hashed = generate_password_hash(password)

        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        try:
            cur.execute("""
            INSERT INTO users (name, email, mobile, designation, photo, password)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (name, email, mobile, designation, filename, hashed))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Email already exists!"

        conn.close()
        return redirect("/login")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[6], password):
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect("/profile")
        else:
            return "Invalid Email or Password"

    return render_template("login.html")


@app.route("/profile")
def profile():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"],)
    )
    user = cur.fetchone()

    cur.execute(
        """
        SELECT question
        FROM questions
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 20
        """,
        (session["user_id"],)
    )
    history = cur.fetchall()

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        history=history
    )


@app.route("/history")
def history():
    if "user_id" not in session:
        return jsonify([])

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT question FROM questions WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (session["user_id"],)
    )
    data = cur.fetchall()
    conn.close()

    return jsonify([row[0] for row in data])

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]

        conn = sqlite3.connect(DB)
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE email=?",
            (email,)
        )

        user = cur.fetchone()
        conn.close()

        if user:
            return redirect(f"/reset-password/{user[0]}")

        return "Email not found"

    return render_template("forgot_password.html")

@app.route("/reset-password/<int:user_id>",
methods=["GET","POST"])
def reset_password(user_id):

    if request.method == "POST":

        password = request.form["password"]

        hashed = generate_password_hash(password)

        conn = sqlite3.connect(DB)
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE users
            SET password=?
            WHERE id=?
            """,
            (hashed, user_id)
        )

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template(
        "reset_password.html",
        user_id=user_id
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)