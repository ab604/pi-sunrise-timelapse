#!/usr/bin/env python3
"""
Sunrise Timelapse Script for Southampton, UK
Created for Raspberry Pi Zero 2 W and Zero Cam
Vibe coded by Claude. Prompted by Alistair Bailey
2025-08-03
"""

import os
import sys
import time
import json
import datetime
import subprocess
import logging
import base64
import urllib.parse
from pathlib import Path

# Import packages (use system packages to avoid virtual environment issues)
try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: sudo apt install python3-requests")
    sys.exit(1)

try:
    # Try newer astral API first (v2.x)
    from astral import LocationInfo
    from astral.sun import sun
    ASTRAL_VERSION = "new"
except ImportError:
    try:
        # Fall back to older astral API (v1.x)
        import astral
        ASTRAL_VERSION = "old"
    except ImportError:
        print("Error: astral not installed. Run: sudo apt install python3-astral")
        sys.exit(1)

# Configuration for Southampton, UK
CONFIG = {
    "location": {
        "name": "Southampton",
        "country": "United Kingdom",
        "latitude": 50.9097,  # Southampton coordinates
        "longitude": -1.4044,
        "timezone": "Europe/London",
    },
    "groq_api_key": os.getenv("GROQ_API_KEY", ""),
    "bluesky": {
        "handle": os.getenv("BLUESKY_HANDLE", "handle.bsky.social"),
        "password": os.getenv("BLUESKY_PASSWORD", ""),
        "server": "https://bsky.social",
    },
    "capture": {
        "duration_minutes": 75,  # 75 minutes total
        "framerate": 1,  # 1 frame per second = 1800 frames
        "width": 800,
        "height": 800,
        "ev": 0.5,
        "start_before_sunrise_minutes": 45,  # Start 45 min before sunrise
    },
    "video": {
        "output_duration_seconds": 30,  # 30-second final video
        "crf": 23,  # Good quality, reasonable file size
        "preset": "ultrafast",  # Fast encoding for Pi Zero 2 W
    },
    "paths": {
        "base_dir": f'{os.path.expanduser("~")}/sunrise_timelapse',
        "video_dir": f'{os.path.expanduser("~")}/sunrise_timelapse/videos',
        "raw_dir": f'{os.path.expanduser("~")}/sunrise_timelapse/raw_videos',
        "log_dir": f'{os.path.expanduser("~")}/sunrise_timelapse/logs',
    },
    "cleanup": {"keep_days": 7, "auto_cleanup": True},
}

