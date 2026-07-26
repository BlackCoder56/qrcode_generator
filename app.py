from flask import Flask, render_template, url_for, redirect, request
from flask_sqlalchemy import SQLAlchemy
import qrcode
from io import BytesIO
import base64
import secrets
# from models import QRCode
from datetime import datetime, timedelta
import pytz
from PIL import Image

# Set timezone to Uganda
uganda_timezone = pytz.timezone('Africa/Kampala')


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
    created_at = db.Column(db.DateTime, default=datetime.now(uganda_timezone))
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
    expires_at = datetime.now(uganda_timezone).replace(tzinfo=None) + timedelta(minutes=5)  # Set to 5 minutes for testing purposes

    # session['token'] = token
    new_qrcode = QRCode(
            token=token,
            expired_at=expires_at
    )

    db.session.add(new_qrcode)
    db.session.commit()

    verification_url = url_for(
        'verify', 
        token=token, 
        _external=True
    )

    # Generate QR code with logo
    logo_path = 'static/logo.png'

    qr_image = generate_qrcode(
        verification_url,
        logo_path
    )

    return render_template(
        'submit.html', 
        qr_image=qr_image,
        expires_at=expires_at
    )

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
    elif datetime.now(uganda_timezone).replace(tzinfo=None) >= qr_code.expired_at:
        qr_code.status = 'expired'
        db.session.commit()

        status = 'expired'
        message = 'This QR pass has expired and can no longer be used.'

    # QR code is active
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

################## ADMIN ROUTES ##################

# ---------- ADMIN DASHBOARD ----------
@app.route('/admin')
def admin():

    # Get the selected status from the URL
    status_filter = request.args.get('status', 'all')

    # Get current Uganda time
    current_time = datetime.now(uganda_timezone).replace(tzinfo=None)

    # Get all QR codes
    qr_codes = QRCode.query.order_by(
        QRCode.created_at.desc()
    ).all()

    # Update expired QR codes
    for qr_code in qr_codes:
        if (
            qr_code.status == 'active'
            and current_time >= qr_code.expired_at
        ):
            qr_code.status = 'expired'

    # Save status changes
    db.session.commit()

    # Filter QR codes
    if status_filter != 'all':
        qr_codes = [
            qr_code for qr_code in qr_codes
            if qr_code.status == status_filter
        ]

    return render_template(
        'admin.html',
        qr_codes=qr_codes,
        status_filter=status_filter
    )

# ------ ---- REVOKE QR CODE ----------
@app.route('/admin/revoke/<int:qr_id>', methods=['POST'])
def revoke_qr(qr_id):

    qr_code = QRCode.query.get_or_404(qr_id)

    # Only revoke if the QR code is active
    if qr_code.status == 'active':
        qr_code.status = 'revoked'
        db.session.commit()
    
    return redirect(
        url_for('admin')
    )

# ------------ QR CODE DETAILS
@app.route('/admin/qr/<int:qr_id>')
def qr_details(qr_id):

    qr_code = QRCode.query.get_or_404(qr_id)

    verification_url = url_for(
        'verify',
        token=qr_code.token,
        _external=True
    )

    logo_path = 'static/logo.png'

    qr_image = generate_qrcode(
        verification_url,
        logo_path
    )

    return render_template(
        'qr_details.html',
        qr_code=qr_code,
        verification_url=verification_url,
        qr_image=qr_image
    )

# ---------- HELPER FUNCTIONS ----------
def generate_qrcode(data, logo_path):
    """Generate a QR code, add a logo, and return it as Base64."""

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )

    qr.add_data(data)
    qr.make(fit=True)

    # Create QR image
    qr_image = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGB")

    # Open logo
    logo = Image.open(logo_path).convert("RGBA")

    # Calculate logo size
    qr_width, qr_height = qr_image.size
    logo_size = qr_width // 4

    # Resize logo
    logo.thumbnail((logo_size, logo_size))

    # Calculate center position
    position = (
        (qr_width - logo.width) // 2,
        (qr_height - logo.height) // 2
    )

    # Create white background behind logo
    background_size = logo.width + 20

    background = Image.new(
        "RGB",
        (background_size, background_size),
        "white"
    )

    # Center logo on white background
    logo_position = (
        (background_size - logo.width) // 2,
        (background_size - logo.height) // 2
    )

    background.paste(
        logo,
        logo_position,
        logo
    )

    # Position white logo background in center of QR
    background_position = (
        (qr_width - background.width) // 2,
        (qr_height - background.height) // 2
    )

    qr_image.paste(
        background,
        background_position
    )

    # Paste logo on top
    qr_image.paste(
        logo,
        position,
        logo
    )

    # Convert image to bytes
    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")

    # Convert bytes to Base64
    img_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return img_base64

def add_logo_to_qrcode(qr_image, logo_path):
    """Adds a logo to the center of the QR code image."""
    qr = qrcode.make(qr_image)
    logo = Image.open(logo_path)

    # Calculate dimensions for the logo
    qr_width, qr_height = qr.size
    logo_size = int(qr_width / 4)  # Logo size is 1/4th of the QR code size
    logo = logo.resize((logo_size, logo_size))

    # Calculate position to paste the logo
    pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)

    # Paste the logo onto the QR code
    qr.paste(logo, pos)

    return qr

# ---------- RUN APP ----------

if __name__ == '__main__':
    app.run(debug=True)

