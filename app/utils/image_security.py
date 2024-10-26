import requests
import magic
import base64
from urllib.parse import urlparse
from typing import Optional, Tuple
from fastapi import HTTPException
import io
from PIL import Image


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

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL to prevent SSRF attacks."""
        try:
            parsed = urlparse(url)

            # Only allow HTTP(S) protocols
            if parsed.scheme not in ('http', 'https'):
                return False

            # Prevent localhost access
            hostname = parsed.hostname.lower()
            if hostname in ('localhost', '127.0.0.1', '::1'):
                return False

            # Prevent private network access
            private_networks = [
                '10.',
                '172.16.', '172.17.', '172.18.', '172.19.',
                '172.20.', '172.21.', '172.22.', '172.23.',
                '172.24.', '172.25.', '172.26.', '172.27.',
                '172.28.', '172.29.', '172.30.', '172.31.',
                '192.168.'
            ]
            if any(hostname.startswith(net) for net in private_networks):
                return False

            # Prevent non-standard ports
            if parsed.port and parsed.port not in (80, 443):
                return False

            return True

        except Exception:
            return False

    @staticmethod
    async def download_and_validate_image(url: str) -> Optional[str]:
        """
        Download image from URL, validate it, and convert to data URL.
        Returns None if validation fails.
        """
        try:
            # Validate URL first
            if not ImageSecurityUtils.validate_url(url):
                raise HTTPException(status_code=400, detail="Invalid image URL")

            # Download image with timeout
            response = requests.get(url, timeout=10, stream=True)
            response.raise_for_status()

            # Check file size
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > ImageSecurityUtils.MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="Image too large")

            # Read content
            content = response.content

            # Validate MIME type using python-magic
            mime_type = magic.from_buffer(content, mime=True)
            if mime_type not in ImageSecurityUtils.ALLOWED_MIME_TYPES:
                raise HTTPException(status_code=400, detail="Invalid image format")

            # Validate image using PIL
            try:
                img = Image.open(io.BytesIO(content))

                # Check dimensions
                if img.size[0] > ImageSecurityUtils.MAX_IMAGE_DIMENSIONS[0] or \
                        img.size[1] > ImageSecurityUtils.MAX_IMAGE_DIMENSIONS[1]:
                    raise HTTPException(status_code=400, detail="Image dimensions too large")

                # Convert to data URL
                buffer = io.BytesIO()
                img.save(buffer, format=img.format)
                base64_image = base64.b64encode(buffer.getvalue()).decode()

                return f"data:{mime_type};base64,{base64_image}"

            except Exception as e:
                raise HTTPException(status_code=400, detail="Invalid image data")

        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=400, detail="Failed to download image")
        except Exception as e:
            raise HTTPException(status_code=400, detail="Image processing failed")

    @staticmethod
    def validate_data_url(data_url: str) -> bool:
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
            if mime_type not in ImageSecurityUtils.ALLOWED_MIME_TYPES:
                return False

            # Validate base64 data
            try:
                decoded = base64.b64decode(data)
                # Additional validation could be added here
                return True
            except Exception:
                return False

        except Exception:
            return False