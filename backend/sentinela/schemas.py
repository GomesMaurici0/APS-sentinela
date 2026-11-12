from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from sentinela.autorizacao import UserPermission

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")]
ImageString = Annotated[str, Field(min_length=1, max_length=1048576)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, strict=True)


class Login(Input):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid", strict=True)


class UserUpdate(Input):
    display_name: str = Field(min_length=1, max_length=100)
    level: Literal[1, 2, 3]
    divisions: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(
        default_factory=list, max_length=20
    )
    active: bool = True

    @field_validator("level", mode="before")
    @classmethod
    def integer_level(cls, value):
        if type(value) is not int:
            raise ValueError("Nível deve ser inteiro")
        return value

    @model_validator(mode="after")
    def permissions(self):
        if isinstance(self.level, bool):
            raise ValueError("Nível inválido")
        if len(set(self.divisions)) != len(self.divisions):
            raise ValueError("Divisões duplicadas")
        UserPermission(self.level, frozenset(self.divisions), self.active)
        return self


class UserCreate(UserUpdate):
    subject_id: Identifier


class ImageInput(Input):
    image: ImageString


class Enrollment(Input):
    consent: Literal[True]
    images: list[ImageString] = Field(min_length=5, max_length=5)

    @field_validator("consent", mode="before")
    @classmethod
    def explicit_consent(cls, value):
        if value is not True:
            raise ValueError("Consentimento explícito obrigatório")
        return value


class AttemptInput(ImageInput):
    requested_level: Literal[1, 2, 3]
    division: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("requested_level", mode="before")
    @classmethod
    def integer_level(cls, value):
        if type(value) is not int:
            raise ValueError("Nível deve ser inteiro")
        return value

    @model_validator(mode="after")
    def target(self):
        if isinstance(self.requested_level, bool):
            raise ValueError("Nível inválido")
        if (self.requested_level == 2) != (self.division is not None):
            raise ValueError("Divisão é exigida somente no nível 2")
        return self


class ErrorResponse(BaseModel):
    detail: str


class SessionResponse(BaseModel):
    username: str
    csrf_token: str
    expires_at: float


class UserResponse(BaseModel):
    subject_id: str
    display_name: str
    level: int
    active: bool
    divisions: list[str]
    sample_count: int
    consent_at: str | None
    consent_version: str | None
    created_at: str
    updated_at: str


class UserPage(BaseModel):
    items: list[UserResponse]
    total: int
    offset: int
    limit: int


class CaptureResponse(BaseModel):
    status: str
    brightness: float | None
    sharpness: float | None
    elapsed_ms: float
    width: int | None
    height: int | None
    faces: list[list[float]]
    aligned_image: str | None


class AttemptResponse(BaseModel):
    id: int
    occurred_at: str
    subject_id: str | None
    requested_level: int
    division: str | None
    granted: bool
    reason: str
    similarity: float | None
    margin: float | None
    elapsed_ms: float
    model_id: str
    config: dict


class DecisionResponse(AttemptResponse):
    capture: CaptureResponse | None = None


class AttemptPage(BaseModel):
    items: list[AttemptResponse]
    total: int
    offset: int
    limit: int


class StatsResponse(BaseModel):
    users: int
    enrolled: int
    attempts: int
    granted: int
    denied: int


class ImportResponse(BaseModel):
    imported: int
    already_present: int
