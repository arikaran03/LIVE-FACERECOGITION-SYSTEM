import os
import cv2
import face_recognition
from deepface import DeepFace
import numpy as np
import base64
import pickle 
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS 
import time

# Initialize Flask app
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Enable CORS for all routes for HTTP requests (e.g., /upload_target)
# For more restrictive CORS, you can specify origins: CORS(app, origins=["http://localhost:xxxx", "http://friend-ip:xxxx"])
CORS(app)

# Initialize SocketIO with CORS settings for WebSocket connections
# Use "*" for testing to allow all origins. For production, specify allowed origins.
# e.g., socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="http://your_friend_client_origin_if_known")
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*") # Use eventlet or gevent
# socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*") # Allows all origins for SocketIO
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


# --- Configuration for Auto-Flushing (Not fully implemented in original, kept structure) ---
FLUSH_TIMEOUT_SECONDS = 120  # Time after which an image is considered stale (example)
CLEANUP_INTERVAL_SECONDS = 600 # How often a cleanup task might run (example)

# --- Session-specific storage ---
# Stores { sid: {"encoding": encoding_array, "filepath": path_to_image, "name": name_string} }
session_target_encodings = {}
# Stores { sid: {"in_progress": bool, "start_time": float, "found_live": bool} }
session_verification_state = {}

VERIFICATION_DURATION = 15  # seconds
KNOWN_FACE_NAME_DEFAULT = "Target Person" # Default name if not provided dynamically

def image_to_base64(image_path): # This function is not used in the provided server code but might be for client.
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

@app.route('/')
def index():
    # This will serve your main HTML page.
    # Ensure 'index.html' is in a 'templates' folder in the same directory as your app.py
    # or adjust the path accordingly.
    return render_template('index.html')

@app.route('/upload_target', methods=['POST'])
def upload_target():
    if 'target_image' not in request.files:
        return jsonify({"status": "error", "message": "No image file provided."}), 400
    
    file = request.files['target_image']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file."}), 400

    socket_id = request.form.get('socket_id')
    if not socket_id:
        return jsonify({"status": "error", "message": "Socket ID is required for target upload."}), 400

    filepath = None # Initialize filepath
    if file:
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        # Using socket_id in filename for session-specific images.
        # Consider if socket_id might contain characters unsuitable for filenames or if it's too long.
        # A more robust approach might be to map socket_id to a UUID or a sanitized string.
        filename = f"target_image_{socket_id.replace(':', '_').replace('/', '_')}.png" # Basic sanitization
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Clean up any old image for this socket_id first
        if socket_id in session_target_encodings and \
           "filepath" in session_target_encodings[socket_id] and \
           os.path.exists(session_target_encodings[socket_id]["filepath"]):
            try:
                os.remove(session_target_encodings[socket_id]["filepath"])
                print(f"Removed old target image for SID {socket_id}")
            except Exception as e:
                print(f"Error removing old target image for SID {socket_id}: {e}")
        
        file.save(filepath)

        try:
            target_image_data = face_recognition.load_image_file(filepath)
            encodings = face_recognition.face_encodings(target_image_data)
            
            if not encodings:
                if os.path.exists(filepath): os.remove(filepath)
                return jsonify({
                    "status": "error", 
                    "message": "No face found in the uploaded image. Please ensure the image contains a clear, single face."
                }), 400
            
            if len(encodings) > 1:
                if os.path.exists(filepath): os.remove(filepath)
                return jsonify({
                    "status": "error",
                    "message": f"Multiple faces detected ({len(encodings)} found). Please upload an image with only one person."
                }), 400

            session_target_encodings[socket_id] = {
                "encoding": encodings[0],
                "filepath": filepath,
                "name": KNOWN_FACE_NAME_DEFAULT # Or a name provided by user via form data
            }
            
            print(f"Target face uploaded successfully for SID: {socket_id}")
            return jsonify({"status": "success", "message": "Target face uploaded successfully."})
        except Exception as e:
            print(f"Error processing target image for SID {socket_id}: {e}")
            if filepath and os.path.exists(filepath): os.remove(filepath)
            return jsonify({"status": "error", "message": f"Could not process target image. Error: {str(e)}"}), 500
    
    return jsonify({"status": "error", "message": "File could not be processed."}), 400

@socketio.on('start_verify')
def handle_start_verify():
    sid = request.sid
    target_data = session_target_encodings.get(sid)

    if not target_data or target_data.get("encoding") is None:
        emit('verification_result', {'status': 'error', 'message': 'Target image not set. Please upload a target image first.'}, room=sid)
        return

    print(f"Verification process started for SID: {sid}.")
    session_verification_state[sid] = {
        'in_progress': True,
        'start_time': time.time(),
        'found_live': False
    }
    emit('verification_status', {'status': 'started', 'message': 'Verification process initiated. receiving frames...'}, room=sid)