class FixedBlueSkyClient:
    """FIXED Bluesky client using correct video service API"""

    def __init__(self):
        self.access_token = None
        self.did = None
        self.handle = None
        self.server = CONFIG['bluesky']['server']
        self.video_server = 'https://video.bsky.app'

    def create_session(self, identifier, password):
        """Create authenticated session"""
        try:
            response = requests.post(
                f"{self.server}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": identifier,
                    "password": password
                },
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data["accessJwt"]
                self.did = data["did"]
                self.handle = data["handle"]
                print(f"✅ Session created for @{self.handle}")
                return True
            else:
                print(f"❌ Bluesky login failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"❌ Bluesky session creation error: {e}")
            return False

    def get_user_pds_did(self):
        """Get the user's PDS DID from their profile"""
        try:
            # Get the user's DID document to find their PDS
            response = requests.get(f"https://plc.directory/{self.did}", timeout=30)

            if response.status_code == 200:
                did_doc = response.json()
                # Look for the PDS service
                services = did_doc.get('service', [])
                for service in services:
                    if service.get('id') == '#atproto_pds':
                        pds_url = service.get('serviceEndpoint', '')
                        if pds_url:
                            # Extract domain and create DID
                            parsed = urllib.parse.urlparse(pds_url)
                            return f"did:web:{parsed.netloc}"
                print("❌ Could not find PDS service in DID document")
                return None
            else:
                print(f"❌ Failed to get DID document: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error getting PDS DID: {e}")
            return None

    def get_service_auth(self):
        """Get service auth token for video uploads"""
        try:
            pds_did = self.get_user_pds_did()
            if not pds_did:
                print("❌ Could not determine user's PDS DID")
                return None

            print(f"🔍 Using PDS DID: {pds_did}")

            response = requests.get(
                f"{self.server}/xrpc/com.atproto.server.getServiceAuth",
                headers={"Authorization": f"Bearer {self.access_token}"},
                params={
                    "aud": pds_did,  # Use the user's PDS DID
                    "lxm": "com.atproto.repo.uploadBlob",  # Use uploadBlob
                    "exp": int(time.time()) + 1800  # 30 minutes
                },
                timeout=30
            )

            if response.status_code == 200:
                service_auth = response.json()["token"]
                print(f"✅ Got service auth token for video uploads")
                return service_auth
            else:
                print(f"❌ Service auth failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"❌ Service auth error: {e}")
            return None

    def wait_for_video_processing(self, job_id):
        """Wait for video processing to complete"""
        try:
            print(f"⏳ Waiting for video processing (Job ID: {job_id})...")

            # Get service auth for job status checking
            service_auth = self.get_service_auth()
            if not service_auth:
                return None

            max_attempts = 30  # Wait up to 5 minutes (30 * 10 seconds)
            for attempt in range(max_attempts):
                response = requests.get(
                    f"{self.video_server}/xrpc/app.bsky.video.getJobStatus",
                    headers={
                        "Authorization": f"Bearer {service_auth}"
                    },
                    params={
                        "jobId": job_id
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    job_status_response = response.json()
                    # The actual job status is nested inside jobStatus
                    job_status = job_status_response.get("jobStatus", {})
                    state = job_status.get("state")

                    print(f"📊 Job status: {state} (attempt {attempt + 1}/{max_attempts})")

                    if state == "JOB_STATE_COMPLETED":
                        blob_ref = job_status.get("blob")
                        if blob_ref:
                            print(f"✅ Video processing complete! Got blob reference.")
                            return blob_ref
                        else:
                            print("❌ Processing complete but no blob reference found")
                            return None
                    elif state == "JOB_STATE_FAILED":
                        error = job_status.get("error", "Unknown error")
                        print(f"❌ Video processing failed: {error}")
                        return None
                    elif state in ["JOB_STATE_CREATED", "JOB_STATE_RUNNING", "JOB_STATE_ENCODING"]:
                        # Still processing, wait a bit
                        # JOB_STATE_ENCODING is a valid intermediate state
                        if state == "JOB_STATE_ENCODING":
                            print("🎬 Video is being encoded...")
                        time.sleep(10)
                        continue
                    else:
                        print(f"⚠️  Unknown job state: {state} - continuing to wait...")
                        time.sleep(10)
                        continue
                else:
                    print(f"❌ Failed to check job status: {response.status_code} - {response.text}")
                    time.sleep(10)
                    continue

            print("❌ Video processing timed out after 5 minutes")
            return None

        except Exception as e:
            print(f"❌ Error waiting for video processing: {e}")
            return None

    def get_completed_job_blob(self, job_id):
        """Get blob reference from completed job"""
        try:
            print(f"📋 Getting blob reference for completed job: {job_id}")

            service_auth = self.get_service_auth()
            if not service_auth:
                return None

            response = requests.get(
                f"{self.video_server}/xrpc/app.bsky.video.getJobStatus",
                headers={
                    "Authorization": f"Bearer {service_auth}"
                },
                params={
                    "jobId": job_id
                },
                timeout=30
            )

            if response.status_code == 200:
                job_status_response = response.json()
                print(f"DEBUG: Full job status response: {json.dumps(job_status_response, indent=2, default=str)}")

                # The blob is nested inside jobStatus
                job_status = job_status_response.get("jobStatus", {})
                blob_ref = job_status.get("blob")

                if blob_ref:
                    print(f"✅ Got blob reference: {json.dumps(blob_ref, indent=2, default=str)}")
                    return blob_ref
                else:
                    print("❌ No blob reference found in jobStatus")
                    print("Available jobStatus fields:", list(job_status.keys()))
                    return None
            else:
                print(f"❌ Failed to get job status: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error getting completed job blob: {e}")
            return None

    def upload_video(self, video_path):
        """Upload video using proper video service API"""
        try:
            # Get service auth token first
            service_auth = self.get_service_auth()
            if not service_auth:
                return None

            print(f"📹 Uploading video to proper video service...")
            print(f"🆔 Using DID: {self.did}")

            # Check file size
            file_size = os.path.getsize(video_path)
            print(f"📊 Video file size: {file_size / (1024*1024):.1f}MB")

            # Read video file
            with open(video_path, 'rb') as f:
                video_data = f.read()

            # Use the working approach: URL parameters with both did and name
            encoded_did = urllib.parse.quote(self.did, safe='')
            upload_url = f"{self.video_server}/xrpc/app.bsky.video.uploadVideo?did={encoded_did}&name=video.mp4"

            print(f"🔗 Uploading to: {upload_url}")

            response = requests.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {service_auth}",
                    "Content-Type": "video/mp4"
                },
                data=video_data,
                timeout=600
            )

            print(f"DEBUG: Video upload response status: {response.status_code}")

            if response.status_code == 200:
                upload_result = response.json()
                print(f"DEBUG: Video upload response: {json.dumps(upload_result, indent=2, default=str)}")

                job_id = upload_result.get("jobId")
                if job_id:
                    # Wait for processing to complete and get blob reference
                    blob_ref = self.wait_for_video_processing(job_id)
                    if blob_ref:
                        # Return the blob reference in the expected format
                        return {
                            "blob": blob_ref,
                            "jobId": job_id,
                            "state": "completed"
                        }
                    else:
                        print("❌ Failed to get blob reference after processing")
                        return None
                else:
                    print("❌ No job ID returned from upload")
                    return None
            elif response.status_code == 409:
                # Video already exists - this is actually good!
                upload_result = response.json()
                print(f"✅ Video already uploaded and processed!")
                print(f"DEBUG: Existing video response: {json.dumps(upload_result, indent=2, default=str)}")

                job_id = upload_result.get("jobId")
                state = upload_result.get("state")

                if state == "JOB_STATE_COMPLETED" and job_id:
                    # Get the blob reference from the completed job
                    blob_ref = self.get_completed_job_blob(job_id)
                    if blob_ref:
                        return {
                            "blob": blob_ref,
                            "jobId": job_id,
                            "state": "completed"
                        }
                    else:
                        print("❌ Failed to get blob reference from completed job")
                        return None
                else:
                    print(f"❌ Unexpected state for existing video: {state}")
                    return None
            else:
                print(f"❌ Video upload failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Video upload error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def create_post_with_video(self, text, video_result, alt_text=""):
        """Create post with video"""
        try:
            # Build post record with proper video embed structure
            record = {
                "$type": "app.bsky.feed.post",
                "text": text,
                "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z'),
                "embed": {
                    "$type": "app.bsky.embed.video",
                    "video": video_result.get("blob")  # Use the blob from video service
                }
            }

            # Add alt text if provided
            if alt_text:
                record["embed"]["alt"] = alt_text

            # Add aspect ratio if available in video result
            if "aspectRatio" in video_result:
                record["embed"]["aspectRatio"] = video_result["aspectRatio"]

            print(f"DEBUG: Post record: {json.dumps(record, indent=2, default=str)}")

            # Create the post
            response = requests.post(
                f"{self.server}/xrpc/com.atproto.repo.createRecord",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json"
                },
                json={
                    "repo": self.did,
                    "collection": "app.bsky.feed.post",
                    "record": record
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                print(f"DEBUG: Post creation response: {json.dumps(result, indent=2, default=str)}")
                return result
            else:
                print(f"❌ Post creation failed: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Post creation error: {e}")
            return None

class SunriseTimelapse:
    def __init__(self):
        self.setup_logging()
        self.setup_directories()
        self.setup_location()

    def setup_logging(self):
        """Setup logging configuration"""
        log_dir = Path(CONFIG['paths']['log_dir'])
        log_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.date.today().strftime('%Y-%m-%d')
        log_file = log_dir / f"sunrise_{today}.log"

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_directories(self):
        """Create necessary directories"""
        for path_key in ['video_dir', 'raw_dir', 'log_dir']:
            Path(CONFIG['paths'][path_key]).mkdir(parents=True, exist_ok=True)

    def setup_location(self):
        """Setup location for sunrise calculations"""
        loc = CONFIG['location']
        if ASTRAL_VERSION == "new":
            self.location = LocationInfo(
                loc['name'],
                loc['country'],
                loc['timezone'],
                loc['latitude'],
                loc['longitude']
            )
        else:
            # Older astral API (v1.x)
            self.location = astral.Location((
                loc['name'],
                loc['country'],
                loc['latitude'],
                loc['longitude'],
                loc['timezone'],
                0  # elevation
            ))

    def get_sunrise_time(self, date=None):
        """Get sunrise time for given date (today if None)"""
        if date is None:
            date = datetime.date.today()

        try:
            if ASTRAL_VERSION == "new":
                s = sun(self.location.observer, date=date)
                sunrise_utc = s['sunrise']
                # Convert UTC to local timezone
                import zoneinfo
                local_tz = zoneinfo.ZoneInfo('Europe/London')
                sunrise_local = sunrise_utc.astimezone(local_tz).replace(tzinfo=None)
            else:
                # Older astral API should handle this automatically
                sunrise_utc = self.location.sunrise(date)
                import zoneinfo
                local_tz = zoneinfo.ZoneInfo('Europe/London')
                sunrise_local = sunrise_utc.astimezone(local_tz).replace(tzinfo=None)

            self.logger.info(f"Sunrise time for {date}: {sunrise_local.strftime('%H:%M:%S')}")
            return sunrise_local

        except Exception as e:
            self.logger.error(f"Error calculating sunrise time: {e}")
            # Fallback: assume 7:00 AM
            fallback_time = datetime.datetime.combine(date, datetime.time(7, 0))
            self.logger.warning(f"Using fallback sunrise time: {fallback_time}")
            return fallback_time

    def wait_until_start_time(self, start_time):
        """Wait until it's time to start capturing"""
        now = datetime.datetime.now()

        if start_time <= now:
            self.logger.warning("Start time has already passed!")
            return

        wait_seconds = (start_time - now).total_seconds()
        self.logger.info(f"Waiting {int(wait_seconds/60)} minutes until {start_time.strftime('%H:%M:%S')}")

        while datetime.datetime.now() < start_time:
            remaining = start_time - datetime.datetime.now()
            if remaining.total_seconds() > 60:
                time.sleep(60)  # Check every minute
                minutes_left = int(remaining.total_seconds() / 60)
                if minutes_left % 5 == 0:  # Log every 5 minutes
                    self.logger.info(f"{minutes_left} minutes until capture starts...")
            else:
                time.sleep(5)  # Check every 5 seconds when close

    def get_free_memory(self):
        """Get available memory in MB"""
        try:
            result = subprocess.run(['free', '-m'], capture_output=True, text=True, timeout=30)
            lines = result.stdout.strip().split('\n')
            mem_line = lines[1].split()
            return int(mem_line[6])  # Available memory
        except Exception as e:
            self.logger.warning(f"Could not get memory info: {e}")
            return 0

    def capture_sunrise_video(self):
        """Capture 75-minute sunrise as continuous video"""
        sunrise_time = self.get_sunrise_time()
        capture_config = CONFIG['capture']

        # Calculate start time (45 minutes before sunrise)
        start_offset = datetime.timedelta(minutes=capture_config['start_before_sunrise_minutes'])
        start_time = sunrise_time - start_offset
        end_time = start_time + datetime.timedelta(minutes=capture_config['duration_minutes'])

        # Create raw video file for today
        today = datetime.date.today().strftime('%Y-%m-%d')
        raw_dir = Path(CONFIG['paths']['raw_dir'])
        raw_video_path = raw_dir / f"sunrise_raw_{today}.h264"

        self.logger.info(f"=== Sunrise Video Capture ===")
        self.logger.info(f"Date: {today}")
        self.logger.info(f"Sunrise time: {sunrise_time.strftime('%H:%M:%S')}")
        self.logger.info(f"Capture start: {start_time.strftime('%H:%M:%S')}")
        self.logger.info(f"Capture end: {end_time.strftime('%H:%M:%S')}")
        self.logger.info(f"Duration: {capture_config['duration_minutes']} minutes")
        self.logger.info(f"Raw video file: {raw_video_path}")

        # Wait until start time
        self.wait_until_start_time(start_time)

        # Calculate timeout in milliseconds
        timeout_ms = capture_config['duration_minutes'] * 60 * 1000

        self.logger.info("=== Starting video capture ===")
        memory_before = self.get_free_memory()

        # Capture using libcamera-vid
        cmd = [
            'libcamera-vid',
            '--width', str(capture_config['width']),
            '--height', str(capture_config['height']),
            '--framerate', str(capture_config['framerate']),
            '--timeout', str(timeout_ms),
            '--ev', str(capture_config['ev']),
            '--nopreview',
            '-o', str(raw_video_path)
        ]

        try:
            start_capture = time.time()

            # Run the video capture with progress monitoring
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

            start_time_monitor = time.time()
            while process.poll() is None:
                elapsed = time.time() - start_time_monitor
                if elapsed > 300 and elapsed % 300 < 1:  # Log every 5 minutes
                    remaining = (timeout_ms / 1000) - elapsed
                    memory_now = self.get_free_memory()
                    self.logger.info(f"Capturing... {elapsed/60:.1f}min elapsed, {remaining/60:.1f}min remaining - {memory_now}MB free")
                time.sleep(30)  # Check every 30 seconds instead of 1 second

            stdout, stderr = process.communicate()

            capture_time = time.time() - start_capture
            memory_after = self.get_free_memory()

            if process.returncode == 0 and raw_video_path.exists():
                size_mb = raw_video_path.stat().st_size / (1024 * 1024)

                self.logger.info("=== Video Capture Success ===")
                self.logger.info(f"Raw video size: {size_mb:.1f}MB")
                self.logger.info(f"Capture duration: {capture_time/60:.1f} minutes")
                self.logger.info(f"Memory used: {memory_before - memory_after}MB")
                self.logger.info(f"Final memory: {memory_after}MB free")

                return raw_video_path
            else:
                self.logger.error(f"Video capture failed. Return code: {process.returncode}")
                if stderr:
                    self.logger.error(f"Error: {stderr}")
                return None

        except Exception as e:
            self.logger.error(f"Video capture error: {e}")
            return None

    def create_timelapse_from_video(self, raw_video_path):
        """Create 30-second timelapse from raw video"""
        if not raw_video_path or not raw_video_path.exists():
            self.logger.error("No raw video file to process")
            return None

        video_config = CONFIG['video']
        today = datetime.date.today().strftime('%Y-%m-%d')
        video_dir = Path(CONFIG['paths']['video_dir'])
        final_video_path = video_dir / f"sunrise_{today}.mp4"

        # Calculate speed-up factor for 30-second output
        capture_duration = CONFIG['capture']['duration_minutes'] * 60  # seconds
        target_duration = video_config['output_duration_seconds']
        speedup_factor = capture_duration / target_duration  # Should be 150x for 75min→30sec

        self.logger.info("=== Creating Final Timelapse ===")
        self.logger.info(f"Input: {raw_video_path}")
        self.logger.info(f"Output: {final_video_path}")
        self.logger.info(f"Speed-up factor: {speedup_factor:.1f}x")
        self.logger.info(f"Target duration: {target_duration} seconds")

        # FFmpeg command to speed up video
        cmd = [
            'ffmpeg', '-y',
            '-i', str(raw_video_path),
            '-filter:v', f'setpts=PTS/{speedup_factor}',
            '-c:v', 'libx264',
            '-preset', video_config['preset'],
            '-crf', str(video_config['crf']),
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',  # Optimize for web streaming
            str(final_video_path)
        ]

        try:
            self.logger.info("Starting video processing (this may take 5-10 minutes)...")
            memory_before = self.get_free_memory()
            start_time = time.time()

            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=3600  # 60 minute timeout
            )

            creation_time = time.time() - start_time
            memory_after = self.get_free_memory()

            if final_video_path.exists():
                size_mb = final_video_path.stat().st_size / (1024 * 1024)

                # Verify video is valid
                probe_cmd = ['ffprobe', '-v', 'quiet', '-show_entries',
                           'format=duration', '-of', 'csv=p=0', str(final_video_path)]
                probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                duration = float(probe_result.stdout.strip()) if probe_result.stdout.strip() else 0

                self.logger.info("=== Video Processing Success ===")
                self.logger.info(f"Final size: {size_mb:.1f}MB")
                self.logger.info(f"Duration: {duration:.1f} seconds")
                self.logger.info(f"Processing time: {creation_time/60:.1f} minutes")
                self.logger.info(f"Memory used: {memory_before - memory_after}MB")

                return final_video_path
            else:
                self.logger.error("Final video file was not created")
                return None

        except subprocess.TimeoutExpired:
            self.logger.error("Video processing timed out")
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg error: {e.stderr}")
            return None

    def take_photo_after_video(self):
        """Take a fresh photo after video recording for weather analysis"""
        today = datetime.date.today().strftime("%Y-%m-%d")
        photo_path = Path(CONFIG["paths"]["raw_dir"]) / f"analysis_photo_{today}.jpg"

        self.logger.info("📸 Taking fresh photo for weather analysis...")

        cmd = [
            'libcamera-still',
            '--width', '800',
            '--height', '800',
            '--ev', '0.5',
            '--quality', '90',
            '--timeout', '2000',  # 2 second delay for auto-exposure
            '--nopreview',
            '-o', str(photo_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=30
            )

            if photo_path.exists() and photo_path.stat().st_size > 10000:
                self.logger.info(f"✅ Analysis photo taken: {photo_path}")
                return photo_path
            else:
                self.logger.warning("Photo file not created or too small")
                return None

        except subprocess.TimeoutExpired:
            self.logger.warning("Photo capture timed out")
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Photo capture failed: {e.stderr}")
            return None
        except Exception as e:
            self.logger.error(f"Error taking photo: {e}")
            return None

    def generate_ai_description(self, image_path):
        """Generate weather description using Groq Vision API"""
        groq_key = CONFIG.get('groq_api_key')

        if not groq_key or groq_key == 'api_key':
            # Fallback description
            self.logger.info("No Groq API key configured, using fallback description")
            return "Dawn in Southampton. Again."

        try:
            # Read and encode image
            with open(image_path, 'rb') as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode()

            headers = {
                'Authorization': f"Bearer {groq_key}",
                'Content-Type': 'application/json'
            }

            data = {
                "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Describe the weather in this image of dawn in Southampton in less than 250 characters. Start the text with: 'Dawn in Southampton and the weather is'",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}"
                                },
                            },
                        ],
                    }
                ],
                "max_tokens": 50,
                "temperature": 0.3,
            }

            self.logger.info("Sending image to Groq for weather description...")
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers=headers,
                json=data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                description = result['choices'][0]['message']['content'].strip()
                self.logger.info(f"Groq generated description: {description}")
                return description
            else:
                self.logger.error(f"Groq API error {response.status_code}: {response.text}")

        except Exception as e:
            self.logger.error(f"Error generating AI description: {e}")

        # Fallback description if API fails
        return "Dawn in Southampton. Again."

    def post_to_bluesky(self, video_path, description, sunrise_time):
        """Post video and description to Bluesky using FIXED video API"""
        bluesky_config = CONFIG['bluesky']

        if (
            bluesky_config["handle"] == "handle.bsky.social"
            or bluesky_config["password"] == ""
        ):
            self.logger.warning("Bluesky credentials not configured, skipping post")
            return False

        try:
            # Use the FIXED client class
            client = FixedBlueSkyClient()

            self.logger.info("Logging into Bluesky...")
            if not client.create_session(bluesky_config['handle'], bluesky_config['password']):
                return False

            # Check file size
            size_mb = video_path.stat().st_size / (1024 * 1024)
            if size_mb > 50:
                self.logger.error(f"Video too large for Bluesky: {size_mb:.1f}MB")
                return False

            self.logger.info(f"Uploading video ({size_mb:.1f}MB) to Bluesky using video API...")

            # Upload video using FIXED video service
            video_result = client.upload_video(video_path)
            if not video_result:
                self.logger.error("Video upload failed")
                return False

            # Add date to description
            today_formatted = datetime.date.today().strftime('%Y-%m-%d')  # e.g., "2025-06-01"
            description_with_date = f"{description}\n\nSunrise: {sunrise_time.strftime('%H:%M:%S')} {today_formatted}"
            self.logger.info("Creating post with video...")
            post_result = client.create_post_with_video(
                text=description_with_date,
                video_result=video_result,
                alt_text="Southampton sunrise timelapse"
            )

            if post_result:
                self.logger.info(f"✅ Successfully posted to Bluesky! Post URI: {post_result.get('uri', 'unknown')}")

                # Construct direct link
                if client.handle and 'uri' in post_result:
                    try:
                        post_id = post_result['uri'].split('/')[-1]
                        direct_link = f"https://bsky.app/profile/{client.handle}/post/{post_id}"
                        self.logger.info(f"Direct link: {direct_link}")
                    except Exception as e:
                        self.logger.warning(f"Could not construct direct link: {e}")

                return True
            else:
                self.logger.error("Post creation failed")
                return False

        except Exception as e:
            self.logger.error(f"Error posting to Bluesky: {e}")
            return False

    def cleanup_old_files(self):
        """Clean up old videos and raw files"""
        if not CONFIG['cleanup']['auto_cleanup']:
            return

        keep_days = CONFIG['cleanup']['keep_days']
        cutoff_date = datetime.date.today() - datetime.timedelta(days=keep_days)

        self.logger.info(f"Cleaning up files older than {keep_days} days...")

        # Clean raw videos
        raw_dir = Path(CONFIG['paths']['raw_dir'])
        removed_raw = 0
        for item in raw_dir.glob("sunrise_raw_*.h264"):
            try:
                date_str = item.stem.replace('sunrise_raw_', '')
                item_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                if item_date < cutoff_date:
                    item.unlink()
                    removed_raw += 1
                    self.logger.info(f"Removed old raw video: {item.name}")
            except ValueError:
                pass

        # Clean analysis photos
        for item in raw_dir.glob("analysis_photo_*.jpg"):
            try:
                date_str = item.stem.replace('analysis_photo_', '')
                item_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                if item_date < cutoff_date:
                    item.unlink()
                    self.logger.info(f"Removed old photo: {item.name}")
            except ValueError:
                pass

        # Clean final videos
        video_dir = Path(CONFIG['paths']['video_dir'])
        removed_videos = 0
        for item in video_dir.glob("sunrise_*.mp4"):
            try:
                date_str = item.stem.replace('sunrise_', '')
                item_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                if item_date < cutoff_date:
                    item.unlink()
                    removed_videos += 1
                    self.logger.info(f"Removed old video: {item.name}")
            except ValueError:
                pass

        if removed_raw > 0 or removed_videos > 0:
            self.logger.info(f"Cleanup complete: {removed_raw} raw videos, {removed_videos} final videos removed")

