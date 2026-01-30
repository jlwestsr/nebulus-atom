import base64
import mimetypes
import os
from nebulus_atom.utils.logger import setup_logger

logger = setup_logger(__name__)


class ImageService:
    @staticmethod
    def encode_image(image_path: str) -> str:
        """Encodes an image to base64."""
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")

        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type or not mime_type.startswith("image"):
            raise ValueError(f"File is not an image: {image_path}")

        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

        return f"data:{mime_type};base64,{encoded_string}"


class ImageServiceManager:
    def __init__(self):
        self.service = ImageService()

    def get_service(self, session_id: str = "default") -> ImageService:
        return self.service
