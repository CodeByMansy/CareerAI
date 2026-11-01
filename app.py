
from io import BytesIO
import json
import os
import re
import sqlite3
import time
import os

from flask import request, jsonify, session
from google import genai
from google.genai import types
from collections import Counter
from functools import wraps
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
)


# ==========================================
# CONFIGURATION
# ==========================================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.environ.get(
    "CAREERAI_SECRET_KEY",
    "careerai-development-secret-change-this"
)

DATABASE = os.path.join(app.root_path, "careerai.db")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

gemini_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)

CHATBOT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

# Number of attempts for temporary Gemini service errors.
GEMINI_MAX_ATTEMPTS = 3


# ==========================================
# DATABASE
# ==========================================

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db_connection()

    # USERS TABLE
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # JOB APPLICATION TRACKER TABLE
    connection.execute("""
        CREATE TABLE IF NOT EXISTS job_applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            job_title TEXT NOT NULL,
            location TEXT,
            job_link TEXT,
            application_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Applied',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    # CAREER PROFILE TABLE
    connection.execute("""
        CREATE TABLE IF NOT EXISTS career_profiles (
            user_id INTEGER PRIMARY KEY,
            phone TEXT DEFAULT '',
            location TEXT DEFAULT '',
            headline TEXT DEFAULT '',
            education TEXT DEFAULT '',
            graduation_year TEXT DEFAULT '',
            skills TEXT DEFAULT '',
            career_goal TEXT DEFAULT '',
            preferred_role TEXT DEFAULT '',
            experience TEXT DEFAULT '',
            projects TEXT DEFAULT '',
            linkedin TEXT DEFAULT '',
            github TEXT DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)
    connection.commit()
    connection.close()


# ==========================================
# AUTHENTICATION DECORATOR
# ==========================================

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash(
                "Please sign in to continue.",
                "error"
            )

            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


# ==========================================
# LOGIN
# ==========================================

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        if not email or not password:
            flash(
                "Please enter your email and password.",
                "error"
            )

            return redirect(url_for("login"))

        connection = get_db_connection()

        user = connection.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        connection.close()

        if user and check_password_hash(
            user["password_hash"],
            password
        ):

            session.clear()

            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["user_email"] = user["email"]

            flash(
                "Welcome back!",
                "success"
            )

            return redirect(url_for("dashboard"))

        flash(
            "Invalid email or password.",
            "error"
        )

    return render_template("login.html")


# ==========================================
# CAREER PROFILE HELPERS
# ==========================================

PROFILE_FIELDS = [
    "phone",
    "location",
    "headline",
    "education",
    "graduation_year",
    "skills",
    "career_goal",
    "preferred_role",
    "experience",
    "projects",
    "linkedin",
    "github",
]


def calculate_profile_completion(profile):
    """
    Calculate profile completion percentage.

    Each of the 12 profile fields contributes equally.
    """

    if not profile:
        return 0

    completed_fields = sum(
        1
        for field in PROFILE_FIELDS
        if str(profile[field] or "").strip()
    )

    return round(
        completed_fields / len(PROFILE_FIELDS) * 100
    )
# ==========================================
# REGISTER
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if "user_id" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        full_name = request.form.get(
            "fullName", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get(
            "password", ""
        )

        agree = request.form.get("agree")

        if not full_name or not email or not password:
            flash(
                "Please complete all required fields.",
                "error"
            )

            return redirect(url_for("register"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "error"
            )

            return redirect(url_for("register"))

        if not agree:
            flash(
                "Please accept the terms to create an account.",
                "error"
            )

            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        connection = get_db_connection()

        try:

            connection.execute(
                """
                INSERT INTO users (
                    full_name,
                    email,
                    password_hash
                )
                VALUES (?, ?, ?)
                """,
                (
                    full_name,
                    email,
                    password_hash
                )
            )

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()

            flash(
                "An account with this email already exists.",
                "error"
            )

            return redirect(url_for("register"))

        connection.close()

        flash(
            "Account created successfully. Please sign in.",
            "success"
        )

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
  # ==========================================
# DASHBOARD WITH DYNAMIC STATISTICS
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():

    user_id = session["user_id"]

    connection = get_db_connection()

    # --------------------------------------
    # Total job applications
    # --------------------------------------

    application_count = connection.execute(
        """
        SELECT COUNT(*)
        FROM job_applications
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()[0]

    # --------------------------------------
    # Total interview preparation sessions
    # --------------------------------------

    interview_count = 0

    interview_table = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'interview_sessions'
        """
    ).fetchone()

    if interview_table:

        interview_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM interview_sessions
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()[0]

    connection.close()

    # --------------------------------------
    # Dashboard statistics
    # --------------------------------------

    stats = {
        "resume_score": "--",
        "job_matches": "--",
        "applications": application_count,
        "interview_prep": interview_count,
    }

    return render_template(
        "dashboard.html",
        stats=stats
    )


# ==========================================
# RESUME ANALYZER
# ==========================================

@app.route("/resume-analyzer", methods=["GET", "POST"])
@login_required
def resume_analyzer():

    result = None

    if request.method == "POST":

        resume_file = request.files.get("resume")

        job_description = request.form.get(
            "job_description", ""
        ).strip()

        if not resume_file or not resume_file.filename:

            flash(
                "Please upload your resume PDF.",
                "error"
            )

            return redirect(url_for("resume_analyzer"))

        if not resume_file.filename.lower().endswith(".pdf"):

            flash(
                "Only PDF resumes are supported.",
                "error"
            )

            return redirect(url_for("resume_analyzer"))

        if not job_description:

            flash(
                "Please enter the job description.",
                "error"
            )

            return redirect(url_for("resume_analyzer"))

        try:

            reader = PdfReader(resume_file)

            if reader.is_encrypted:

                flash(
                    "Please upload an unlocked PDF resume.",
                    "error"
                )

                return redirect(url_for("resume_analyzer"))

            resume_text = " ".join(
                page.extract_text() or ""
                for page in reader.pages
            )

            if not resume_text.strip():

                flash(
                    "Could not extract text. "
                    "Please upload a text-based PDF.",
                    "error"
                )

                return redirect(url_for("resume_analyzer"))

            def extract_keywords(text):

                words = re.findall(
                    r"\b[a-zA-Z][a-zA-Z+#.]{1,}\b",
                    text.lower()
                )

                stop_words = {
                    "the", "and", "for", "with", "you",
                    "your", "are", "this", "that", "from",
                    "have", "has", "will", "our", "their",
                    "they", "can", "who", "what", "when",
                    "where", "how", "into", "about", "such",
                    "than", "then", "also", "all", "any",
                    "job", "role", "work", "team",
                    "experience", "years", "year",
                    "required", "preferred"
                }

                return {
                    word for word in words
                    if word not in stop_words
                }

            resume_keywords = extract_keywords(resume_text)

            job_keywords = extract_keywords(
                job_description
            )

            matching_keywords = sorted(
                resume_keywords.intersection(job_keywords)
            )

            missing_keywords = sorted(
                job_keywords.difference(resume_keywords)
            )

            if job_keywords:

                score = round(
                    len(matching_keywords)
                    / len(job_keywords)
                    * 100
                )

            else:
                score = 0

            result = {
                "score": score,
                "matching_keywords": matching_keywords[:30],
                "missing_keywords": missing_keywords[:30],
                "resume_text": resume_text[:5000]
            }

        except Exception:

            app.logger.exception(
                "Resume analysis failed"
            )

            flash(
                "Unable to analyze this PDF. "
                "Please try another file.",
                "error"
            )

            return redirect(url_for("resume_analyzer"))

    return render_template(
        "resume_analyzer.html",
        result=result
    )


# ==========================================
# RESUME BUILDER
# ==========================================

@app.route("/resume-builder", methods=["GET", "POST"])
@login_required
def resume_builder():

    resume = None

    if request.method == "POST":

        resume = {
            "full_name": request.form.get(
                "full_name", ""
            ).strip(),

            "email": request.form.get(
                "email", ""
            ).strip(),

            "phone": request.form.get(
                "phone", ""
            ).strip(),

            "location": request.form.get(
                "location", ""
            ).strip(),

            "summary": request.form.get(
                "summary", ""
            ).strip(),

            "degree": request.form.get(
                "degree", ""
            ).strip(),

            "college": request.form.get(
                "college", ""
            ).strip(),

            "graduation_year": request.form.get(
                "graduation_year", ""
            ).strip(),

            "skills": request.form.get(
                "skills", ""
            ).strip(),

            "projects": request.form.get(
                "projects", ""
            ).strip(),

            "experience": request.form.get(
                "experience", ""
            ).strip(),
        }

        action = request.form.get(
            "action", "preview"
        )

        if action == "download_pdf":
            return generate_resume_pdf(resume)

    return render_template(
        "resume_builder.html",
        resume=resume
    )


def generate_resume_pdf(resume):
    """Generate a professional ATS-friendly resume PDF."""

    buffer = BytesIO()

    navy = colors.HexColor("#17365D")
    blue = colors.HexColor("#2878B5")
    dark_text = colors.HexColor("#222222")
    muted_text = colors.HexColor("#5B6573")
    light_line = colors.HexColor("#D9E2F0")

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"{resume.get('full_name', 'Resume')} - Resume",
        author=resume.get("full_name", ""),
    )

    styles = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "ResumeName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=27,
        alignment=TA_CENTER,
        textColor=navy,
        spaceAfter=5,
    )

    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        alignment=TA_CENTER,
        textColor=muted_text,
        spaceAfter=10,
    )

    section_style = ParagraphStyle(
        "ResumeSection",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        textColor=navy,
        spaceBefore=9,
        spaceAfter=5,
    )

    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=14,
        textColor=dark_text,
        spaceAfter=4,
    )

    story = []

    full_name = escape(
        resume.get("full_name", "").strip()
    )

    if full_name:
        story.append(
            Paragraph(full_name, name_style)
        )

    contact_parts = [
        resume.get("email", "").strip(),
        resume.get("phone", "").strip(),
        resume.get("location", "").strip(),
    ]

    contact_parts = [
        escape(item)
        for item in contact_parts
        if item
    ]

    if contact_parts:

        story.append(
            Paragraph(
                " &nbsp; | &nbsp; ".join(contact_parts),
                contact_style
            )
        )

    story.append(
        HRFlowable(
            width="100%",
            thickness=1.2,
            color=blue,
            spaceBefore=2,
            spaceAfter=8,
        )
    )

    def add_section(title, content):

        if not content or not content.strip():
            return

        story.append(
            Paragraph(
                escape(title.upper()),
                section_style
            )
        )

        story.append(
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=light_line,
                spaceAfter=5,
            )
        )

        for line in content.splitlines():

            line = line.strip()

            if not line:
                continue

            safe_line = escape(line)

            if line.startswith(("•", "-", "*")):

                safe_line = (
                    "• "
                    + escape(
                        line.lstrip("•-* ").strip()
                    )
                )

                story.append(
                    Paragraph(
                        safe_line,
                        ParagraphStyle(
                            "ResumeBullet",
                            parent=body_style,
                            leftIndent=10,
                            firstLineIndent=-7,
                            spaceAfter=3,
                        )
                    )
                )

            else:

                story.append(
                    Paragraph(
                        safe_line,
                        body_style
                    )
                )

        story.append(
            Spacer(1, 3)
        )

    add_section(
        "Professional Summary",
        resume.get("summary", "")
    )

    education = "\n".join(
        value
        for value in [
            resume.get("degree", ""),
            resume.get("college", ""),
            resume.get("graduation_year", ""),
        ]
        if value
    )

    add_section(
        "Education",
        education
    )

    add_section(
        "Technical Skills",
        resume.get("skills", "")
    )

    add_section(
        "Projects",
        resume.get("projects", "")
    )

    add_section(
        "Experience",
        resume.get("experience", "")
    )

    document.build(story)

    buffer.seek(0)

    safe_name = resume.get(
        "full_name", "resume"
    ).strip()

    safe_name = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        safe_name
    )

    filename = f"{safe_name}_Resume.pdf"

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ==========================================
# GEMINI API HELPERS
# ==========================================

