from enum import Enum

class DeepZoomStatus(str, Enum):
    """
    Status of Deep Zoom tile generation.
    Used in 'photos' table 'deepzoom_status' column and in processing service.
    """
    NONE = "none"
    SCHEDULED = "scheduled"   # Enqueued for processing
    PROCESSING = "processing" # Currently generating tiles
    UPLOADING = "uploading"   # Uploading tiles to storage
    FINALIZING = "finalizing" # Creating metadata/manifests
    COMPLETED = "completed"   # Fully processed and ready
    ERROR = "error"           # Permanent failure (DB uses 'error')
    FAILED = "failed"         # Alias often used in service (should map to ERROR in DB)
    RETRYING = "retrying"     # Temporary failure, will retry

    @property
    def is_active(self) -> bool:
        """Returns True if the status implies active processing."""
        return self in (
            DeepZoomStatus.SCHEDULED,
            DeepZoomStatus.PROCESSING,
            DeepZoomStatus.UPLOADING,
            DeepZoomStatus.FINALIZING,
            DeepZoomStatus.RETRYING
        )

    @property
    def is_terminal(self) -> bool:
        """Returns True if the state is final (success or permanent failure)."""
        return self in (
            DeepZoomStatus.COMPLETED,
            DeepZoomStatus.ERROR,
            DeepZoomStatus.FAILED
        )