@socketio.on('video_frame')
def handle_video_frame(data_url):
    sid = request.sid
    current_session_state = session_verification_state.get(sid)
    target_session_data = session_target_encodings.get(sid)

    if not current_session_state or not current_session_state.get('in_progress'):
        # print(f"Video frame received for SID {sid}, but verification not in progress.")
        return # Verification not active or already completed/stopped for this session

    if not target_session_data or target_session_data.get("encoding") is None:
        emit('verification_result', {'status': 'error', 'message': 'Target image data missing for session.'}, room=sid)
        if current_session_state: current_session_state['in_progress'] = False
        return

    known_face_encoding_for_session = target_session_data["encoding"]
    # known_face_name_for_session = target_session_data.get("name", KNOWN_FACE_NAME_DEFAULT)


    if time.time() - current_session_state['start_time'] > VERIFICATION_DURATION:
        if not current_session_state.get('found_live', False): # Only send timeout if not already found
             print(f"Verification timed out for SID: {sid}.")
             emit('verification_result', {'status': 'failed', 'message': 'Face mismatch or timeout.'}, room=sid)
        current_session_state['in_progress'] = False # Stop processing further frames
        return

    try:
        # Ensure data_url is a string and contains the expected prefix
        if not isinstance(data_url, str) or not data_url.startswith('data:image/jpeg;base64,'): # Or image/png, etc.
            # print(f"Invalid data_url format received from SID: {sid}")
            # emit('verification_result', {'status': 'error', 'message': 'Invalid frame data received.'}, room=sid)
            return

        header, encoded = data_url.split(",", 1)
        image_data = base64.b64decode(encoded)
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            # print(f"Received an empty or undecodable frame for SID: {sid}.")
            return

        # Resize frame for faster face recognition processing
        # Consider making fx, fy configurable or adaptive. 0.25 is faster but less accurate for small faces.
        # 0.5 was in original, keeping it.
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        # Convert the image from BGR color (which OpenCV uses) to RGB color (which face_recognition uses)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)


        face_locations = face_recognition.face_locations(rgb_small_frame) # model can be 'cnn' for more accuracy but slower
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        # Loop through each face found in the frame
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            matches = face_recognition.compare_faces([known_face_encoding_for_session], face_encoding, tolerance=0.5) # Adjust tolerance as needed
            
            name = "Unknown" # Default if no match
            if True in matches:
                name = target_session_data.get("name", KNOWN_FACE_NAME_DEFAULT)
                # print(f"Target face matched for SID: {sid}. Name: {name}. Proceeding to liveness check.")

                # Scale back up face locations since the frame we detected in was scaled
                top_orig, right_orig, bottom_orig, left_orig = top * 2, right * 2, bottom * 2, left * 2
                
                # Add some padding to the cropped face for liveness detection, but ensure it's within frame bounds
                padding = 20 
                h, w, _ = frame.shape
                top_orig = max(0, top_orig - padding)
                left_orig = max(0, left_orig - padding)
                bottom_orig = min(h, bottom_orig + padding)
                right_orig = min(w, right_orig + padding)

                face_img_for_liveness = frame[top_orig:bottom_orig, left_orig:right_orig]

                if face_img_for_liveness.size == 0:
                    # print(f"Cropped face image for liveness is empty for SID: {sid}.")
                    continue
                
                try:
                    # Important: DeepFace.extract_faces with anti_spoofing can be slow.
                    # It expects BGR images by default if passing a numpy array.
                    # If `frame` is BGR, `face_img_for_liveness` is also BGR.
                    liveness_results_list = DeepFace.extract_faces(
                        img_path=face_img_for_liveness, # Pass the BGR numpy array directly
                        detector_backend='opencv',  # 'ssd', 'dlib', 'mtcnn', 'retinaface', 'mediapipe', 'yolov8', 'centerface'
                        align=False, # Alignment might improve liveness but adds overhead
                        enforce_detection=False, # Don't error if DeepFace fails to re-detect a face in the crop
                        anti_spoofing=True
                    )
                    
                    if liveness_results_list and len(liveness_results_list) > 0:
                        # Assuming the first face in the crop is the one we care about for liveness
                        liveness_result = liveness_results_list[0]
                        
                        # The key for liveness might be 'is_real' or 'is_live' depending on DeepFace version and model
                        # Checking common keys. Prioritize 'is_real'.
                        is_real_face = liveness_result.get("is_real", False) # New key in recent versions
                        is_live_face = liveness_result.get("is_live", False) # Older key possibly

                        if is_real_face or is_live_face:
                            print(f"Verification successful: Live person ({name}) detected for SID: {sid}.")
                            emit('verification_result', {'status': 'success', 'message': f'Verification successful! Welcome {name}.'}, room=sid)
                            current_session_state['found_live'] = True
                            current_session_state['in_progress'] = False 
                            return # Exit after successful verification
                        # elif liveness_result.get("is_fake", False): # New key
                        #     print(f"Spoof detected for SID: {sid}. is_fake: True")
                        #     # Optionally emit a specific spoof message
                        #     # emit('verification_result', {'status': 'failed', 'message': 'Spoof attempt detected.'}, room=sid)
                        #     # current_session_state['in_progress'] = False # Could stop on detected spoof
                        #     # return
                        else:
                            # This case means anti_spoofing ran but didn't confirm 'is_real' or 'is_live' as True.
                            # It might not explicitly say 'is_fake: True' but imply it's not real.
                            print(f"Liveness check negative (not confirmed real) for SID: {sid}. Result: {liveness_result}")
                            # Do not immediately fail here, let the timeout or other frames handle it,
                            # unless you want to be very strict on the first negative liveness.
                    else:
                        # DeepFace's extract_faces with anti_spoofing didn't return a face or liveness result from the crop
                        print(f"No face or inconclusive liveness result by DeepFace for SID: {sid}.")

                except Exception as e:
                    # Log detailed error for liveness check failure
                    print(f"Liveness check error for SID {sid} on face of {name}: {e}")
                    # You might want to inform the client, or just retry with the next frame.
                    # emit('verification_result', {'status': 'error', 'message': 'Liveness check failed to process.'}, room=sid)

            # If found_live became true, we should have returned already.
            # This break is more of a safeguard if the return was missed.
            if current_session_state.get('found_live', False):
                break 
        
    except cv2.error as e:
        print(f"OpenCV error processing video frame for SID {sid}: {e}. Likely bad image data.")
        # emit('verification_result', {'status': 'error', 'message': 'Error processing video frame data.'}, room=sid)
        # Consider stopping verification for this user if frames are consistently bad
    except Exception as e:
        print(f"Generic error processing video frame for SID {sid}: {e}")
        # emit('verification_result', {'status': 'error', 'message': 'An unexpected error occurred.'}, room=sid)
        # current_session_state['in_progress'] = False # Optionally stop on generic error