def call_gemini(prompt):
    """
    Call Gemini with retries for temporary service errors.

    Retries are limited to avoid repeatedly sending requests
    when the API is unavailable.
    """

    if not gemini_client:

        raise RuntimeError(
            "Gemini API key is missing. "
            "Please configure GEMINI_API_KEY in your .env file."
        )

    last_error = None

    for attempt in range(GEMINI_MAX_ATTEMPTS):

        try:

            response = gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                },
            )

            response_text = response.text

            if not response_text:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return response_text

        except Exception as error:

            last_error = error

            error_text = str(error).lower()

            is_temporary_error = (
                "503" in error_text
                or "unavailable" in error_text
                or "429" in error_text
                or "resource_exhausted" in error_text
                or "high demand" in error_text
            )

            # Do not retry errors such as invalid API keys
            # or unavailable model names.
            if not is_temporary_error:
                raise

            # No need to wait after the final attempt.
            if attempt == GEMINI_MAX_ATTEMPTS - 1:
                break

            # Exponential backoff: 2 seconds, then 4 seconds.
            wait_seconds = 2 ** (attempt + 1)

            app.logger.warning(
                "Gemini temporarily unavailable. "
                "Retrying in %s seconds. Attempt %s/%s.",
                wait_seconds,
                attempt + 1,
                GEMINI_MAX_ATTEMPTS,
            )

            time.sleep(wait_seconds)

    raise RuntimeError(
        "Gemini AI is temporarily busy or unavailable. "
        "Please try again in a few minutes."
    ) from last_error


