import base64
import hashlib
import re
import secrets
import sys
import uuid

from rich.console import Console

from ._env import require_dotenv, check_required_vars, REQUIRED_FOR_DB
from sqlalchemy.exc import IntegrityError

console = Console()


def run(
    name: str,
    email: str,
    password: str,
    subdomain: str = None,
) -> None:
    env = require_dotenv()
    check_required_vars(env, *REQUIRED_FOR_DB)

    from dotenv import load_dotenv
    load_dotenv(".env", override=False)

    if subdomain is None:
        subdomain = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")

    console.print(f"Creating tenant [bold]{name}[/bold] (subdomain={subdomain})…")

    try:
        from src.database.db import get_db
        from src.database.ts_models import Tenant, User

        db = get_db()
        try:
            tenant = Tenant(
                name=name,
                subdomain=subdomain,
                tenant_id=f"t_{uuid.uuid4().hex[:12]}",
                admin_email=email,
            )
            db.add(tenant)
            db.flush()

            pwd_hash = _hash_password(password)
            user = User(
                user_id=f"pwd_{secrets.token_hex(8)}",
                email=email,
                name=name,
                provider="password",
                profile_picture_url=None,
                tenant_id=tenant.id,
                password_hash=pwd_hash,
            )
            db.add(user)
            db.commit()

            console.print(f"[green]✓[/green] Tenant created: [bold]{tenant.tenant_id}[/bold]")
            console.print(f"[green]✓[/green] Admin user:   [bold]{user.email}[/bold]")
        except IntegrityError:
            db.rollback()
            console.print("[yellow]⚠[/yellow]  Tenant already exists — skipping creation.")
            console.print("[green]✓[/green]  Setup can continue with existing account.")
            return
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise SystemExit(1)


def _hash_password(password: str, iterations: int = 200_000) -> str:
    """PBKDF2-SHA256 hash matching src/auth/service.py format."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return (
        f"pbkdf2_sha256${iterations}"
        f"${base64.b64encode(salt).decode()}"
        f"${base64.b64encode(dk).decode()}"
    )
