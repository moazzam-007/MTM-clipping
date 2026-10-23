"""
modules/face_engine.py
Automated Face Detection and Alignment using OpenCV to horizontally center Mufti Tariq Masood in 1:1 crops.
"""

import logging
import cv2
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("al-haqq-engine.face")

class FaceEngine:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

    def calculate_crop_x(self, video_path: Path, target_size: int = 640) -> int:
        """
        Samples a frame from the video clip, detects the face center,
        and returns the horizontal offset 'crop_x' for a centered 1:1 crop.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.warning(f"Could not open video {video_path} for face detection. Using center crop.")
            return -1

        # Jump to ~2 seconds into the video to avoid black transition frames
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 2))
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            logger.warning("Could not read frame for face detection. Using center crop.")
            return -1

        height, width = frame.shape[:2]
        square_dim = min(width, height)
        default_center_x = (width - square_dim) // 2

        # Convert to grayscale for detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(80, 80)
        )

        if len(faces) == 0:
            logger.info("No face detected in sample frame. Using default center crop.")
            return default_center_x

        # Pick the largest face detected (assumed to be the speaker)
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        fx, fy, fw, fh = faces[0]
        face_center_x = fx + (fw // 2)

        # Center the square crop box on the face center
        crop_x = int(face_center_x - (square_dim / 2))
        # Clamp bounds
        crop_x = max(0, min(crop_x, width - square_dim))

        logger.info(f"Speaker face detected at x={face_center_x}. Dynamic crop_x set to {crop_x}")
        return crop_x
