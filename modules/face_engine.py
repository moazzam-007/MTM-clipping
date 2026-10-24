"""
modules/face_engine.py
Automated Face Detection and Alignment using OpenCV to horizontally center Mufti Tariq Masood in 1:1 crops.
Multi-frame sampling (5 frames across duration) with median filtering to prevent single-frame anomalies.
"""

import logging
import cv2
from pathlib import Path

logger = logging.getLogger("al-haqq-engine.face")

class FaceEngine:
    def __init__(self):
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self.face_cascade = cv2.CascadeClassifier(cascade_path)
            if self.face_cascade.empty():
                self.face_cascade = None
                logger.warning("Haar cascade classifier loaded empty. Center crop will be used.")
        except Exception as e:
            self.face_cascade = None
            logger.warning(f"Could not initialize face cascade: {e}. Center crop will be used.")

    def calculate_crop_x(self, video_path: Path, samples: int = 5) -> int:
        """
        Samples multiple frames across the video clip, detects face centers,
        and uses the median coordinate to return an even horizontal offset 'crop_x' for a centered 1:1 crop.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.warning(f"Could not open video {video_path} for face detection. Using default center crop.")
            return -1

        detected_centers = []
        width = 0
        height = 0
        square_dim = 0

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

            if width <= 0 or height <= 0:
                # Read first frame to inspect shape
                ret, probe = cap.read()
                if ret and probe is not None:
                    height, width = probe.shape[:2]

            square_dim = min(width, height) if (width > 0 and height > 0) else 720

            if total_frames > 0 and self.face_cascade is not None:
                # Sample positions across video (e.g. 15%, 35%, 50%, 65%, 85%)
                sample_fractions = [0.15, 0.35, 0.50, 0.65, 0.85][:samples]
                for frac in sample_fractions:
                    target_frame = int(total_frames * frac)
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                    ret, frame = cap.read()
                    if not ret or frame is None:
                        continue

                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = self.face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.1,
                        minNeighbors=4,
                        minSize=(80, 80)
                    )

                    if len(faces) > 0:
                        # Pick largest face
                        best_face = max(faces, key=lambda f: f[2] * f[3])
                        fx, fy, fw, fh = best_face
                        face_center_x = fx + (fw // 2)
                        detected_centers.append(face_center_x)
        finally:
            cap.release()

        default_center_x = (width - square_dim) // 2 if width > square_dim else 0

        if not detected_centers:
            logger.info("No face detected in sampled frames. Using default center crop.")
            final_center = default_center_x + (square_dim // 2)
        else:
            # Use median face center to ignore temporary movements or false positives
            detected_centers.sort()
            final_center = detected_centers[len(detected_centers) // 2]
            logger.info(f"Speaker face median center at x={final_center} (from {len(detected_centers)} sample frames).")

        crop_x = int(final_center - (square_dim / 2))
        crop_x = max(0, min(crop_x, width - square_dim)) if width > square_dim else 0
        # Ensure crop_x is even number to prevent YUV420p chroma misalignments
        crop_x = crop_x - (crop_x % 2)

        return crop_x
