import requests
import magic
import base64
import uuid
import boto3
import logging
from botocore.config import Config
from urllib.parse import urlparse
from typing import Optional
from fastapi import HTTPException
import io
from PIL import Image
from datetime import datetime

from config import AWS_KEY_ID, AWS_SECRET_KEY

logger = logging.getLogger(__name__)


class ImageSecurityUtils:
    # Allowed image MIME types
    ALLOWED_MIME_TYPES = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp'
    }

    # Maximum file size (5MB)
    MAX_FILE_SIZE = 5 * 1024 * 1024

    # Maximum image dimensions
    MAX_IMAGE_DIMENSIONS = (2048, 2048)

    # Yandex Cloud S3 configuration
    S3_CONFIG = {
        'aws_access_key_id': AWS_KEY_ID,
        'aws_secret_access_key': AWS_SECRET_KEY,
        'endpoint_url': 'https://storage.yandexcloud.net',
        'region_name': 'ru-central1'
    }

    @classmethod
    def _get_s3_client(cls):
        """Create and return a properly configured S3 client for Yandex Cloud."""
        config = Config(
            region_name='ru-central1',
            s3={
                'addressing_style': 'virtual'
            }
        )

        return boto3.client(
            's3',
            endpoint_url=cls.S3_CONFIG['endpoint_url'],
            aws_access_key_id=cls.S3_CONFIG['aws_access_key_id'],
            aws_secret_access_key=cls.S3_CONFIG['aws_secret_access_key'],
            region_name=cls.S3_CONFIG['region_name'],
            config=config
        )

    @classmethod
    def _generate_unique_filename(cls, original_filename: str = None) -> str:
        """Generate a unique filename using UUID and timestamp."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        extension = '.jpg'  # Default extension

        if original_filename:
            ext = original_filename.rsplit('.', 1)[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                extension = f'.{ext}'

        return f'images/{timestamp}_{unique_id}{extension}'

    @classmethod
    def validate_url(cls, url: str) -> bool:
        """Validate URL to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)

            # Only allow HTTP(S) protocols
            if parsed.scheme not in ('http', 'https'):
                return False

            # Block localhost and private network access
            hostname = parsed.hostname.lower() if parsed.hostname else ''
            blocked_hostnames = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}
            if hostname in blocked_hostnames:
                return False

            # Block private networks
            private_networks = [
                '10.',
                '172.16.', '172.17.', '172.18.', '172.19.',
                '172.20.', '172.21.', '172.22.', '172.23.',
                '172.24.', '172.25.', '172.26.', '172.27.',
                '172.28.', '172.29.', '172.30.', '172.31.',
                '192.168.',
                'fc00:',
                'fe80:'
            ]
            if any(hostname.startswith(net) for net in private_networks):
                return False

            # Block non-standard ports
            if parsed.port and parsed.port not in (80, 443):
                return False

            return True
        except Exception as e:
            logger.error(f"URL validation error: {str(e)}")
            return False

    @classmethod
    def validate_data_url(cls, data_url: str) -> bool:
        """Validate if a string is a proper image data URL."""
        try:
            if not data_url.startswith('data:image/'):
                return False

            # Split header and data
            header, data = data_url.split(',', 1)

            # Validate header format
            if ';base64' not in header:
                return False

            # Validate mime type
            mime_type = header[5:header.index(';')]
            if mime_type not in cls.ALLOWED_MIME_TYPES:
                return False

            # Validate base64 data
            try:
                decoded = base64.b64decode(data)
                if len(decoded) > cls.MAX_FILE_SIZE:
                    return False
                return True
            except Exception as e:
                logger.error(f"Base64 validation error: {str(e)}")
                return False

        except Exception as e:
            logger.error(f"Data URL validation error: {str(e)}")
            return False

    @classmethod
    async def process_and_upload_image(cls, image_data: bytes, mime_type: str) -> str:
        """Process image data and upload to Yandex Cloud S3."""
        try:
            # Validate image using PIL
            with Image.open(io.BytesIO(image_data)) as img:
                # Check dimensions
                if img.size[0] > cls.MAX_IMAGE_DIMENSIONS[0] or \
                        img.size[1] > cls.MAX_IMAGE_DIMENSIONS[1]:
                    raise HTTPException(status_code=400, detail="Image dimensions too large")

                # Optimize image
                output = io.BytesIO()
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background

                img.save(output, format='JPEG', quality=85, optimize=True)
                image_data = output.getvalue()

            # Generate filename and upload to S3
            filename = cls._generate_unique_filename()
            s3_client = cls._get_s3_client()

            try:
                s3_client.put_object(
                    Bucket='readroom',
                    Key=filename,
                    Body=image_data,
                    ContentType='image/jpeg'
                )
            except Exception as e:
                logger.error(f"S3 upload error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")

            # Return the public URL of the uploaded image
            return f"https://storage.yandexcloud.net/readroom/{filename}"

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Image processing error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")

    @classmethod
    async def handle_image_upload(cls, image_source: str) -> str:
        """Handle image upload from either URL or data URL."""
        try:
            if image_source.startswith('data:'):
                # Handle data URL
                if not cls.validate_data_url(image_source):
                    raise HTTPException(status_code=400, detail="Invalid image data URL")

                # Extract mime type and decode base64 data
                header, encoded_data = image_source.split(',', 1)
                mime_type = header[5:header.index(';')]
                image_data = base64.b64decode(encoded_data)

            else:
                # Handle URL
                if not cls.validate_url(image_source):
                    raise HTTPException(status_code=400, detail="Invalid image URL")

                # Download image
                try:
                    response = requests.get(image_source, timeout=10, stream=True)
                    response.raise_for_status()

                    # Check file size
                    content_length = response.headers.get('content-length')
                    if content_length and int(content_length) > cls.MAX_FILE_SIZE:
                        raise HTTPException(status_code=400, detail="Image too large")

                    image_data = response.content
                    mime_type = magic.from_buffer(image_data, mime=True)
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to download image: {str(e)}")
                    raise HTTPException(status_code=400, detail="Failed to download image")

            # Validate mime type
            if mime_type not in cls.ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=400, detail="Invalid image format")

            # Process and upload image
            return await cls.process_and_upload_image(image_data, mime_type)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Image upload handling error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")