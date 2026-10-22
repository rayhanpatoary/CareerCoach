from cv.repository import CvRepository
from .tables import JobFitRecord
from .schemas import JobFitSummary,JobFitReview,JobFitHistory


class JobFitRepository(CvRepository):
    record_type=JobFitRecord
    summary_type=JobFitSummary
    view_type=JobFitReview
    history_type=JobFitHistory
    rate_namespace="job-fit"
    label="Job-fit analysis"
