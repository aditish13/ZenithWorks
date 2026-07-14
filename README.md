# ZenithWorks AI Employees

Multi-agent AI automation platform that generates professional emails for 4 departments using **CrewAI + Groq (Llama 3.1)**.

## Why Groq?
| | Groq (Llama 3.1) | Gemini 1.5 Flash | GPT-4o-mini |
|---|---|---|---|
| Free tier | Yes | Yes (limited) | No |
| Daily limit | 14,400 requests | Quota exhausts fast | Paid only |
| Speed | Fastest (LPU) | Fast | Fast |
| Setup | API key only | Google account + project | OpenAI account |

## Departments

| Department | Input Fields |
|------------|-------------|
| HR | name, position, department, start_date, manager |
| Customer Service | customer_name, issue, product, priority |
| Marketing | product, audience, benefits, offer |
| Accounting | client_name, invoice_number, amount, due_date |

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env
# Edit .env — add your GROQ_API_KEY (free from https://console.groq.com)

# 3. Run
python app.py
# → http://localhost:5000
```

## Get Your Free Groq API Key

1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up with Google or email
3. Go to **API Keys** → **Create API Key**
4. Paste into `.env` as `GROQ_API_KEY=...`

## Environment Variables

```env
# Required
GROQ_API_KEY=your_groq_api_key_here

# Flask
SECRET_KEY=any_random_string
PORT=5000
FLASK_DEBUG=false

# Optional — SMTP email dispatch
SMTP_EMAIL=your@gmail.com
SMTP_PASSWORD=your_16_char_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587

# Optional — Google Sheets logging
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account",...}
SPREADSHEET_ID=your_sheet_id
```

## Docker

```bash
docker-compose up --build
```

## Deploy to Render (free)

1. Push to GitHub
2. Connect repo at [render.com](https://render.com)
3. Set env vars in Render dashboard (`GROQ_API_KEY` is the only required one)
4. Deploy — `render.yaml` handles the rest

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + monitoring stats |
| GET | `/api/departments` | List available departments |
| POST | `/api/process/{dept}` | Generate single email |
| POST | `/api/process/csv` | Batch CSV processing |

## Single Request Example

```bash
curl -X POST http://localhost:5000/api/process/hr \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Jane Doe",
    "position": "Software Engineer",
    "department": "Engineering",
    "start_date": "2025-09-01",
    "manager": "John Smith"
  }'
```

## Batch CSV Example

```bash
curl -X POST http://localhost:5000/api/process/csv \
  -H "Content-Type: application/json" \
  -d '{
    "department": "hr",
    "csv_content": "name,position,department,start_date,manager\nJane,Engineer,Tech,2025-09-01,John",
    "save_to_sheets": false
  }'
```

## Monitoring — /health Response

```json
{
  "status": "healthy",
  "model": "groq/llama-3.1-8b-instant",
  "framework": "CrewAI",
  "monitoring": {
    "total_requests": 47,
    "avg_latency_ms": 843.2,
    "department_breakdown": {
      "hr": 18,
      "marketing": 12,
      "customer-service": 10,
      "accounting": 7
    },
    "batch_rows_processed": 23,
    "emails_sent": 5,
    "errors": 0
  }
}
```

## Google Sheets Setup (Optional)

1. Create a Google Cloud project
2. Enable the Google Sheets API
3. Create a Service Account and download the JSON key
4. Share your spreadsheet with the service account email
5. Paste the entire JSON as a single line into `GOOGLE_SHEETS_CREDENTIALS`

Sheet tabs auto-logged:
- `HR_Outputs`, `CS_Outputs`, `Marketing_Outputs`, `Accounting_Outputs`
- `HR_Batch`, `CS_Batch`, `Marketing_Batch`, `Accounting_Batch`