from pydantic import BaseModel, ConfigDict


class ConversationParticipantResponse(BaseModel):
    """A profile visible to the participants in one authorized conversation."""

    ref: str
    display_name: str | None = None
    avatar: str | None = None

    model_config = ConfigDict(extra="forbid")