def parse_gemini_json(response_text):
    """Parse and validate JSON returned by Gemini."""

    try:

        parsed = json.loads(response_text)

    except json.JSONDecodeError as error:

        app.logger.error(
            "Gemini returned invalid JSON: %s",
            response_text
        )

        raise RuntimeError(
            "Gemini returned an invalid response. "
            "Please try again."
        ) from error

    if not isinstance(parsed, dict):

        raise RuntimeError(
            "Gemini returned an unexpected response format."
        )

    return parsed


# ==========================================
# GEMINI AI JOB RECOMMENDATIONS
# ==========================================

def generate_ai_job_recommendations(
    profile_text,
    preferred_role="",
    location=""
):
    """
    Generate AI-based job role recommendations.

    These are AI-generated suggestions, not verified
    live job vacancies.
    """

    prompt = f"""
You are CareerAI, an AI career recommendation assistant.

Analyze the candidate profile and recommend suitable job roles.

Candidate profile:
{profile_text[:6000]}

Preferred job role:
{preferred_role or "Recommend suitable roles based on the profile"}

Preferred location:
{location or "Any location"}

Generate 5 relevant job recommendations.

For every recommendation, provide:
- title: job role title
- company: use "AI Recommendation"
- location: use the provided location or "Not specified"
- type: "Recommended Role"
- description: realistic description of the role
- score: integer from 0 to 100 representing profile compatibility
- matching_skills: skills supported by the candidate profile
- missing_skills: important skills not evident in the profile
- explanation: short explanation of why this role fits
- learning_suggestions: list of useful skills or topics to learn

Rules:
- These are AI-generated role suggestions, not live vacancies.
- Do not invent company names, recruiters, or application links.
- Do not invent candidate qualifications.
- Use realistic compatibility scores.
- Use the candidate's actual skills and experience.
- Return only valid JSON.

Required JSON structure:
{{
  "recommendations": [
    {{
      "title": "Python Developer",
      "company": "AI Recommendation",
      "location": "Not specified",
      "type": "Recommended Role",
      "description": "Develop backend applications...",
      "score": 80,
      "matching_skills": ["Python", "Flask"],
      "missing_skills": ["Docker"],
      "explanation": "Your Python and Flask skills are relevant...",
      "learning_suggestions": ["Docker", "Cloud deployment"]
    }}
  ]
}}
"""

    response_text = call_gemini(prompt)

    parsed = parse_gemini_json(response_text)

    recommendations = parsed.get(
        "recommendations",
        []
    )

    if not isinstance(recommendations, list):

        raise RuntimeError(
            "Gemini returned an unexpected recommendation format."
        )

    return recommendations


# ==========================================
# GEMINI CUSTOM JOB DESCRIPTION ANALYSIS
# ==========================================

def analyze_custom_job(
    profile_text,
    job_description,
    preferred_role=""
):
    """
    Analyze the candidate against the exact job description.
    """

    prompt = f"""
You are CareerAI, a resume and job compatibility assistant.

Analyze how well the candidate matches the supplied job description.

Candidate profile:
{profile_text[:6000]}

Preferred role:
{preferred_role or "Not specified"}

Job description:
{job_description[:6000]}

Return a single JSON object with:
- score: integer from 0 to 100
- matching_skills: list of skills supported by the candidate
- missing_skills: list of important skills not evident in the profile
- explanation: concise explanation of the match

Rules:
- Analyze the supplied job description directly.
- Do not generate a different job.
- Do not invent candidate skills or qualifications.
- Be realistic with the score.
- Return only valid JSON.

Required structure:
{{
  "score": 75,
  "matching_skills": ["Python", "Flask"],
  "missing_skills": ["Docker"],
  "explanation": "The candidate has relevant Python experience..."
}}
"""

    response_text = call_gemini(prompt)

    parsed = parse_gemini_json(response_text)

    try:

        score = int(
            parsed.get("score", 0)
        )

    except (ValueError, TypeError):

        score = 0

    return {
        "score": max(
            0,
            min(100, score)
        ),

        "matching_skills": parsed.get(
            "matching_skills", []
        ),

        "missing_skills": parsed.get(
            "missing_skills", []
        ),

        "explanation": parsed.get(
            "explanation", ""
        ),
    }



# ==========================================
# CAREERAI JOB MATCHING FEATURE
# ==========================================

JOB_DATABASE = [
    {
        "title": "Python Developer",
        "company": "Tech Solutions",
        "location": "Pune, India",
        "type": "Full-time",
        "description": (
            "Develop backend applications using Python, Flask, "
            "REST APIs, SQL, Git, and database management."
        ),
        "skills": [
            "python", "flask", "rest api", "sql",
            "git", "database"
        ],
    },
    {
        "title": "Flutter Developer",
        "company": "Mobile Innovations",
        "location": "Mumbai, India",
        "type": "Full-time",
        "description": (
            "Build cross-platform mobile applications using Flutter, "
            "Dart, Firebase, REST APIs, and Git."
        ),
        "skills": [
            "flutter", "dart", "firebase",
            "rest api", "git"
        ],
    },
    {
        "title": "Machine Learning Intern",
        "company": "AI Research Labs",
        "location": "Remote",
        "type": "Internship",
        "description": (
            "Work on machine learning models using Python, "
            "TensorFlow, pandas, NumPy, and data analysis."
        ),
        "skills": [
            "python", "machine learning", "tensorflow",
            "pandas", "numpy", "data analysis"
        ],
    },
    {
        "title": "Full Stack Developer",
        "company": "WebCraft Technologies",
        "location": "Bengaluru, India",
        "type": "Full-time",
        "description": (
            "Develop web applications using HTML, CSS, JavaScript, "
            "Python, Flask, SQL, and REST APIs."
        ),
        "skills": [
            "html", "css", "javascript",
            "python", "flask", "sql", "rest api"
        ],
    },
    {
        "title": "Data Analyst",
        "company": "Insight Analytics",
        "location": "Remote",
        "type": "Full-time",
        "description": (
            "Analyze datasets using Python, SQL, Excel, "
            "pandas, NumPy, and data visualization."
        ),
        "skills": [
            "python", "sql", "excel",
            "pandas", "numpy", "data visualization"
        ],
    },
]


