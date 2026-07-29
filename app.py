from flask import Flask, render_template, url_for, redirect, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO
import base64
import secrets

import qrcode
from PIL import Image


# =========================================================
# CONFIGURATION
# =========================================================

UGANDA_TIMEZONE = ZoneInfo("Africa/Kampala")


def now_uganda():
    """
    Return the current time in Uganda.
    The timezone information is removed before saving to SQLite.
    """
    return datetime.now(UGANDA_TIMEZONE).replace(tzinfo=None)


# =========================================================
# FLASK APPLICATION
# =========================================================

app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///qrcodes.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "your-secret-key"

db = SQLAlchemy(app)


# =========================================================
# DATABASE MODEL
# =========================================================

class QRCode(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    token = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="active"
    )

    created_at = db.Column(
        db.DateTime,
        default=now_uganda
    )

    expired_at = db.Column(
        db.DateTime,
        nullable=False
    )


with app.app_context():
    db.create_all()


# =========================================================
# PUBLIC ROUTES
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():

    # Generate unique QR token
    token = secrets.token_urlsafe(16)

    # Get current Uganda time
    created_at = now_uganda()

    # QR code expires 5 minutes after creation
    expires_at = created_at + timedelta(minutes=5)

    # Create database record
    new_qrcode = QRCode(
        token=token,
        created_at=created_at,
        expired_at=expires_at
    )

    db.session.add(new_qrcode)
    db.session.commit()

    # Generate verification URL
    verification_url = url_for(
        "verify",
        token=token,
        _external=True
    )

    # Generate QR code with logo
    logo_path = "static/logo.png"

    qr_image = generate_qrcode(
        verification_url,
        logo_path
    )

    return render_template(
        "submit.html",
        qr_image=qr_image,
        expires_at=expires_at
    )


@app.route("/verify/<token>")
def verify(token):

    # Find QR code
    qr_code = QRCode.query.filter_by(
        token=token
    ).first()

    # QR code does not exist
    if not qr_code:

        status = "invalid"

        message = (
            "This QR pass could not be found."
        )

    # QR code already used
    elif qr_code.status == "used":

        status = "used"

        message = (
            "This QR pass has already been scanned "
            "and cannot be used again."
        )

    # QR code revoked
    elif qr_code.status == "revoked":

        status = "revoked"

        message = (
            "This QR pass has been revoked "
            "and is no longer valid."
        )

    # QR code expired
    elif now_uganda() >= qr_code.expired_at:

        qr_code.status = "expired"

        db.session.commit()

        status = "expired"

        message = (
            "This QR pass has expired "
            "and can no longer be used."
        )

    # QR code is active
    elif qr_code.status == "active":

        # Mark QR code as used
        qr_code.status = "used"

        db.session.commit()

        status = "valid"

        message = (
            "This QR pass is valid "
            "and has been successfully verified."
        )

    # Unknown status
    else:

        status = "invalid"

        message = (
            "This QR pass has an unknown status."
        )

    return render_template(
        "result.html",
        status=status,
        message=message,
        qr_code=qr_code
    )


@app.route("/admin/api/verify/<token>")
def admin_verify(token):

    # Find QR code
    qr_code = QRCode.query.filter_by(
        token=token
    ).first()

    # QR code does not exist
    if not qr_code:

        return {
            "status": "invalid",
            "message": "This QR pass could not be found."
        }

    # Check expiration first
    if (
        qr_code.status == "active"
        and now_utc() >= qr_code.expired_at
    ):

        qr_code.status = "expired"
        db.session.commit()

    # QR code already used
    if qr_code.status == "used":

        return {
            "status": "used",
            "message": "This QR pass has already been scanned.",
            "qr_id": qr_code.id
        }

    # QR code revoked
    if qr_code.status == "revoked":

        return {
            "status": "revoked",
            "message": "This QR pass has been revoked.",
            "qr_id": qr_code.id
        }

    # QR code expired
    if qr_code.status == "expired":

        return {
            "status": "expired",
            "message": "This QR pass has expired.",
            "qr_id": qr_code.id
        }

    # QR code is active
    if qr_code.status == "active":

        # Mark as used
        qr_code.status = "used"

        db.session.commit()

        return {
            "status": "valid",
            "message": "This QR pass is valid and has been successfully verified.",
            "qr_id": qr_code.id
        }

    # Unknown status
    return {
        "status": "invalid",
        "message": "This QR pass has an unknown status."
    }



