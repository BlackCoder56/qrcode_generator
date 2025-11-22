from flask import Flask, render_template
import qrcode
from io import BytesIO
import base64

app = Flask(__name__)

@app.route('/')
def index():
    data = "Hi there it worked"

    # Generate QR code
    qr = qrcode.make(data)

    # Convert to bytes
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()

    # Encode to base64
    img_base64 = base64.b64encode(img_bytes).decode()

    return render_template('index.html', qr_image=img_base64)