# Skills vocabulary used to identify skills in custom job descriptions.
ALL_JOB_SKILLS = sorted(
    {
        skill
        for job in JOB_DATABASE
        for skill in job["skills"]
    },
    key=len,
    reverse=True,
)


def normalize_text(text):
    """Normalize text for case-insensitive skill matching."""
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def contains_skill(text, skill):
    """
    Match a skill as a complete phrase.
    Avoid matching 'sql' inside another unrelated word.
    """
    text = normalize_text(text)
    skill = normalize_text(skill)

    pattern = r"(?<![a-zA-Z0-9+#.])" + re.escape(skill) + \
              r"(?![a-zA-Z0-9+#.])"

    return re.search(pattern, text) is not None


def calculate_job_match(profile_text, job):
    """Calculate a keyword-based match score for a job."""

    profile_text = normalize_text(profile_text)

    job_skills = job.get("skills", [])

    matching_skills = [
        skill for skill in job_skills
        if contains_skill(profile_text, skill)
    ]

    missing_skills = [
        skill for skill in job_skills
        if skill not in matching_skills
    ]

    if job_skills:
        score = round(
            len(matching_skills) / len(job_skills) * 100
        )
    else:
        score = None

    return {
        "score": score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
    }


@app.route("/job-matching", methods=["GET", "POST"])
@login_required
def job_matching():

    results = []
    selected_job = None
    analysis = None

    form_data = {
        "role": "",
        "skills": "",
        "job_description": "",
    }

    if request.method == "POST":

        form_data["role"] = request.form.get(
            "role", ""
        ).strip()

        form_data["skills"] = request.form.get(
            "skills", ""
        ).strip()

        form_data["job_description"] = request.form.get(
            "job_description", ""
        ).strip()

        resume_file = request.files.get("resume")
        resume_text = ""

        # ----------------------------------
        # Extract uploaded PDF resume
        # ----------------------------------

        if resume_file and resume_file.filename:

            if not resume_file.filename.lower().endswith(".pdf"):
                flash(
                    "Please upload a PDF resume.",
                    "error"
                )

                return redirect(url_for("job_matching"))

            try:
                reader = PdfReader(resume_file)

                if reader.is_encrypted:
                    flash(
                        "Please upload an unlocked PDF resume.",
                        "error"
                    )

                    return redirect(url_for("job_matching"))

                resume_text = " ".join(
                    page.extract_text() or ""
                    for page in reader.pages
                )

                if not resume_text.strip():
                    flash(
                        "No readable text was found in the PDF. "
                        "Please upload a text-based resume.",
                        "error"
                    )

                    return redirect(url_for("job_matching"))

            except Exception:
                app.logger.exception(
                    "Job matching PDF extraction failed"
                )

                flash(
                    "Unable to read this PDF resume.",
                    "error"
                )

                return redirect(url_for("job_matching"))

        # ----------------------------------
        # Build user profile text
        # ----------------------------------

        profile_text = " ".join([
            form_data["role"],
            form_data["skills"],
            resume_text,
        ])

        if not profile_text.strip():
            flash(
                "Please enter your skills or upload a resume.",
                "error"
            )

            return render_template(
                "job_matching.html",
                results=results,
                selected_job=selected_job,
                analysis=analysis,
                form_data=form_data,
            )

        # ----------------------------------
        # Custom job description analysis
        # ----------------------------------

        if form_data["job_description"]:

            job_description = form_data["job_description"]

            detected_skills = [
                skill for skill in ALL_JOB_SKILLS
                if contains_skill(job_description, skill)
            ]

            selected_job = {
                "title": form_data["role"] or "Selected Job",
                "company": "Custom Job Description",
                "location": "Not specified",
                "type": "Custom",
                "description": job_description,
                "skills": detected_skills,
            }

            if detected_skills:

                analysis = calculate_job_match(
                    profile_text,
                    selected_job
                )

            else:

                analysis = {
                    "score": None,
                    "matching_skills": [],
                    "missing_skills": [],
                }

                flash(
                    "No supported skills were detected in the "
                    "job description. Try including skills such "
                    "as Python, SQL, Flask, or Flutter.",
                    "warning"
                )

        # ----------------------------------
        # Compare against sample job listings
        # ----------------------------------

        else:

            for job in JOB_DATABASE:

                match = calculate_job_match(
                    profile_text,
                    job
                )

                results.append({
                    **job,
                    **match,
                })

            results.sort(
                key=lambda item: item["score"],
                reverse=True
            )

    return render_template(
        "job_matching.html",
        results=results,
        selected_job=selected_job,
        analysis=analysis,
        form_data=form_data,
    )

# ==========================================
# INTERVIEW PREPARATION
# ==========================================

