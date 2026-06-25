from flask import Flask, request, jsonify, render_template
import csv
import os
import hashlib
import hmac
import smtplib

from datetime import datetime
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


# Shared secret
SECRET_KEY = b"eot2026et67567"


# Gmail from Render environment
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")


# LGU boundaries

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
    }
]


RISK_THRESHOLD = 50



def get_lgu_email_by_gps(lat, lng):

    for lgu in LGU_BOUNDARIES:

        if (
            lgu["lat_min"] <= lat <= lgu["lat_max"]
            and
            lgu["lng_min"] <= lng <= lgu["lng_max"]
        ):
            return lgu["email"]

    return GMAIL_USER



# Create CSV if missing

if not os.path.exists(CSV_FILE):

    with open(CSV_FILE, "w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow(
            [
                "timestamp",
                "trap_id",
                "trap_type",
                "gps",
                "egg_count",
                "barangay",
                "sha256_valid"
            ]
        )



@app.route("/")
def index():

    return "Receiver API is running"



# ==========================
# RECEIVE DATA
# ==========================

@app.route("/api/submit", methods=["POST"])
def submit_data():

    try:

        data = request.json


        trap_id = data.get("trap_id")
        trap_type = data.get("trap_type")
        gps = data.get("gps")
        egg_count = int(data.get("egg_count",0))
        barangay = data.get("barangay","")


        payload = f"{trap_id}{trap_type}{gps}{egg_count}".encode()


        sha256_hash = hmac.new(
            SECRET_KEY,
            payload,
            hashlib.sha256
        ).hexdigest()


        valid = sha256_hash == data.get("sha256")


        with open(CSV_FILE,"a",newline="") as f:

            writer = csv.writer(f)

            writer.writerow(
                [
                    datetime.utcnow(),
                    trap_id,
                    trap_type,
                    gps,
                    egg_count,
                    barangay,
                    valid
                ]
            )


        return jsonify(
            {
                "success":True,
                "sha256_valid":valid
            }
        )


    except Exception as e:

        return jsonify(
            {
                "error":str(e)
            }
        ),400




# ==========================
# DASHBOARD DATA
# ==========================

@app.route("/api/ingestion")
def ingestion():


    entries=[]


    if os.path.exists(CSV_FILE):

        with open(CSV_FILE,newline="") as f:

            reader=csv.DictReader(f)


            for row in reader:

                entries.append(
                    {
                        "timestamp":row["timestamp"],
                        "trap_id":row["trap_id"],
                        "trap_type":row["trap_type"],
                        "gps":row["gps"],
                        "egg_count":int(row["egg_count"]),
                        "barangay":row["barangay"],
                        "sha256_valid":row["sha256_valid"]=="True"
                    }
                )


    return jsonify(entries)




# ==========================
# EMAIL ESCALATION
# ==========================

@app.route("/api/escalate",methods=["POST"])
def escalate():

    try:


        if not os.path.exists(CSV_FILE):

            return jsonify(
                {
                    "error":"No data available"
                }
            ),400



        with open(CSV_FILE,newline="") as f:

            records=list(csv.DictReader(f))


        if not records:

            return jsonify(
                {
                    "error":"No records"
                }
            ),400



        highest=max(
            records,
            key=lambda x:int(x["egg_count"])
        )


        trap_id=highest["trap_id"]

        gps=highest["gps"]

        egg_count=int(highest["egg_count"])



        if egg_count <= RISK_THRESHOLD:

            return jsonify(
                {
                    "success":True,
                    "message":"Below threshold"
                }
            )



        lat,lng=map(float,gps.split(","))


        recipient=get_lgu_email_by_gps(
            lat,
            lng
        )



        msg=MIMEMultipart()

        msg["From"]=GMAIL_USER

        msg["To"]=recipient

        msg["Subject"]=f"High Risk Trap Alert {trap_id}"



        body=f"""

ESCALATION ALERT


Trap ID:
{trap_id}


GPS:
{gps}


Egg Count:
{egg_count}


Please investigate immediately.

"""


        msg.attach(
            MIMEText(body,"plain")
        )



        server=smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465
        )


        server.login(
            GMAIL_USER,
            GMAIL_APP_PASSWORD
        )


        server.send_message(msg)


        server.quit()



        return jsonify(
            {
                "success":True,
                "message":"Escalation email sent"
            }
        )



    except Exception as e:


        return jsonify(
            {
                "error":str(e)
            }
        ),500




if __name__=="__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
