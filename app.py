"""
ZenithWorks AI Employees — Multi-Agent Workflow Automation
Flask app using CrewAI + Groq (llama-3.1-8b-instant)

"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import csv
import time
import smtplib
import logging
import threading
from datetime import datetime
from io import StringIO
from collections import defaultdict

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from crewai import Agent, Task, Crew, Process, LLM

# Logging 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Flask
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "zenithworks-secret")
CORS(app)

# Groq LLM
if not os.getenv("GROQ_API_KEY"):
    logger.warning("GROQ_API_KEY not set in .env — agent calls will fail.")

llm = LLM(
    model="groq/llama-3.1-8b-instant",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.3,
)

# Monitoring (thread-safe)
_stats_lock = threading.Lock()
_monitor = {
    "total_requests":       0,
    "total_latency_ms":     0.0,
    "errors":               0,
    "dept_counts":          defaultdict(int),
    "batch_rows_processed": 0,
    "emails_sent":          0,
}

def _record(department: str, latency_ms: float):
    with _stats_lock:
        _monitor["total_requests"]   += 1
        _monitor["total_latency_ms"] += latency_ms
        _monitor["dept_counts"][department] += 1

def _get_monitor_snapshot() -> dict:
    with _stats_lock:
        total = _monitor["total_requests"]
        return {
            "total_requests":       total,
            "avg_latency_ms":       round(_monitor["total_latency_ms"] / total, 1) if total else 0,
            "errors":               _monitor["errors"],
            "department_breakdown": dict(_monitor["dept_counts"]),
            "batch_rows_processed": _monitor["batch_rows_processed"],
            "emails_sent":          _monitor["emails_sent"],
        }

# Google Sheets + SMTP
class GoogleServices:
    def __init__(self):
        creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        if creds_json:
            try:
                creds_dict = json.loads(creds_json)
                creds = service_account.Credentials.from_service_account_info(
                    creds_dict,
                    scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                self.sheets_service = build("sheets", "v4", credentials=creds)
                self.spreadsheet_id = os.getenv("SPREADSHEET_ID")
                logger.info("Google Sheets connected.")
            except Exception as e:
                logger.warning(f"Sheets init failed: {e}")
                self.sheets_service = None
                self.spreadsheet_id = None
        else:
            self.sheets_service = None
            self.spreadsheet_id = None
            logger.warning("GOOGLE_SHEETS_CREDENTIALS not set — Sheets logging disabled.")

        self.smtp_server   = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port     = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_email    = os.getenv("SMTP_EMAIL")
        self.smtp_password = os.getenv("SMTP_PASSWORD")

    def write_sheet(self, range_name: str, values: list) -> bool:
        if not self.sheets_service:
            return False
        try:
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": values}
            ).execute()
            return True
        except HttpError as e:
            logger.error(f"Sheets write error: {e}")
            return False

    def send_email(self, to: str, subject: str, body: str) -> bool:
        if not self.smtp_email or not self.smtp_password:
            logger.warning("SMTP credentials not set.")
            return False
        try:
            msg = MIMEMultipart()
            msg["From"]    = self.smtp_email
            msg["To"]      = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_email, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Email sent to {to}")
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

google_services = GoogleServices()

# CrewAI runner
def run_crewai(role: str, goal: str, backstory: str, prompt: str) -> str:
    agent = Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=1,
    )
    task = Task(
        description=prompt,
        agent=agent,
        expected_output="A professional business email starting with 'Subject:'"
    )
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
    )
    return str(crew.kickoff())

# Department handlers
def process_hr_task(data: dict) -> str:
    return run_crewai(
        role="Senior HR Business Partner",
        goal="Write warm professional onboarding emails that make new employees feel welcomed",
        backstory="You are an experienced HR professional at ZenithWorks Tech with 10+ years of talent management.",
        prompt=f"""
Write a professional and warm onboarding welcome email for a new employee:
  Name       : {data.get('name', 'N/A')}
  Position   : {data.get('position', 'N/A')}
  Department : {data.get('department', 'N/A')}
  Start Date : {data.get('start_date', 'N/A')}
  Manager    : {data.get('manager', 'N/A')}