INTERVIEW_QUESTION_BANK = {
    "Python Developer": {
        "technical": [
            {
                "question": "What is the difference between a list and a tuple in Python?",
                "answer": (
                    "A list is mutable, which means its elements can be changed "
                    "after creation. A tuple is immutable. Lists are useful for "
                    "collections that change, while tuples are useful for fixed data."
                )
            },
            {
                "question": "What are Python decorators?",
                "answer": (
                    "A decorator is a function that wraps another function to "
                    "modify or extend its behavior without changing the original "
                    "function. Decorators are commonly used for logging, "
                    "authentication, and timing."
                )
            },
            {
                "question": "How do you handle exceptions in Python?",
                "answer": (
                    "Python uses try and except blocks to handle exceptions. "
                    "The finally block can be used for cleanup operations. "
                    "It is good practice to catch specific exceptions instead "
                    "of using a broad except block."
                )
            },
            {
                "question": "What is the difference between shallow copy and deep copy?",
                "answer": (
                    "A shallow copy creates a new outer object but retains "
                    "references to nested objects. A deep copy recursively "
                    "copies nested objects. Python provides copy() and "
                    "deepcopy() in the copy module."
                )
            },
            {
                "question": "How do you connect a Flask application to SQLite?",
                "answer": (
                    "Python provides the sqlite3 module. A Flask application "
                    "can create a connection, execute parameterized SQL "
                    "queries, commit changes, and close the connection."
                )
            },
        ],

        "hr": [
            {
                "question": "Tell me about yourself.",
                "answer": (
                    "Give a short introduction covering your education, "
                    "technical skills, relevant projects, and career goals. "
                    "Connect your experience to the Python Developer role."
                )
            },
            {
                "question": "Describe a challenging programming problem you solved.",
                "answer": (
                    "Use the STAR method: Situation, Task, Action, and Result. "
                    "Explain the problem, your responsibility, the steps you "
                    "took, and the outcome."
                )
            },
            {
                "question": "How do you learn a new technology?",
                "answer": (
                    "Explain how you review documentation, build a small "
                    "example, apply the technology in a project, test it, "
                    "and record what you learn."
                )
            },
        ],
    },

    "Frontend Developer": {
        "technical": [
            {
                "question": "What is the difference between HTML, CSS, and JavaScript?",
                "answer": (
                    "HTML defines the structure and content of a webpage. "
                    "CSS controls its presentation and layout. JavaScript "
                    "adds behavior and interactivity."
                )
            },
            {
                "question": "What is the CSS box model?",
                "answer": (
                    "The CSS box model consists of content, padding, border, "
                    "and margin. These properties determine the space occupied "
                    "by an element."
                )
            },
            {
                "question": "What is the difference between let, const, and var?",
                "answer": (
                    "var is function-scoped and can be redeclared. let is "
                    "block-scoped and can be reassigned. const is block-scoped "
                    "and cannot be reassigned."
                )
            },
            {
                "question": "How do you make a website responsive?",
                "answer": (
                    "Use flexible layouts, CSS Grid, Flexbox, relative sizing, "
                    "responsive images, and media queries. Test the website "
                    "on different screen sizes."
                )
            },
            {
                "question": "What is the DOM?",
                "answer": (
                    "The Document Object Model represents a webpage as a "
                    "tree of objects. JavaScript can use the DOM to read "
                    "and modify page content and styles."
                )
            },
        ],

        "hr": [
            {
                "question": "Why are you interested in frontend development?",
                "answer": (
                    "Discuss your interest in designing user-friendly "
                    "interfaces, visual problem solving, and building "
                    "responsive web experiences."
                )
            },
            {
                "question": "How do you respond to design feedback?",
                "answer": (
                    "Explain that you understand the feedback, evaluate "
                    "it against usability and requirements, make changes, "
                    "and validate the result."
                )
            },
            {
                "question": "Describe a project where you improved a user interface.",
                "answer": (
                    "Explain the original problem, the changes you made, "
                    "the tools you used, and how you evaluated the result."
                )
            },
        ],
    },

    "Data Analyst": {
        "technical": [
            {
                "question": "What is the difference between mean, median, and mode?",
                "answer": (
                    "Mean is the arithmetic average. Median is the middle "
                    "value after sorting. Mode is the most frequently "
                    "occurring value."
                )
            },
            {
                "question": "How would you handle missing data?",
                "answer": (
                    "First investigate why data is missing. Depending on "
                    "the situation, missing values may be removed, imputed, "
                    "or retained as a separate signal. The decision should "
                    "be documented."
                )
            },
            {
                "question": "What is the difference between INNER JOIN and LEFT JOIN?",
                "answer": (
                    "INNER JOIN returns rows that match in both tables. "
                    "LEFT JOIN returns every row from the left table and "
                    "matching rows from the right table. Unmatched right-side "
                    "values become NULL."
                )
            },
            {
                "question": "What is data visualization?",
                "answer": (
                    "Data visualization represents information graphically "
                    "to make patterns, comparisons, trends, and outliers "
                    "easier to understand."
                )
            },
            {
                "question": "How do you validate your analysis?",
                "answer": (
                    "Check data quality, missing values, duplicates, "
                    "assumptions, calculations, and totals. Reproduce "
                    "important results and compare them with known benchmarks."
                )
            },
        ],

        "hr": [
            {
                "question": "How would you explain a complex data insight to a non-technical person?",
                "answer": (
                    "Start with the business question, state the key finding "
                    "in plain language, support it with a simple metric or "
                    "visual, and explain the next step."
                )
            },
            {
                "question": "Tell me about a time you used data to solve a problem.",
                "answer": (
                    "Use the STAR method. Explain the data, the question, "
                    "your analysis, the result, and how the result influenced "
                    "a decision."
                )
            },
            {
                "question": "How do you prioritize analysis requests?",
                "answer": (
                    "Consider business impact, urgency, effort, data "
                    "availability, and dependencies. Clarify expectations "
                    "and communicate trade-offs."
                )
            },
        ],
    },

    "Machine Learning Engineer": {
        "technical": [
            {
                "question": "What is the difference between supervised and unsupervised learning?",
                "answer": (
                    "Supervised learning uses labeled data to learn a "
                    "mapping from inputs to targets. Unsupervised learning "
                    "uses unlabeled data to discover patterns or structures."
                )
            },
            {
                "question": "Why do we split data into training and testing sets?",
                "answer": (
                    "The training set is used to fit the model. The test "
                    "set estimates how well the model performs on unseen data. "
                    "A validation set can be used for model selection."
                )
            },
            {
                "question": "What is overfitting?",
                "answer": (
                    "Overfitting occurs when a model learns training-specific "
                    "noise and performs poorly on new data. It can be reduced "
                    "using regularization, simpler models, more data, "
                    "cross-validation, or early stopping."
                )
            },
            {
                "question": "What is a confusion matrix?",
                "answer": (
                    "A confusion matrix compares predicted and actual classes. "
                    "For binary classification, it contains true positives, "
                    "false positives, true negatives, and false negatives."
                )
            },
            {
                "question": "What is the difference between precision and recall?",
                "answer": (
                    "Precision measures how many predicted positives are "
                    "correct. Recall measures how many actual positives "
                    "the model identifies. The appropriate balance depends "
                    "on the problem."
                )
            },
        ],

        "hr": [
            {
                "question": "Explain an ML project you worked on.",
                "answer": (
                    "Discuss the problem, dataset, preprocessing, model "
                    "selection, evaluation metrics, results, limitations, "
                    "and your personal contribution."
                )
            },
            {
                "question": "How do you choose an evaluation metric?",
                "answer": (
                    "Choose based on the problem and the cost of errors. "
                    "For imbalanced classification, accuracy alone may "
                    "be misleading. Precision, recall, F1, or AUC may "
                    "be more useful."
                )
            },
            {
                "question": "What would you do if a model performs poorly in production?",
                "answer": (
                    "Investigate data drift, concept drift, preprocessing "
                    "differences, data quality, and training-serving skew. "
                    "Monitor performance and retrain or adjust when justified."
                )
            },
        ],
    },

    "Full Stack Developer": {
        "technical": [
            {
                "question": "What happens when a browser sends an HTTP request?",
                "answer": (
                    "The browser sends a request to the server. The server "
                    "routes and processes it, may access a database, and "
                    "returns an HTTP response containing a status code, "
                    "headers, and possibly a response body."
                )
            },
            {
                "question": "What is a REST API?",
                "answer": (
                    "A REST-style API exposes resources through URLs and "
                    "uses HTTP methods such as GET, POST, PUT, PATCH, "
                    "and DELETE. It commonly exchanges JSON data."
                )
            },
            {
                "question": "How should passwords be stored?",
                "answer": (
                    "Passwords should never be stored in plaintext. Store "
                    "salted password hashes generated by a suitable "
                    "password-hashing algorithm such as Werkzeug's "
                    "secure password hash functions."
                )
            },
            {
                "question": "How do you prevent SQL injection?",
                "answer": (
                    "Use parameterized SQL queries instead of concatenating "
                    "user input into SQL statements. Validate input and "
                    "use least-privilege database access."
                )
            },
            {
                "question": "What is the purpose of sessions?",
                "answer": (
                    "Sessions maintain user-specific state across requests, "
                    "such as a logged-in user ID. Session cookies should "
                    "be protected using secure settings and a strong secret key."
                )
            },
        ],

        "hr": [
            {
                "question": "How do you manage frontend and backend tasks?",
                "answer": (
                    "Break requirements into UI components and API contracts, "
                    "identify dependencies, test each layer, and communicate "
                    "progress."
                )
            },
            {
                "question": "Describe a bug that required frontend and backend investigation.",
                "answer": (
                    "Explain how you reproduced the issue, traced the data "
                    "flow, isolated the cause, fixed it, and prevented "
                    "regression."
                )
            },
            {
                "question": "How do you ensure your application is maintainable?",
                "answer": (
                    "Use clear module boundaries, readable naming, reusable "
                    "components, validation, tests, documentation, version "
                    "control, and consistent error handling."
                )
            },
        ],
    },
}


