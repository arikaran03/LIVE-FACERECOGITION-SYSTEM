# Real-Time Face Verification with Liveness Detection

![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)

This project is a Python-based web server that provides real-time face verification and liveness detection. A user can upload a target image, and then verify their identity through a live video stream. The system first matches the face against the target image and then performs a liveness check to prevent spoofing attacks (e.g., using a photo or video).

The application is built with **Flask** for the web framework and **Flask-SocketIO** for real-time bidirectional communication over WebSockets.

---

## Features

* 📷 **Target Image Upload:** Securely upload a reference image of the person to be verified.
* 📹 **Real-Time Video Streaming:** The client streams video frames to the server via WebSockets.
* 🧠 **AI-Powered Face Recognition:** Uses the `face-recognition` library to compare the face in the video stream against the target image.
* 👁️ **Liveness Detection:** Employs `DeepFace` to ensure the face in the video is a live person, not a static image or a video replay.
* 🔐 **Session-Based:** Each user connection (`socket.sid`) is handled independently, ensuring data privacy between concurrent users.
* ⚙️ **Automatic Cleanup:** Server automatically deletes user data and uploaded images upon disconnection.

---

## How It Works

1.  **Client Connects:** A user connects to the web server, establishing an HTTP and a WebSocket connection.
2.  **Upload Target:** The user uploads a clear picture of their face. The server processes this image, generates a unique face encoding (a mathematical representation), and stores it for the user's session.
3.  **Start Verification:** The user initiates the verification process. A timer starts on the server.
4.  **Stream & Process:** The client's webcam sends video frames to the server in real-time. For each frame, the server:
    * Detects any faces.
    * Compares the detected face's encoding to the stored target encoding.
    * If they match, it performs a **liveness check** on the face.
5.  **Get Result:**
    * ✅ **Success:** If a matching face is found *and* it passes the liveness check, a success message is sent to the client.
    * ❌ **Failure:** If the timer runs out, the user manually stops, or the connection is lost, a failure message is sent.

---

## Tech Stack

* **Backend:** Python
* **Web Framework:** Flask
* **Real-Time Communication:** Flask-SocketIO, python-eventlet
* **Computer Vision:** OpenCV (`opencv-python`)
* **Face Recognition:** `face-recognition`
* **Liveness Detection:** `deepface`
* **Numerical Operations:** NumPy
* **API & CORS:** Flask-CORS

---

## Setup and Installation

### Prerequisites

* Python 3.8 or newer
* `pip` (Python package installer)
* It is highly recommended to use a virtual environment.

### 1. Clone the Repository

```bash
git clone https://github.com/arikaran03/LIVE-FACERECOGITION-SYSTEM
cd LIVE-FACERECOGITION-SYSTEM
```

### 2. Create and Activate a Virtual Environment

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install Dependencies

Now, install all the required packages by running this command in your terminal:

```bash
pip install -r requirements.txt
```

---

## 4. Running the Server

To start the Flask server, execute the following command:

```bash
python app.py
```

You will see output confirming the server has started:
```
Starting Flask app with SocketIO...
Server will be accessible on port 5000.
Client-side JavaScript should connect to: http://localhost:5000
```

You can access the application from:
- **The same machine:** `http://localhost:5000`
- **Other devices on the same network:** `http://192.168.1.10:5000` (replace `192.168.1.10` with your server's local IP address).

---

## 5. API Endpoints

The application uses a combination of a standard HTTP endpoint for the initial setup and WebSocket events for real-time communication.

### HTTP Endpoint

#### `POST /upload_target`
Uploads the target image that will be used for verification. This must be done before starting the verification process.

-   **Form Data:**
    -   `target_image`: The image file of the person to verify.
    -   `socket_id`: The client's unique `socket.id` from the WebSocket connection, which links the uploaded image to the correct user session.

### WebSocket Events

#### Emit Events (Client ➝ Server)

These are events that the client application should send to the server.

-   **`start_verify`**:
    -   Tells the server to begin the face verification process for the client that sent the event.

-   **`video_frame`**:
    -   Sends a single video frame from the client's camera to the server for analysis.
    -   **Payload Example:**
        ```json
        {
          "image": "data:image/jpeg;base64,..."
        }
        ```

-   **`stop_verify`**:
    -   Manually tells the server to stop the verification process for this client.

#### Listen Events (Server ➝ Client)

These are events that the server will send back to the client.

-   **`verification_result`**:
    -   Communicates the final result of the verification process.
    -   **Success Payload:**
        ```json
        {
          "status": "success",
          "message": "Face verified successfully."
        }
        ```
    -   **Failure Payload:**
        ```json
        {
          "status": "failed",
          "message": "Face verification failed or spoof detected."
        }
        ```

-   **`verification_status`**:
    -   Provides real-time status updates to the client throughout the process.
    -   **Example Messages:**
        -   `"Verification started"`
        -   `"Face matched"`
        -   `"Liveness confirmed"`
        -   `"Verification failed"`