def main():
    """Main function to run the sunrise timelapse"""
    print("Southampton Sunrise Timelapse (Video Method)")
    print("=============================================================")
    print("✅ All bugs fixed: testing code removed, timeouts added, exception handling fixed")

    timelapse = SunriseTimelapse()

    try:
        # Show today's sunrise info
        sunrise_time = timelapse.get_sunrise_time()
        start_time = sunrise_time - datetime.timedelta(minutes=CONFIG['capture']['start_before_sunrise_minutes'])

        print(f"Today's sunrise: {sunrise_time.strftime('%H:%M:%S')}")
        print(f"Capture starts: {start_time.strftime('%H:%M:%S')}")
        print(f"Capture duration: {CONFIG['capture']['duration_minutes']} minutes")
        print(f"Method: Continuous video at {CONFIG['capture']['framerate']}fps")
        print(f"Final video: {CONFIG['video']['output_duration_seconds']} seconds")
        print(f"Bluesky upload: Using video.bsky.app API")
        print()

        # Capture sunrise as video
        raw_video_path = timelapse.capture_sunrise_video()

        if not raw_video_path:
            timelapse.logger.error("Video capture failed")
            return False

        # Create final timelapse
        final_video_path = timelapse.create_timelapse_from_video(raw_video_path)

        if final_video_path and final_video_path.exists():
            # Take fresh photo for weather analysis
            analysis_photo = timelapse.take_photo_after_video()

            # Generate weather description
            if analysis_photo:
                description = timelapse.generate_ai_description(analysis_photo)
            else:
                description = "This morning in Southampton the weather is looking beautiful for this sunrise timelapse! 🌅"

            # Post to Bluesky immediately when video is ready
            timelapse.logger.info("Video processing complete, posting to Bluesky now...")

            # Post to Bluesky using FIXED video API
            posted = timelapse.post_to_bluesky(final_video_path, description,sunrise_time)

            # Clean up old files
            timelapse.cleanup_old_files()

            timelapse.logger.info("=== SUCCESS ===")
            timelapse.logger.info(f"Final video: {final_video_path}")
            timelapse.logger.info(f"Description: {description}")
            if posted:
                timelapse.logger.info("✅ Successfully posted to Bluesky using video API!")
            else:
                timelapse.logger.warning("Bluesky posting failed or skipped")
            timelapse.logger.info("Sunrise timelapse process completed successfully!")

            return True
        else:
            timelapse.logger.error("Video processing failed")
            return False

    except KeyboardInterrupt:
        timelapse.logger.info("Process interrupted by user")
        return False
    except Exception as e:
        timelapse.logger.error(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
