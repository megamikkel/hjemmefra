"""An adapter that always fails - used to test graceful degradation."""
from hjemmefra.ingestion.base import FetchResult, SourceAdapter, SourceDescriptor


class FailingAdapter(SourceAdapter):
    def __init__(self, descriptor: SourceDescriptor, message: str = "source unavailable"):
        self.descriptor = descriptor
        self.message = message

    def fetch(self) -> FetchResult:
        return FetchResult(descriptor=self.descriptor, error=self.message)
