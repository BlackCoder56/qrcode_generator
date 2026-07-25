from flask import Flask, render_template, request, session, url_for
import qrcode
from io import BytesIO
import base64
import secrets

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'  # Needed for session


# ---------- ROUTES ----------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/submit', methods=['POST'])
def submit():
    # Generate a random code and save it in the session
    token = secrets.token_urlsafe(16)

    session['token'] = token

    verification_url = url_for('verify', token=token, _external=True)

    # Generate QR code
    qr_image = generate_qrcode(verification_url)

    return render_template(
        'submit.html', 
        qr_image=qr_image, 
        token=token,
        verification_url=verification_url
    )

# ---------- Verification Route ----------
@app.route('/verify/<token>')
def verify(token):
    saved_token = session.get('token')

    if token == saved_token:
        msg = "Valid QR Code!"
    else:
        msg = "Invalid QR Code!"
    
    return render_template('Verify.html', msg=msg)

@app.route('/result', methods=['POST'])
def result():
    code_entered = request.form.get("generatedCode")
    saved_code = session.get('token')

    if not code_entered:
        return render_template('result.html', msg="Code not entered!")

    try:
        if int(code_entered) == int(saved_code):
            msg = True
        else:
            msg = False
    except ValueError:
        # In case user enters non-numeric input
        msg = False

    session.pop('token', None) # Remove value from session

    return render_template('result.html', msg=msg)


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