Guidelines:
- Express genuine excitement about them joining
- Briefly mention what to expect on their first day
- Keep it under 200 words, professional but warm tone

Write ONLY the email. Start with "Subject:" on the first line.
Sign off as: HR Team, ZenithWorks Tech
"""
    )


def process_customer_service_task(data: dict) -> str:
    return run_crewai(
        role="Senior Customer Support Specialist",
        goal="Resolve customer issues with empathy and clear action steps",
        backstory="You are a skilled customer support specialist at ZenithWorks Tech known for empathetic communication.",
        prompt=f"""
Write a professional support response email:
  Customer   : {data.get('customer_name', 'N/A')}
  Issue      : {data.get('issue', 'N/A')}
  Product    : {data.get('product', 'N/A')}
  Priority   : {data.get('priority', 'N/A')}

Guidelines:
- Open with empathy and acknowledgment of the issue
- Provide a clear next step or resolution
- Match urgency to priority (High = immediate action, Low = standard timeline)
- Keep it under 200 words

Write ONLY the email. Start with "Subject:" on the first line.
Sign off as: Customer Services Team, ZenithWorks Tech
"""
    )


def process_marketing_task(data: dict) -> str:
    return run_crewai(
        role="Senior Marketing Strategist",
        goal="Create high-converting email campaigns that drive engagement and sales",
        backstory="You are a creative marketing strategist at ZenithWorks Tech with expertise in B2B and B2C campaigns.",
        prompt=f"""
Write a compelling marketing email:
  Product     : {data.get('product', 'N/A')}
  Audience    : {data.get('audience', 'N/A')}
  Key Benefits: {data.get('benefits', 'N/A')}
  Offer/CTA   : {data.get('offer', 'N/A')}

Guidelines:
- Hook the reader in the first sentence
- Highlight 2-3 key benefits clearly
- End with a strong call-to-action
- Keep it under 250 words, persuasive but not pushy

Write ONLY the email. Start with "Subject:" on the first line.
Sign off as: Marketing Team, ZenithWorks Tech
"""
    )


def process_accounting_task(data: dict) -> str:
    return run_crewai(
        role="Accounts Receivable Specialist",
        goal="Send accurate professional payment emails that maintain good client relationships",
        backstory="You are a detail-oriented accounts receivable specialist at ZenithWorks Tech.",
        prompt=f"""
Write a professional invoice/payment email:
  Client         : {data.get('client_name', 'N/A')}
  Invoice Number : {data.get('invoice_number', 'N/A')}
  Amount         : {data.get('amount', 'N/A')}
  Due Date       : {data.get('due_date', 'N/A')}

Guidelines:
- Professional and courteous, not aggressive
- Clearly state the invoice number, amount, and due date
- Include a note to contact us for any discrepancies
- Keep it under 150 words

