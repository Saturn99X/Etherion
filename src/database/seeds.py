# src/database/seeds.py
from sqlmodel import Session
from src.database.models import ToneProfile
from datetime import datetime


def create_default_tone_profiles(tenant_id: int, user_id: int, session: Session):
    """
    Create default tone profiles for a new tenant.
    
    Args:
        tenant_id: The tenant ID
        user_id: The user ID
        session: Database session
    """
    default_profiles = [
        {
            "name": "Professional",
            "profile_text": "Use a formal, professional tone with proper grammar and business language.",
            "description": "Formal tone suitable for business communications",
            "is_default": True
        },
        {
            "name": "Casual",
            "profile_text": "Use a friendly, conversational tone that's approachable and easy to read.",
            "description": "Friendly tone for informal communications",
            "is_default": True
        },
        {
            "name": "Witty",
            "profile_text": "Use a clever, humorous tone with creative wordplay and engaging expressions.",
            "description": "Creative and humorous tone for engaging content",
            "is_default": True
        }
    ]
    
    for profile_data in default_profiles:
        # Check if profile already exists
        existing_profile = session.query(ToneProfile).filter(
            ToneProfile.tenant_id == tenant_id,
            ToneProfile.name == profile_data["name"]
        ).first()
        
        if not existing_profile:
            tone_profile = ToneProfile(
                name=profile_data["name"],
                profile_text=profile_data["profile_text"],
                description=profile_data["description"],
                is_default=profile_data["is_default"],
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                user_id=user_id,
                tenant_id=tenant_id
            )
            session.add(tone_profile)
    
    session.commit()