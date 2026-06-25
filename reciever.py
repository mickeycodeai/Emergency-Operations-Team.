from flask import Flask, request, jsonify, render_template
import csv, os, hashlib, hmac
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_cors import CORS

app = Flask(__name__)
CORS(
    app,
    origins=[
        "https://alab-gjgv.onrender.com",
        "http://localhost:5173"
    ]
)
CSV_FILE = "receiver_data.csv"

# --- Shared secret key (must match scanner) ---
SECRET_KEY = b"eot2026et67567"  # <-- Change this if you want

# --- Gmail Configuration ---
GMAIL_USER = "mikec.pascua@gmail.com"  # <-- Replace with your Gmail
GMAIL_APP_PASSWORD = "qait jrro zucm xiww"  # <-- Use App Password, not normal password

# --- LGU boundaries for GPS-based routing ---
# Each LGU has a bounding box and an official email
LGU_BOUNDARIES = [
    {
        "name": "Luna",
        "lat_min": 14.6,
        "lat_max": 14.65,
        "lng_min": 121.0,
        "lng_max": 121.05,
        "email": "luna_lgu@gmail.com",
    },
    {
        "name": "Cauayan City",
        "lat_min": 15.2,
        "lat_max": 15.25,
        "lng_min": 121.1,
        "lng_max": 121.15,
        "email": "cauayan_lgu@gmail.com",
    },
    # Add more LGUs here
]

# --- Threshold for escalation ---
RISK_THRESHOLD = 50  # Only send email if egg_count exceeds this


# --- Helper to get LGU email by GPS ---
def get_lgu_email_by_gps(lat, lng):
    for lgu in LGU_BOUNDARIES:
        if (
            lgu["lat_min"] <= lat <= lgu["lat_max"]
            and lgu["lng_min"] <= lng <= lgu["lng_max"]
        ):
            return lgu["email"]
    return GMAIL_USER  # fallback


# --- Ensure CSV exists ---
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="") as f:
        csv.writer(f).writerow(
            [
                "timestamp",
                "trap_id",
                "trap_type",
                "gps",
                "egg_count",
                "barangay",
                "sha256_valid",
            ]
        )


# --- Serve Dashboard ---
@app.route("/")
def index():
    return render_template("receiver.html")


# --- Scanner Submission Endpoint ---
@app.route("/api/submit", methods=["POST"])
def submit_data():
    try:
        data = request.json
        trap_id = data.get("trap_id")
        trap_type = data.get("trap_type")
        gps = data.get("gps")
        egg_count = int(data.get("egg_count", 0))
        barangay = data.get("barangay", "")

        # --- Compute HMAC-SHA256 for verification ---
        payload_str = f"{trap_id}{trap_type}{gps}{egg_count}".encode()
        sha256_hash = hmac.new(SECRET_KEY, payload_str, hashlib.sha256).hexdigest()
        valid = sha256_hash == data.get("sha256")

        # --- Save to CSV ---
        with open(CSV_FILE, "a", newline="") as f:
            csv.writer(f).writerow(
                [datetime.utcnow(), trap_id, trap_type, gps, egg_count, barangay, valid]
            )

        return jsonify({"success": True, "sha256_valid": valid})

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# --- Provide Dashboard Data ---
@app.route("/api/ingestion")
def get_ingestion_data():
    entries = []
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(
                    {
                        "timestamp": row["timestamp"],
                        "trap_id": row["trap_id"],
                        "trap_type": row["trap_type"],
                        "gps": row["gps"],
                        "egg_count": int(row["egg_count"]),
                        "barangay": row.get("barangay", ""),
                        "sha256_valid": row["sha256_valid"] == "True",
                    }
                )
    return jsonify(entries)


# --- Escalation Endpoint using GPS ---
@app.route("/api/escalate", methods=["POST"])
def escalate():
    try:
        if not os.path.exists(CSV_FILE):
            return jsonify({"error": "No data available"}), 400

        # Load all records
        with open(CSV_FILE, newline="") as f:
            reader = list(csv.DictReader(f))
            if not reader:
                return jsonify({"error": "No records to escalate"}), 400

            # Pick record with highest egg count
            highest = max(reader, key=lambda x: int(x["egg_count"]))
            trap_id = highest.get("trap_id")
            gps = highest.get("gps")
            egg_count = int(highest.get("egg_count"))

        # --- Skip escalation if below threshold ---
        if egg_count <= RISK_THRESHOLD:
            return jsonify(
                {"success": True, "message": "No escalation: egg count below threshold"}
            )

        # --- Extract latitude and longitude from GPS ---
        lat, lng = map(float, gps.split(","))

        # --- Determine LGU email based on GPS ---
        recipient = get_lgu_email_by_gps(lat, lng)

        # Compose email
        msg = MIMEMultipart()
        msg["From"] = GMAIL_USER
        msg["To"] = recipient
        msg["Subject"] = f"Escalation Alert: High Risk Trap {trap_id}"

        body = f"""
Escalation Alert

Trap ID: {trap_id}
GPS: {gps}
Egg Count: {egg_count}

Please take immediate action.
"""
        msg.attach(MIMEText(body, "plain"))

        # Send email via Gmail SMTP
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({"success": True, "message": f"Escalation sent to {recipient}"})
        return jsonify({"error": str(e)}, 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