Write ONLY the email. Start with "Subject:" on the first line.
Sign off as: Accounting Team, ZenithWorks Tech
"""
    )


# Department registry
HANDLERS = {
    "hr":               process_hr_task,
    "customer-service": process_customer_service_task,
    "marketing":        process_marketing_task,
    "accounting":       process_accounting_task,
}

SHEET_MAP = {
    "hr":               "HR_Outputs!A:E",
    "customer-service": "CS_Outputs!A:E",
    "marketing":        "Marketing_Outputs!A:E",
    "accounting":       "Accounting_Outputs!A:E",
}

BATCH_SHEET_MAP = {
    "hr":               "HR_Batch!A:E",
    "customer-service": "CS_Batch!A:E",
    "marketing":        "Marketing_Batch!A:E",
    "accounting":       "Accounting_Batch!A:E",
}

# CSV batch processor
def process_csv_tasks(csv_content: str, department: str) -> list:
    handler = HANDLERS.get(department)
    if not handler:
        raise ValueError(f"Unknown department: '{department}'")

    results = []
    for i, row in enumerate(csv.DictReader(StringIO(csv_content))):
        try:
            output = handler(row)
            status = "success"
            logger.info(f"[Batch] Row {i+1} OK")
        except Exception as e:
            output = f"Error: {e}"
            status = "error"
            logger.error(f"[Batch] Row {i+1} failed: {e}")

        results.append({
            "row":       i + 1,
            "input":     row,
            "output":    output,
            "status":    status,
            "timestamp": datetime.now().isoformat(),
        })

    with _stats_lock:
        _monitor["batch_rows_processed"] += len(results)

    return results


# Routes
@app.route("/health")
def health():
    snap = _get_monitor_snapshot()
    return jsonify({
        "status":     "healthy",
        "model":      "groq/llama-3.1-8b-instant",
        "framework":  "CrewAI",
        "timestamp":  datetime.now().isoformat(),
        "monitoring": snap,
    })


@app.route("/api/departments")
def list_departments():
    return jsonify({
        "departments": list(HANDLERS.keys()),
        "model":       "groq/llama-3.1-8b-instant",
    })


@app.route("/api/process/<department>", methods=["POST"])
def process_department(department: str):
    if department not in HANDLERS:
        return jsonify({"success": False, "error": f"Invalid department: '{department}'"}), 400

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    t0 = time.perf_counter()
    try:
        result = HANDLERS[department](data)
    except Exception as e:
        with _stats_lock:
            _monitor["errors"] += 1
        logger.exception(f"Task error — dept={department}")
        return jsonify({"success": False, "error": str(e)}), 500

    latency_ms = round((time.perf_counter() - t0) * 1000, 1)
    _record(department, latency_ms)

    primary_key = (
        data.get("name") or data.get("customer_name") or
        data.get("product") or data.get("client_name") or department
    )
    google_services.write_sheet(
        SHEET_MAP[department],
        [[datetime.now().isoformat(), department, primary_key, f"{latency_ms}ms", result]]
    )

    email_sent = False
    if data.get("send_email") and data.get("email"):
        lines      = result.split("\n")
        subject    = lines[0].replace("Subject:", "").strip() if lines else "ZenithWorks Notification"
        body       = "\n".join(lines[1:]).strip()
        email_sent = google_services.send_email(data["email"], subject, body)
        if email_sent:
            with _stats_lock:
                _monitor["emails_sent"] += 1

    return jsonify({
        "success":    True,
        "department": department,
        "result":     result,
        "email_sent": email_sent,
        "latency_ms": latency_ms,
        "model":      "groq/llama-3.1-8b-instant",
        "timestamp":  datetime.now().isoformat(),
    })


@app.route("/api/process/csv", methods=["POST"])
def process_csv():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Request body must be JSON"}), 400

    missing = [f for f in ["csv_content", "department"] if f not in data]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {missing}"}), 400

    try:
        results = process_csv_tasks(data["csv_content"], data["department"])
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        with _stats_lock:
            _monitor["errors"] += 1
        return jsonify({"success": False, "error": str(e)}), 500

    if data.get("save_to_sheets"):
        rows = [
            [r["timestamp"], data["department"], str(r["input"]), r["status"], r["output"]]
            for r in results
        ]
        google_services.write_sheet(
            BATCH_SHEET_MAP.get(data["department"], "Sheet1!A:E"), rows
        )

    success_count = sum(1 for r in results if r["status"] == "success")
    return jsonify({
        "success":       True,
        "total":         len(results),
        "success_count": success_count,
        "error_count":   len(results) - success_count,
        "model":         "groq/llama-3.1-8b-instant",
        "results":       results,
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.errorhandler(404)
def not_found(e):          return jsonify({"error": "Endpoint not found"}), 404
@app.errorhandler(405)
def method_not_allowed(e): return jsonify({"error": "Method not allowed"}), 405
@app.errorhandler(500)
def internal_error(e):     return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"ZenithWorks starting on port {port} | model=groq/llama-3.1-8b-instant")
    app.run(host="0.0.0.0", port=port, debug=debug)