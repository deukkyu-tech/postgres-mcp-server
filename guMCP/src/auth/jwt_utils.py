import jwt
import logging
from datetime import datetime, timedelta
from os import environ
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("jwt_utils")

class JWTUtils:
    def __init__(self, jwt_secret=None):
        self._jwt_secret = jwt_secret or environ.get("JWT_SECRET", "default-secret")  # Secret으로 관리 권장

    def generate_jwt_token(self, user_id: str) -> str:
        """Generate a JWT token for the given user_id with KST timezone."""
        kst = pytz.timezone('Asia/Seoul')
        current_time = datetime.now(kst)
        
        payload = {
            "user_id": user_id,
            "iat": current_time,  # Issued at time in KST
            "exp": current_time + timedelta(hours=24)  # Token expires in 24 hours from issuance
        }
        try:
            return jwt.encode(payload, self._jwt_secret, algorithm="HS256")
        except Exception as e:
            logger.error(f"Failed to generate JWT token for user {user_id}: {e}")
            raise ValueError(f"Failed to generate JWT token: {str(e)}")

    def verify_jwt_token(self, token: str) -> dict:
        """Verify a JWT token and return the payload."""
        try:
            payload = jwt.decode(token, self._jwt_secret, algorithms=["HS256"])
            if "user_id" not in payload:
                raise ValueError("Invalid JWT payload: user_id missing")
            return payload
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {e}")
            raise ValueError("Invalid or expired JWT token")