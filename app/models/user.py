"""User domain models for CarbonSaathi.

Defines the Indian state enumeration used for CEA grid-factor lookups,
the home-profile sub-model, and the top-level user profile entity written
to ``users/{uid}`` in Firestore.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.shared import IsoTimestamp


class IndianState(StrEnum):
    """All 28 Indian states and 8 Union Territories.

    Values are title-cased strings matching the naming convention used in the
    CEA CO₂ Baseline Database for state-wise grid emission factors.
    """

    ANDHRA_PRADESH = "Andhra Pradesh"
    ARUNACHAL_PRADESH = "Arunachal Pradesh"
    ASSAM = "Assam"
    BIHAR = "Bihar"
    CHHATTISGARH = "Chhattisgarh"
    GOA = "Goa"
    GUJARAT = "Gujarat"
    HARYANA = "Haryana"
    HIMACHAL_PRADESH = "Himachal Pradesh"
    JHARKHAND = "Jharkhand"
    KARNATAKA = "Karnataka"
    KERALA = "Kerala"
    MADHYA_PRADESH = "Madhya Pradesh"
    MAHARASHTRA = "Maharashtra"
    MANIPUR = "Manipur"
    MEGHALAYA = "Meghalaya"
    MIZORAM = "Mizoram"
    NAGALAND = "Nagaland"
    ODISHA = "Odisha"
    PUNJAB = "Punjab"
    RAJASTHAN = "Rajasthan"
    SIKKIM = "Sikkim"
    TAMIL_NADU = "Tamil Nadu"
    TELANGANA = "Telangana"
    TRIPURA = "Tripura"
    UTTAR_PRADESH = "Uttar Pradesh"
    UTTARAKHAND = "Uttarakhand"
    WEST_BENGAL = "West Bengal"
    # Union Territories
    ANDAMAN_AND_NICOBAR = "Andaman and Nicobar Islands"
    CHANDIGARH = "Chandigarh"
    DADRA_AND_NAGAR_HAVELI = "Dadra and Nagar Haveli and Daman and Diu"
    DELHI = "Delhi"
    JAMMU_AND_KASHMIR = "Jammu and Kashmir"
    LADAKH = "Ladakh"
    LAKSHADWEEP = "Lakshadweep"
    PUDUCHERRY = "Puducherry"


Dietary = Literal["veg", "non-veg", "eggetarian"]
"""Primary dietary category for food emission factor selection."""

FridgeClass = Literal["5-star", "4-star", "3-star", "2-star", "1-star", "unknown"]
"""BEE star rating of the primary household refrigerator."""


class HomeProfile(BaseModel):
    """Physical attributes of the user's home that affect electricity estimates.

    Attributes:
        bhk: Number of bedrooms (1-5).  Used to scale appliance baseline.
        has_ac: Whether the home has an air conditioner.
        fridge_class: BEE star rating of the primary refrigerator.
        dietary: Primary dietary category for food emission factors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    bhk: int = Field(ge=1, le=5, description="Bedrooms, hall, kitchen count (1-5)")
    has_ac: bool
    fridge_class: FridgeClass
    dietary: Dietary


class UserProfile(BaseModel):
    """Complete user profile stored at ``users/{uid}`` in Firestore.

    Attributes:
        uid: Firebase Authentication UID (primary key).
        email: Verified email address (``EmailStr`` enforces RFC format); ``None``
            when the verified token carries no email claim.
        display_name: Human-readable name from Google Sign-In.
        state: Indian state used to select the CEA grid emission factor; ``None``
            until the user completes onboarding.
        home_profile: Home attributes for electricity and food estimation; ``None``
            until the user completes onboarding.
        created_at: Account creation timestamp (UTC, timezone-aware).
        last_active: Last recorded user activity timestamp (UTC, timezone-aware).
        onboarding_complete: ``True`` once the user has submitted the onboarding form.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    uid: str
    email: EmailStr | None = None
    display_name: str
    state: IndianState | None = None
    home_profile: HomeProfile | None = None
    created_at: IsoTimestamp
    last_active: IsoTimestamp
    onboarding_complete: bool = False