DEFAULT_INTERVIEW_BANK = {
    "technical": [
        {
            "question": "Explain a technical concept important for your target role.",
            "answer": (
                "Define the concept clearly, explain why it matters, "
                "and provide a practical example relevant to the role."
            )
        },
        {
            "question": "Describe a project where you applied your technical skills.",
            "answer": (
                "Explain the goal, your approach, your contribution, "
                "the main challenge, and the outcome."
            )
        },
        {
            "question": "How do you debug an unfamiliar issue?",
            "answer": (
                "Reproduce the issue, inspect logs and inputs, narrow "
                "the cause, test a focused fix, and add a regression "
                "check when possible."
            )
        },
        {
            "question": "How do you keep your technical knowledge up to date?",
            "answer": (
                "Use official documentation, trusted technical resources, "
                "small experiments, and practical project work."
            )
        },
    ],

    "hr": [
        {
            "question": "Tell me about yourself.",
            "answer": (
                "Give a brief introduction covering your education, "
                "relevant skills, one project or achievement, and "
                "the role you are seeking."
            )
        },
        {
            "question": "What is one strength you would bring to this role?",
            "answer": (
                "Choose a role-relevant strength and support it with "
                "a specific example rather than only naming the quality."
            )
        },
        {
            "question": "Describe a time you worked through a difficult challenge.",
            "answer": (
                "Use the STAR method: Situation, Task, Action, and Result. "
                "Emphasize your actions and what you learned."
            )
        },
        {
            "question": "Why should we hire you?",
            "answer": (
                "Connect your relevant skills, project experience, "
                "willingness to learn, and understanding of the role "
                "to the employer's needs."
            )
        },
    ],
}


def select_interview_questions(role, interview_type, difficulty):
    """
    Select questions from the local question bank.
    This feature does not require an external AI API.
    """

    role_bank = INTERVIEW_QUESTION_BANK.get(
        role,
        DEFAULT_INTERVIEW_BANK
    )

    if interview_type == "technical":

        questions = list(
            role_bank.get("technical", [])
        )

    elif interview_type == "hr":

        questions = list(
            role_bank.get("hr", [])
        )

    else:

        questions = (
            list(role_bank.get("technical", []))
            + list(role_bank.get("hr", []))
        )

    if not questions:

        questions = (
            list(DEFAULT_INTERVIEW_BANK["technical"])
            + list(DEFAULT_INTERVIEW_BANK["hr"])
        )

    questions.insert(
        0,
        {
            "question": (
                f"Why are you interested in the {role} role, "
                "and what makes your background relevant?"
            ),

            "answer": (
                f"Connect your interests and experience to the "
                f"{role} responsibilities. Mention relevant coursework, "
                "projects, tools, and what you hope to contribute. "
                "Use specific examples and avoid claiming skills "
                "you have not practiced."
            )
        }
    )

    if difficulty == "Advanced":

        questions.append(
            {
                "question": (
                    f"What trade-offs would you consider when "
                    f"designing a solution as a {role}?"
                ),

                "answer": (
                    "Explain the requirements first, then compare "
                    "alternatives using performance, maintainability, "
                    "reliability, security, cost, and complexity. "
                    "State the assumptions behind your choice."
                )
            }
        )

    elif difficulty == "Beginner":

        questions.append(
            {
                "question": (
                    f"What fundamental skills should a beginner "
                    f"develop for a {role} position?"
                ),

                "answer": (
                    "Identify the core language or tools, problem-solving "
                    "basics, debugging, version control, and a small "
                    "portfolio project. Explain how you would practice them."
                )
            }
        )

    else:

        questions.append(
            {
                "question": (
                    f"How would you approach a real-world task "
                    f"assigned to a {role}?"
                ),

                "answer": (
                    "Clarify the requirement and success criteria, "
                    "break the task into steps, choose suitable tools, "
                    "implement incrementally, test, and communicate progress."
                )
            }
        )

    # Remove duplicate questions and limit the set to 8.
    unique_questions = []
    seen_questions = set()

    for item in questions:

        normalized_question = (
            item["question"].strip().lower()
        )

        if normalized_question not in seen_questions:

            unique_questions.append(item)

            seen_questions.add(
                normalized_question
            )

        if len(unique_questions) == 8:
            break

    return unique_questions


