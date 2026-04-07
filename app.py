from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
import requests, base64, uuid, os
from datetime import datetime
import qrcode
from flask_mail import Mail, Message

app = Flask(__name__)

# =========================
# DATABASE
# =========================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///payments.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =========================
# EMAIL CONFIG (GMAIL)
# =========================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'ledwabathabang54@email.com'
app.config['MAIL_PASSWORD'] = 'Karaboboity#88'

mail = Mail(app)

# =========================
# PAYPAL CONFIG
# =========================
CLIENT_ID = "AfE7Dk_XHIdYcgq7Sy2rwmzQa9mgrj33TmRPh2FOtsAOF5557OmRM7A_OaGbYHT7xMegjPmkPbLfQyO1"
SECRET = "EAVPEctw_KDxzZb9UeVdTkZ1W1JsHWg3v3Bh9qURa8zw9A2aayJ7xUz7RzrrjYcja-qgBMvwL282gRTq"
BASE_URL = "https://api-m.sandbox.paypal.com"  # change to live later

# =========================
# MODELS
# =========================
class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(100))
    payment_id = db.Column(db.String(100))
    amount = db.Column(db.String(20))
    status = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_code = db.Column(db.String(100), unique=True)
    payment_id = db.Column(db.String(100))
    used = db.Column(db.Boolean, default=False)

# =========================
# INIT DB
# =========================
@app.before_first_request
def create_tables():
    db.create_all()

# =========================
# PAYPAL AUTH
# =========================
def get_access_token():
    auth = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()

    res = requests.post(
        f"{BASE_URL}/v1/oauth2/token",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={"grant_type": "client_credentials"}
    )
    return res.json()['access_token']

# =========================
# QR GENERATION
# =========================
def generate_qr(code):
    folder = "static/qrcodes"
    os.makedirs(folder, exist_ok=True)

    path = f"{folder}/{code}.png"
    qr = qrcode.make(code)
    qr.save(path)

    return path

# =========================
# EMAIL FUNCTION
# =========================
def send_ticket(email, code):
    msg = Message("Your Ticket 🎟️",
                  sender=app.config['MAIL_USERNAME'],
                  recipients=[email])

    msg.body = f"Your ticket code: {code}"
    mail.send(msg)

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return render_template("paypal.html")

# CREATE ORDER
@app.route("/create-order", methods=["POST"])
def create_order():
    access_token = get_access_token()
    amount = request.json.get("amount", "10.00")

    res = requests.post(
        f"{BASE_URL}/v2/checkout/orders",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        },
        json={
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "ZAR",
                    "value": amount
                }
            }]
        }
    )

    data = res.json()

    payment = Payment(order_id=data['id'], amount=amount, status="CREATED")
    db.session.add(payment)
    db.session.commit()

    return jsonify(data)

# CAPTURE PAYMENT
@app.route("/capture-order", methods=["POST"])
def capture_order():
    order_id = request.json["orderID"]
    email = request.json.get("email", "test@email.com")

    access_token = get_access_token()

    res = requests.post(
        f"{BASE_URL}/v2/checkout/orders/{order_id}/capture",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }
    )

    data = res.json()

    if data['status'] == "COMPLETED":
        payment = Payment.query.filter_by(order_id=order_id).first()

        ticket_code = str(uuid.uuid4())
        generate_qr(ticket_code)

        ticket = Ticket(ticket_code=ticket_code, payment_id=data['id'])

        payment.status = "COMPLETED"
        payment.payment_id = data['id']

        db.session.add(ticket)
        db.session.commit()

        send_ticket(email, ticket_code)

        return jsonify({"ticket_code": ticket_code})

    return jsonify({"error": "Payment failed"})

# VIEW TICKETS
@app.route("/tickets")
def tickets():
    tickets = Ticket.query.all()
    return render_template("tickets.html", tickets=tickets)

# VALIDATE
@app.route("/validate/<code>")
def validate(code):
    t = Ticket.query.filter_by(ticket_code=code).first()

    if not t:
        return "❌ Invalid Ticket"
    if t.used:
        return "⚠️ Already Used"

    t.used = True
    db.session.commit()
    return "✅ Access Granted"

# ADMIN
@app.route("/admin")
def admin():
    payments = Payment.query.all()
    tickets = Ticket.query.all()
    return render_template("admin.html", payments=payments, tickets=tickets)

# WEBHOOK
@app.route("/webhook/paypal", methods=["POST"])
def webhook():
    data = request.json
    print("Webhook:", data)
    return jsonify({"status": "ok"})

# RUN
if __name__ == "__main__":
    app.run()