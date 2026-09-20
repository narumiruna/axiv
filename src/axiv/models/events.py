from axiv.models.common import ExternalModel
from axiv.models.common import ItemCollection


class Event(ExternalModel):
    id: str
    title: str
    link: str
    date: str
    speaker: str | None = None
    organization: str
    recording: str | None = None


class EventsResponse(ItemCollection[Event]):
    pass