@app.route(
    "/interview-prep",
    methods=["GET", "POST"]
)
@login_required
def interview_prep():

    questions = []

    session_info = None

    roles = sorted(
        INTERVIEW_QUESTION_BANK.keys()
    )

    selected_role = "Python Developer"

    selected_difficulty = "Intermediate"

    selected_type = "mixed"

    if request.method == "POST":

        selected_role = request.form.get(
            "role",
            "Python Developer"
        ).strip()

        selected_difficulty = request.form.get(
            "difficulty",
            "Intermediate"
        ).strip()

        selected_type = request.form.get(
            "interview_type",
            "mixed"
        ).strip()

        allowed_roles = set(
            INTERVIEW_QUESTION_BANK.keys()
        )

        allowed_difficulties = {
            "Beginner",
            "Intermediate",
            "Advanced",
        }

        allowed_types = {
            "technical",
            "hr",
            "mixed",
        }

        if selected_role not in allowed_roles:

            flash(
                "Please select a supported job role.",
                "error"
            )

            return redirect(
                url_for("interview_prep")
            )

        if selected_difficulty not in allowed_difficulties:

            selected_difficulty = "Intermediate"

        if selected_type not in allowed_types:

            selected_type = "mixed"

        questions = select_interview_questions(
            selected_role,
            selected_type,
            selected_difficulty,
        )

        connection = get_db_connection()

        connection.execute("""
            CREATE TABLE IF NOT EXISTS interview_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                interview_type TEXT NOT NULL,
                question_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor = connection.execute(
            """
            INSERT INTO interview_sessions (
                user_id,
                role,
                difficulty,
                interview_type,
                question_count
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                selected_role,
                selected_difficulty,
                selected_type,
                len(questions),
            )
        )

        connection.commit()

        session_id = cursor.lastrowid

        connection.close()

        session_info = {
            "id": session_id,
            "role": selected_role,
            "difficulty": selected_difficulty,
            "interview_type": selected_type,
            "question_count": len(questions),
        }

    return render_template(
        "interview_prep.html",
        questions=questions,
        session_info=session_info,
        roles=roles,
        selected_role=selected_role,
        selected_difficulty=selected_difficulty,
        selected_type=selected_type,
    )
# ==========================================
# JOB APPLICATION TRACKER
# ==========================================

JOB_APPLICATION_STATUSES = [
    "Applied",
    "Under Review",
    "Interview",
    "Offer",
    "Rejected"
]