@socketio.on('stop_verify')
def handle_stop_verify():
    sid = request.sid
    current_session_state = session_verification_state.get(sid)

    print(f"Verification stop request received for SID: {sid}.")
    if current_session_state and current_session_state.get('in_progress'):
        # Only send 'failed' if not already successful
        if not current_session_state.get('found_live', False):
            emit('verification_result', {'status': 'failed', 'message': 'Verification stopped by user.'}, room=sid)
        current_session_state['in_progress'] = False
        print(f"Verification stopped by client for SID: {sid}.")
    # else:
        # print(f"Verification stop request for SID {sid}, but no active verification found or already stopped.")


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Client disconnected: {sid}")

    # Clean up target encoding and image file
    if sid in session_target_encodings:
        target_data = session_target_encodings.pop(sid)
        filepath_to_delete = target_data.get("filepath")
        if filepath_to_delete and os.path.exists(filepath_to_delete):
            try:
                os.remove(filepath_to_delete)
                print(f"Deleted target image {filepath_to_delete} for SID {sid}.")
            except Exception as e:
                print(f"Error deleting target image {filepath_to_delete} for SID {sid}: {e}")
    
    # Clean up verification state
    if sid in session_verification_state:
        session_verification_state.pop(sid)
        print(f"Cleaned up verification state for SID {sid}.")


if __name__ == '__main__':
    print("Starting Flask app with SocketIO...")
    print(f"Server will be accessible on port 5000. If on a local network, use this machine's local IP address.")
    print("Make sure your firewall allows connections on port 5000.")
    print("Client-side JavaScript should connect to: http://<YOUR_SERVER_IP>:5000")

    try:
        print("Pre-loading DeepFace models (this might take a moment on first run)...")
        # Create a small dummy image for DeepFace model pre-loading
        # Using a BGR numpy array as DeepFace.extract_faces can handle it.
        dummy_img_array = np.zeros((100, 100, 3), dtype=np.uint8)
        DeepFace.extract_faces(
            img_path=dummy_img_array,
            detector_backend='opencv', # Using a lightweight detector for pre-loading
            anti_spoofing=True,
            enforce_detection=False
        )
        
        print("DeepFace model check/pre-load attempt complete.")
    except Exception as e:
        print(f"Could not pre-load/check DeepFace models: {e}")
        print("Note: DeepFace models might download/initialize on the first actual liveness check, causing an initial delay for the first user.")

    # For production, use a proper WSGI server like Gunicorn with eventlet or gevent workers
    # Example: gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
    # The `host='0.0.0.0'` makes the server accessible from other devices on your network.
    socketio.run(app, host='0.0.0.0', port=5000, debug=True) # Set debug=False for production