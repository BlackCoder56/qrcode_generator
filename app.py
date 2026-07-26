from flask import Flask, render_template, url_for
from flask_sqlalchemy import SQLAlchemy
import qrcode
from io import BytesIO
import base64
import secrets
# from models import QRCode
from datetime import datetime, timedelta


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qrcodes.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'  # Needed for session

db = SQLAlchemy(app)

# ---------- DATABASE MODEL ---------

class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expired_at = db.Column(db.DateTime, nullable=False)

with app.app_context():
    db.create_all()  # Create database tables if they don't exist

# ---------- ROUTES ----------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    # Generate a random code and save it in the session
    token = secrets.token_urlsafe(16)

    # Set expiration time for the QR code (e.g., 5 minutes from now)
    expires_at = datetime.utcnow() + timedelta(hours=7)  # Set to 7 hours for testing purposes

    # session['token'] = token
    new_qrcode = QRCode(
            token=token, expired_at=expires_at
    )

    db.session.add(new_qrcode)
    db.session.commit()

    verification_url = url_for(
        'verify', 
        token=token, 
        _external=True
    )

    # Generate QR code
    qr_image = generate_qrcode(verification_url)

    return render_template(
        'submit.html', 
        qr_image=qr_image,
        expires_at=expires_at
    )

# ---------- Verification Route ----------
# ---------- Verification Route ----------
@app.route('/verify/<token>')
def verify(token):

    # Find QR code in the database
    qr_code = QRCode.query.filter_by(token=token).first()

    # QR code does not exist
    if not qr_code:
        status = 'invalid'
        message = 'This QR pass could not be found.'

    # QR code has already been used
    elif qr_code.status == 'used':
        status = 'used'
        message = 'This QR pass has already been scanned and cannot be used again.'

    # QR code has been revoked
    elif qr_code.status == 'revoked':
        status = 'revoked'
        message = 'This QR pass has been revoked and is no longer valid.'

    # QR code has expired
    elif datetime.utcnow() > qr_code.expired_at:

        qr_code.status = 'expired'
        db.session.commit()

        status = 'expired'
        message = 'This QR pass has expired and can no longer be used.'

    # QR code is active and valid
    elif qr_code.status == 'active':

        # Mark QR code as used
        qr_code.status = 'used'
        db.session.commit()

        status = 'valid'
        message = 'This QR pass is valid and has been successfully verified.'

    # Unknown status
    else:
        status = 'invalid'
        message = 'This QR pass has an unknown status.'

    return render_template(
        'result.html',
        status=status,
        message=message,
        qr_code=qr_code
    )

# @app.route('/result', methods=['POST'])
# def result():
#     code_entered = request.form.get("generatedCode")
#     saved_code = session.get('token')

#     if not code_entered:
#         return render_template('result.html', msg="Code not entered!")

#     try:
#         if int(code_entered) == int(saved_code):
#             msg = True
#         else:
#             msg = False
#     except ValueError:
#         # In case user enters non-numeric input
#         msg = False

#     session.pop('token', None) # Remove value from session

#     return render_template('result.html', msg=msg)


# ---------- HELPER FUNCTIONS ----------

def generate_qrcode(data):
    """Generates a QR code and returns it as a base64 string."""
    qr = qrcode.make(data)

    # Convert QR code image to bytes
    buffer = BytesIO()
    qr.save(buffer, format="PNG")

    img_bytes = buffer.getvalue()

    # Encode as base64 string
    img_base64 = base64.b64encode(img_bytes).decode()

    return img_base64


# ---------- RUN APP ----------

if __name__ == '__main__':
    app.run(debug=True)