@app.route("/job-tracker", methods=["GET", "POST"])
@login_required
def job_tracker():

    if request.method == "POST":

        company_name = request.form.get(
            "company_name", ""
        ).strip()

        job_title = request.form.get(
            "job_title", ""
        ).strip()

        location = request.form.get(
            "location", ""
        ).strip()

        job_link = request.form.get(
            "job_link", ""
        ).strip()

        application_date = request.form.get(
            "application_date", ""
        ).strip()

        status = request.form.get(
            "status", "Applied"
        ).strip()

        notes = request.form.get(
            "notes", ""
        ).strip()

        if not company_name or not job_title or not application_date:
            flash(
                "Company name, job title, and application date are required.",
                "error"
            )

            return redirect(url_for("job_tracker"))

        if status not in JOB_APPLICATION_STATUSES:
            status = "Applied"

        connection = get_db_connection()

        connection.execute("""
            INSERT INTO job_applications (
                user_id,
                company_name,
                job_title,
                location,
                job_link,
                application_date,
                status,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            company_name,
            job_title,
            location,
            job_link,
            application_date,
            status,
            notes
        ))

        connection.commit()
        connection.close()

        flash(
            "Job application added successfully!",
            "success"
        )

        return redirect(url_for("job_tracker"))

    connection = get_db_connection()

    applications = connection.execute("""
        SELECT *
        FROM job_applications
        WHERE user_id = ?
        ORDER BY application_date DESC, id DESC
    """, (
        session["user_id"],
    )).fetchall()

    connection.close()

    status_counts = {
        status: 0
        for status in JOB_APPLICATION_STATUSES
    }

    for application in applications:

        if application["status"] in status_counts:
            status_counts[application["status"]] += 1

    return render_template(
        "job_tracker.html",
        applications=applications,
        statuses=JOB_APPLICATION_STATUSES,
        status_counts=status_counts,
        total_applications=len(applications)
    )


@app.route("/job-tracker/edit/<int:application_id>", methods=["POST"])
@login_required
def edit_job_application(application_id):

    company_name = request.form.get(
        "company_name", ""
    ).strip()

    job_title = request.form.get(
        "job_title", ""
    ).strip()

    location = request.form.get(
        "location", ""
    ).strip()

    job_link = request.form.get(
        "job_link", ""
    ).strip()

    application_date = request.form.get(
        "application_date", ""
    ).strip()

    status = request.form.get(
        "status", "Applied"
    ).strip()

    notes = request.form.get(
        "notes", ""
    ).strip()

    if (
        not company_name
        or not job_title
        or not application_date
    ):

        flash(
            "Please complete all required fields.",
            "error"
        )

        return redirect(url_for("job_tracker"))

    if status not in JOB_APPLICATION_STATUSES:
        status = "Applied"

    connection = get_db_connection()

    cursor = connection.execute("""
        UPDATE job_applications

        SET
            company_name = ?,
            job_title = ?,
            location = ?,
            job_link = ?,
            application_date = ?,
            status = ?,
            notes = ?

        WHERE id = ?
        AND user_id = ?

    """, (
        company_name,
        job_title,
        location,
        job_link,
        application_date,
        status,
        notes,
        application_id,
        session["user_id"]
    ))

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:

        flash(
            "Application not found.",
            "error"
        )

    else:

        flash(
            "Application updated successfully!",
            "success"
        )

    return redirect(url_for("job_tracker"))


@app.route(
    "/job-tracker/delete/<int:application_id>",
    methods=["POST"]
)
@login_required
def delete_job_application(application_id):

    connection = get_db_connection()

    cursor = connection.execute("""
        DELETE FROM job_applications

        WHERE id = ?
        AND user_id = ?

    """, (
        application_id,
        session["user_id"]
    ))

    connection.commit()
    connection.close()

    if cursor.rowcount == 0:

        flash(
            "Application not found.",
            "error"
        )

    else:

        flash(
            "Application deleted successfully.",
            "success"
        )

    return redirect(url_for("job_tracker"))

CHATBOT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
@app.route("/api/ai-assistant", methods=["POST"])
@login_required
def ai_assistant():
    """
    CareerAI chatbot endpoint.
    Uses the Gemini client configured at the top of app.py.
    """

    if not gemini_client:
        return jsonify({
            "error": (
                "Gemini API key is missing. "
                "Please configure GEMINI_API_KEY in your .env file."
            )
        }), 500

    data = request.get_json(silent=True) or {}

    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({
            "error": "Invalid message format."
        }), 400

    message = message.strip()

    if not message:
        return jsonify({
            "error": "Please enter a message."
        }), 400

    if len(message) > 4000:
        return jsonify({
            "error": "Please keep your message under 4000 characters."
        }), 400

    history = data.get("history", [])

    safe_history = []

    if isinstance(history, list):

        for item in history[-10:]:

            if not isinstance(item, dict):
                continue

            role = item.get("role")
            content = item.get("content", "")

            if role == "assistant":
                role = "model"

            if role not in ("user", "model"):
                continue

            if not isinstance(content, str):
                continue

            content = content.strip()

            if not content or len(content) > 4000:
                continue

            safe_history.append(
                types.Content(
                    role=role,
                    parts=[
                        types.Part(text=content)
                    ]
                )
            )

    try:

        chat = gemini_client.chats.create(
            model=CHATBOT_MODEL,
            history=safe_history,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are CareerAI Assistant, a helpful and professional "
                    "career guidance chatbot inside the CareerAI platform. "
                    "Help users with resumes, job searching, job matching, "
                    "interview preparation, career planning, professional "
                    "communication, and skill development. "
                    "Give practical, beginner-friendly answers. "
                    "Use clear steps and concise explanations when useful. "
                    "Do not claim to have accessed a user's resume, profile, "
                    "applications, or private account data unless that data "
                    "was explicitly provided in the conversation. "
                    "Do not guarantee job offers or interview success."
                ),
                temperature=0.7,
                max_output_tokens=900
            )
        )

        response = chat.send_message(message=message)

        answer = response.text

        if not answer:
            answer = (
                "I couldn't generate a response. Please try again."
            )

        return jsonify({
            "reply": answer
        })

    except Exception as error:

        app.logger.exception(
            "CareerAI Gemini Assistant error"
        )

        error_text = str(error).lower()

        if (
            "503" in error_text
            or "unavailable" in error_text
            or "high demand" in error_text
        ):

            return jsonify({
                "error": (
                    "Gemini is temporarily busy. "
                    "Please try again in a few moments."
                )
            }), 503

        if (
            "429" in error_text
            or "resource_exhausted" in error_text
        ):

            return jsonify({
                "error": (
                    "Gemini API usage limit reached. "
                    "Please try again later."
                )
            }), 429

        return jsonify({
            "error": (
                "The AI assistant could not respond. "
                "Please check the Flask terminal for the error."
            )
        }), 500

# ==========================================
# COMPLETE CAREER PROFILE
# ==========================================

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():

    user_id = session["user_id"]

    # Default profile values
    profile_data = {
        "phone": "",
        "location": "",
        "headline": "",
        "education": "",
        "graduation_year": "",
        "skills": "",
        "career_goal": "",
        "preferred_role": "",
        "experience": "",
        "projects": "",
        "linkedin": "",
        "github": "",
    }

    connection = get_db_connection()

    try:

        # ----------------------------------
        # LOAD EXISTING PROFILE
        # ----------------------------------

        existing_profile = connection.execute(
            """
            SELECT *
            FROM career_profiles
            WHERE user_id = ?
            """,
            (user_id,)
        ).fetchone()

        if existing_profile:

            for field in PROFILE_FIELDS:

                profile_data[field] = (
                    existing_profile[field] or ""
                )

        # ----------------------------------
        # SAVE PROFILE
        # ----------------------------------

        if request.method == "POST":

            # Read and sanitize submitted values
            for field in PROFILE_FIELDS:

                value = request.form.get(
                    field,
                    ""
                )

                if not isinstance(value, str):
                    value = ""

                profile_data[field] = value.strip()

            # ----------------------------------
            # VALIDATION
            # ----------------------------------

            phone = profile_data["phone"]

            if phone and not re.fullmatch(
                r"[0-9+\-\s()]{7,20}",
                phone
            ):

                flash(
                    "Please enter a valid phone number.",
                    "error"
                )

                return render_template(
                    "profile.html",
                    profile=profile_data,
                    completion=calculate_profile_completion(
                        profile_data
                    )
                )

            graduation_year = profile_data[
                "graduation_year"
            ]

            if graduation_year and not re.fullmatch(
                r"\d{4}",
                graduation_year
            ):

                flash(
                    "Please enter a valid graduation year.",
                    "error"
                )

                return render_template(
                    "profile.html",
                    profile=profile_data,
                    completion=calculate_profile_completion(
                        profile_data
                    )
                )

            # ----------------------------------
            # SAVE TO DATABASE
            # ----------------------------------

            connection.execute(
                """
                INSERT INTO career_profiles (
                    user_id,
                    phone,
                    location,
                    headline,
                    education,
                    graduation_year,
                    skills,
                    career_goal,
                    preferred_role,
                    experience,
                    projects,
                    linkedin,
                    github,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CURRENT_TIMESTAMP
                )

                ON CONFLICT(user_id)
                DO UPDATE SET
                    phone = excluded.phone,
                    location = excluded.location,
                    headline = excluded.headline,
                    education = excluded.education,
                    graduation_year = excluded.graduation_year,
                    skills = excluded.skills,
                    career_goal = excluded.career_goal,
                    preferred_role = excluded.preferred_role,
                    experience = excluded.experience,
                    projects = excluded.projects,
                    linkedin = excluded.linkedin,
                    github = excluded.github,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    profile_data["phone"],
                    profile_data["location"],
                    profile_data["headline"],
                    profile_data["education"],
                    profile_data["graduation_year"],
                    profile_data["skills"],
                    profile_data["career_goal"],
                    profile_data["preferred_role"],
                    profile_data["experience"],
                    profile_data["projects"],
                    profile_data["linkedin"],
                    profile_data["github"],
                )
            )

            connection.commit()

            flash(
                "Your career profile has been saved successfully!",
                "success"
            )

            return redirect(
                url_for("profile")
            )

        # ----------------------------------
        # PROFILE COMPLETION
        # ----------------------------------

        completion = calculate_profile_completion(
            profile_data
        )

        return render_template(
            "profile.html",
            profile=profile_data,
            completion=completion
        )

    except sqlite3.Error:

        app.logger.exception(
            "Career profile database error"
        )

        flash(
            "Unable to load or save your profile. Please try again.",
            "error"
        )

        return render_template(
            "profile.html",
            profile=profile_data,
            completion=calculate_profile_completion(
                profile_data
            )
        )

    finally:

        connection.close()
# ==========================================
# START APPLICATION
# ==========================================

init_db()

if __name__ == "__main__":
    app.run(debug=True)
