from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables / backend/.env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- database ---
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "preschool"

    # --- auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720  # 12 hours

    # --- bootstrap admin (created on first start if the users collection is empty) ---
    admin_email: str = "admin@school.com"
    admin_password: str = "admin123"
    admin_name: str = "Administrator"

    # --- school profile (printed on receipts) ---
    # Hello Kids is a franchise: school_name should be YOUR branch, and the
    # address/phone/email must be your branch's — not the franchise head office.
    school_name: str = "Hello Kids Preschool"
    school_branch: str = ""  # e.g. "Kasturi Nagar Branch" — shown next to the name
    # The legal entity running the branch. Shown under the school name in the
    # app and printed on every receipt, since the trust is the body parents are
    # actually paying.
    school_trust: str = "Sahjaswi Educational Trust"
    school_tagline: str = "The Power of Early Childhood Education"
    school_address: str = "Set SCHOOL_ADDRESS in backend/.env"
    school_phone: str = "+91 00000 00000"
    school_email: str = "info@hellokids.co.in"
    school_website: str = "www.hellokids.co.in"
    school_logo: str = "hellokids-logo.png"  # file in backend/app/assets/
    # Optional pre-designed banner (the printed letterhead). When the file is
    # present it replaces the whole composed receipt header — logo, names,
    # tagline, address and phone are all already inside the artwork, so
    # repeating them below it would just duplicate the information.
    # Give a bare name to accept any of the extensions below, or a full
    # filename to pin one exactly.
    school_letterhead: str = "letterhead"  # file in backend/app/assets/
    currency_symbol: str = "₹"
    currency_code: str = "INR"

    @property
    def school_full_name(self) -> str:
        return f"{self.school_name} — {self.school_branch}" if self.school_branch else self.school_name

    @property
    def school_legal_line(self) -> str:
        """"<school> — <branch>, run by <trust>", for receipt headers."""
        if not self.school_trust:
            return self.school_full_name
        return f"{self.school_full_name} · A unit of {self.school_trust}"

    @property
    def logo_path(self) -> Path | None:
        path = Path(__file__).parent / "assets" / self.school_logo
        return path if path.is_file() else None

    @property
    def letterhead_path(self) -> Path | None:
        """The banner file, whatever image format it was supplied in."""
        if not self.school_letterhead:
            return None
        assets = Path(__file__).parent / "assets"
        name = Path(self.school_letterhead)
        if name.suffix:
            path = assets / name
            return path if path.is_file() else None
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            path = assets / f"{name}{suffix}"
            if path.is_file():
                return path
        return None

    @property
    def letterhead_filename(self) -> str | None:
        """Name the SPA serves the same banner under, from frontend/public/."""
        path = self.letterhead_path
        return path.name if path else None

    # --- academics ---
    academic_year: str = "2026-27"
    session_start_month: int = 4  # April

    # --- registers ---
    # Prefix for generated admission numbers, e.g. HKB20260002 for Hello Kids
    # Bells. Change this and only *new* admissions are affected — numbers
    # already issued are never rewritten automatically.
    admission_prefix: str = "HKB"
    employee_prefix: str = "EMP"

    # --- misc ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