# =========================================================
# ADMIN ROUTES
# =========================================================

@app.route("/admin")
def admin():

    # Get selected status filter
    status_filter = request.args.get(
        "status",
        "all"
    )

    # Get current Uganda time
    current_time = now_uganda()

    # Get all QR codes
    qr_codes = QRCode.query.order_by(
        QRCode.created_at.desc()
    ).all()

    # Automatically mark expired QR codes
    for qr_code in qr_codes:

        if (
            qr_code.status == "active"
            and current_time >= qr_code.expired_at
        ):

            qr_code.status = "expired"

    # Save any expired status changes
    db.session.commit()

    # Apply status filter
    if status_filter != "all":

        qr_codes = [
            qr_code
            for qr_code in qr_codes
            if qr_code.status == status_filter
        ]

    return render_template(
        "admin.html",
        qr_codes=qr_codes,
        status_filter=status_filter
    )


@app.route(
    "/admin/revoke/<int:qr_id>",
    methods=["POST"]
)
def revoke_qr(qr_id):

    qr_code = QRCode.query.get_or_404(
        qr_id
    )

    # Only active QR codes can be revoked
    if qr_code.status == "active":

        qr_code.status = "revoked"

        db.session.commit()

    return redirect(
        url_for("admin")
    )


@app.route("/admin/qr/<int:qr_id>")
def qr_details(qr_id):

    qr_code = QRCode.query.get_or_404(
        qr_id
    )

    # Generate verification URL
    verification_url = url_for(
        "verify",
        token=qr_code.token,
        _external=True
    )

    # Generate QR code with logo
    logo_path = "static/logo.png"

    qr_image = generate_qrcode(
        verification_url,
        logo_path
    )

    return render_template(
        "qr_details.html",
        qr_code=qr_code,
        verification_url=verification_url,
        qr_image=qr_image
    )


@app.route("/admin/scanner")
def scanner():
    return render_template("scanner.html")

# =========================================================
# QR CODE GENERATION
# =========================================================

def generate_qrcode(data, logo_path):

    """
    Generate a QR code, add a logo,
    and return the image as Base64.
    """

    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4
    )

    qr.add_data(data)
    qr.make(fit=True)

    # Generate QR image
    qr_image = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGB")

    # Open logo
    logo = Image.open(
        logo_path
    ).convert("RGBA")

    # Calculate logo size
    qr_width, qr_height = qr_image.size

    logo_size = qr_width // 4

    # Resize logo
    logo.thumbnail(
        (logo_size, logo_size)
    )

    # Create white background for logo
    background_size = logo.width + 20

    background = Image.new(
        "RGB",
        (
            background_size,
            background_size
        ),
        "white"
    )

    # Center logo on background
    logo_position = (
        (background_size - logo.width) // 2,
        (background_size - logo.height) // 2
    )

    background.paste(
        logo,
        logo_position,
        logo
    )

    # Center white background on QR code
    background_position = (
        (qr_width - background.width) // 2,
        (qr_height - background.height) // 2
    )

    qr_image.paste(
        background,
        background_position
    )

    # Paste logo on top
    logo_position_on_qr = (
        (qr_width - logo.width) // 2,
        (qr_height - logo.height) // 2
    )

    qr_image.paste(
        logo,
        logo_position_on_qr,
        logo
    )

    # Convert image to bytes
    buffer = BytesIO()

    qr_image.save(
        buffer,
        format="PNG"
    )

    # Convert image to Base64
    img_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return img_base64


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(
        debug=True
    )